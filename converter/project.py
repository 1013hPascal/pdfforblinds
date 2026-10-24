"""Projektordner: eine Textdatei und Bilder pro Seite plus project.json.

Jede Seite wird sofort gespeichert, damit ein abgebrochener Lauf fortgesetzt
werden kann.
"""

import json
from datetime import datetime
from pathlib import Path

from .blocks import CAPTION, IMAGE, Block
from .classify import classify, kind_text
from .images import crop_hires
from .render import math_to_dollar, render_page

VERSION = 1


class Project:
    def __init__(self, folder: Path, source: Path):
        self.folder = folder
        self.source = source
        self.json_path = folder / "project.json"
        for sub in ("pages", "images", "renders"):
            (folder / sub).mkdir(parents=True, exist_ok=True)

        if self.json_path.exists():
            self.data = json.loads(self.json_path.read_text(encoding="utf-8"))
            if Path(self.data["quelle"]).name != source.name:
                raise SystemExit(
                    f"Der Ordner {folder} gehört zu {self.data['quelle']}, nicht zu {source.name}."
                )
        else:
            self.data = {
                "version": VERSION,
                "quelle": str(source),
                "erstellt": datetime.now().isoformat(timespec="seconds"),
                "seitenzahl": 0,
                "seiten": [],
            }
            self._write()

    def set_page_count(self, count: int):
        self.data["seitenzahl"] = count
        self._write()

    def render_path(self, nr: int) -> Path:
        return self.folder / "renders" / f"{nr:04d}.png"

    def is_done(self, nr: int) -> bool:
        return any(p["nr"] == nr for p in self.data["seiten"])

    def is_complete(self) -> bool:
        return 0 < self.data["seitenzahl"] <= len(self.data["seiten"])

    def save_page(self, nr: int, engine: str, reason: str, blocks: list[Block]):
        images = []
        for i, block in enumerate(blocks):
            if block.type != IMAGE:
                continue
            number = len(images) + 1
            rel = f"images/p{nr:04d}_{number}.png"
            image = crop_hires(self.source, nr, block.bbox) or block.image
            image.convert("RGB").save(self.folder / rel)
            caption = None
            if i + 1 < len(blocks) and blocks[i + 1].type == CAPTION:
                caption = math_to_dollar(blocks[i + 1].content).strip()
            kind, certainty = classify(image)
            images.append({
                "nr": number,
                "datei": rel,
                "bbox": [round(v, 4) for v in block.bbox] if block.bbox else None,
                "bildunterschrift": caption,
                "typ": kind,
                "typ_sicherheit": round(certainty, 2),
                "beschreibung": None,
            })

        text_rel = f"pages/{nr:04d}.txt"
        kinds = [kind_text(img["typ"], img["typ_sicherheit"]) for img in images]
        (self.folder / text_rel).write_text(render_page(blocks, kinds), encoding="utf-8")

        self.data["seiten"] = [p for p in self.data["seiten"] if p["nr"] != nr]
        self.data["seiten"].append({
            "nr": nr,
            "engine": engine,
            "grund": reason,
            "text": text_rel,
            "render": f"renders/{nr:04d}.png",
            "bilder": images,
        })
        self.data["seiten"].sort(key=lambda p: p["nr"])
        self._write()

    def _write(self):
        tmp = self.json_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.json_path)
        self._write_full_text()

    def _write_full_text(self):
        """Alle fertigen Seiten in einer Datei, mit <seite>-Markierungen wie in den Blinden-Fassungen."""
        parts = []
        for page in self.data["seiten"]:
            text = (self.folder / page["text"]).read_text(encoding="utf-8")
            parts.append(f"<seite>{page['nr']}</seite>\n{text}")
        (self.folder / "gesamt.txt").write_text("\n".join(parts), encoding="utf-8")
