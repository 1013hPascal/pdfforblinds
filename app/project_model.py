"""Lädt ein vom Konverter erzeugtes Projekt (.pdfforblinds oder Arbeitsordner) und speichert Bildbeschreibungen."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from converter import package as pkg
from converter.classify import kind_text
from converter.render import image_placeholder

# <bild 1: keine Beschreibung> oder mit Bildart <bild 1, Zeichnung: Beschreibung vorhanden>
PLACEHOLDER_RE = re.compile(r"<bild (\d+)(?:, [^:<>]+)?: [^<>]*>")


@dataclass
class ImageInfo:
    page: int
    number: int
    path: Path
    caption: str | None
    description: str | None
    bbox: list[float] | None = None
    source: Path | None = None   # Original-PDF bzw. -Foto
    kind: str | None = None      # Bildart, z. B. "Zeichnung"
    certainty: float | None = None
    focus: str | None = None     # Frage, unter der die Beschreibung entstand

    @property
    def described(self) -> bool:
        return bool(self.description)

    @property
    def kind_label(self) -> str:
        return kind_text(self.kind, self.certainty)

    def placeholder(self) -> str:
        return image_placeholder(self.number, self.described, self.kind_label)


@dataclass
class PageInfo:
    number: int
    text_path: Path
    render_path: Path
    images: list[ImageInfo]

    def text(self) -> str:
        """Seitentext mit aktuellem Beschreibungsstatus in den Platzhaltern."""
        raw = self.text_path.read_text(encoding="utf-8")
        by_number = {img.number: img for img in self.images}

        def repl(m):
            img = by_number.get(int(m.group(1)))
            return img.placeholder() if img else m.group(0)

        return PLACEHOLDER_RE.sub(repl, raw)

    def image(self, number: int) -> ImageInfo | None:
        return next((img for img in self.images if img.number == number), None)


class Project:
    def __init__(self, folder: Path, package: Path | None = None):
        """folder: Arbeitsordner. package: zugehörige .pdfforblinds-Datei, die bei jeder Änderung
        zusammen mit der Textdatei daneben neu geschrieben wird (None: nur der Ordner)."""
        self.folder = folder
        self.package = package
        self.json_path = folder / "project.json"
        self.data = json.loads(self.json_path.read_text(encoding="utf-8"))
        self.title = Path(self.data["quelle"]).stem
        self.source = self._find_source()
        self.pages: list[PageInfo] = []
        for page in self.data["seiten"]:
            images = [
                ImageInfo(
                    page=page["nr"],
                    number=img["nr"],
                    path=folder / img["datei"],
                    caption=img.get("bildunterschrift"),
                    description=img.get("beschreibung"),
                    bbox=img.get("bbox"),
                    source=self.source,
                    kind=img.get("typ"),
                    certainty=img.get("typ_sicherheit"),
                    focus=img.get("beschreibung_fokus"),
                )
                for img in page["bilder"]
            ]
            self.pages.append(PageInfo(
                number=page["nr"],
                text_path=folder / page["text"],
                render_path=folder / page["render"],
                images=images,
            ))

    @classmethod
    def from_package(cls, package: Path) -> "Project":
        """.pdfforblinds in seinen Arbeitsordner entpacken und öffnen. Das Paket ist maßgeblich."""
        folder = pkg.work_dir(package)
        pkg.unpack(package, folder)
        return cls(folder, package)

    def _find_source(self) -> Path:
        """Original-PDF. Die gleichnamige Datei neben 'pdfforblinds <Name>' hat Vorrang, damit ein
        kopiertes oder verschobenes Paket zu seiner eigenen PDF gehört und nicht zur alten."""
        source = Path(self.data["quelle"])
        if self.package is not None:
            beside = self.package.parent.parent / source.name
            if beside.exists():
                return beside
        return source

    @property
    def recent_entry(self) -> Path:
        """Was in die Liste Zuletzt kommt: die PDF, wenn sie wieder genau zu diesem Paket führt, sonst das Paket."""
        if self.package is None:
            return self.folder
        if self.source.exists() and pkg.package_path(self.source.resolve()) == self.package.resolve():
            return self.source
        return self.package

    @property
    def is_complete(self) -> bool:
        return 0 < self.data.get("seitenzahl", 0) <= len(self.pages)

    def page(self, number: int) -> PageInfo | None:
        return next((p for p in self.pages if p.number == number), None)

    def set_description(self, image: ImageInfo, text: str, model: str, focus: str = ""):
        image.description = text
        image.focus = focus
        for page in self.data["seiten"]:
            if page["nr"] != image.page:
                continue
            for img in page["bilder"]:
                if img["nr"] == image.number:
                    img["beschreibung"] = text
                    img["beschreibung_modell"] = model
                    img["beschreibung_fokus"] = focus or None
        self.save()
        self.update_text_files([image.page])

    def save(self):
        tmp = self.json_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.json_path)

    def update_text_files(self, page_numbers: list[int] | None = None):
        """Platzhalter (Status, Bildart) auch in pages/NNNN.txt und gesamt.txt aktualisieren."""
        for page in self.pages:
            if page_numbers is None or page.number in page_numbers:
                page.text_path.write_text(page.text(), encoding="utf-8")
        parts = [f"<seite>{p.number}</seite>\n{p.text_path.read_text(encoding='utf-8')}" for p in self.pages]
        (self.folder / "gesamt.txt").write_text("\n".join(parts), encoding="utf-8")
        if self.package is not None:
            pkg.export(self.folder, self.package)
