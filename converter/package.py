"""Ablage neben der Quelldatei: Ordner "pdfforblinds <Name>" mit <Name>.pdfforblinds und <Name>.txt.

<Name>.pdfforblinds ist eine ZIP-Datei mit project.json, pages/ und images/ (das Format für das
Programm). <Name>.txt ist das komplette Dokument als Text, mit den Bildbeschreibungen.
Gearbeitet wird in einem Arbeitsordner unter %LOCALAPPDATA%; nach jeder Änderung werden beide
Dateien neu geschrieben.
"""

import hashlib
import json
import os
import re
import tempfile
import time
import zipfile
from pathlib import Path

from .classify import kind_text

SUFFIX = ".pdfforblinds"
FOLDER_PREFIX = "pdfforblinds "
PACKED = ("project.json", "pages/", "images/")     # Seitenbilder (renders/) nur im Arbeitsordner
PLACEHOLDER_RE = re.compile(r"<bild (\d+)(?:, [^:<>]+)?: [^<>]*>")


def output_dir(source: Path) -> Path:
    return source.parent / f"{FOLDER_PREFIX}{source.stem}"


def package_path(source: Path) -> Path:
    return output_dir(source) / f"{source.stem}{SUFFIX}"


def text_path(package: Path) -> Path:
    return package.with_suffix(".txt")


def work_dir(package: Path) -> Path:
    """Fester Arbeitsordner je .pdfforblinds-Datei."""
    base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "pdfforblinds" / "Arbeitsordner"
    key = hashlib.sha1(str(package.resolve()).lower().encode()).hexdigest()[:8]
    return base / f"{package.stem}-{key}"


def pack(folder: Path, package: Path) -> None:
    package.parent.mkdir(parents=True, exist_ok=True)
    tmp = package.with_name(package.name + ".tmp")
    with zipfile.ZipFile(tmp, "w") as bundle:
        for path in sorted(folder.rglob("*")):
            name = path.relative_to(folder).as_posix()
            if path.is_file() and name.startswith(PACKED):
                compress = zipfile.ZIP_STORED if path.suffix == ".png" else zipfile.ZIP_DEFLATED
                bundle.write(path, name, compress_type=compress)
    tmp.replace(package)


def unpack(package: Path, folder: Path) -> None:
    """Paket in den Arbeitsordner entpacken. Seitenbilder einer laufenden Umwandlung bleiben."""
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package) as bundle:
        for member in bundle.infolist():
            name = member.filename.replace("\\", "/")
            if member.is_dir() or not name.startswith(PACKED) or ".." in name.split("/"):
                continue
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.read(member))


def full_text(folder: Path) -> str:
    """Das komplette Dokument: <seite>-Markierungen, beschriebene Bilder mit ihrer Beschreibung."""
    data = json.loads((folder / "project.json").read_text(encoding="utf-8"))
    parts = []
    for page in data["seiten"]:
        images = {img["nr"]: img for img in page["bilder"]}

        def repl(m):
            img = images.get(int(m.group(1)))
            if not img or not img.get("beschreibung"):
                return m.group(0)
            kind = kind_text(img.get("typ"), img.get("typ_sicherheit"))
            head = f"<bild {img['nr']}, {kind}>" if kind else f"<bild {img['nr']}>"
            focus = f"Fokus: {img['beschreibung_fokus']}\n" if img.get("beschreibung_fokus") else ""
            return f"{head}\n{focus}{img['beschreibung']}\n</bild>"

        text = PLACEHOLDER_RE.sub(repl, (folder / page["text"]).read_text(encoding="utf-8"))
        parts.append(f"<seite>{page['nr']}</seite>\n{text}")
    return "\n".join(parts)


def export(folder: Path, package: Path) -> None:
    """Paket und Textdatei neben der Quelle aktualisieren."""
    pack(folder, package)
    target = text_path(package)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(full_text(folder), encoding="utf-8")
    tmp.replace(target)


class Exporter:
    """Während der Umwandlung höchstens alle `interval` Sekunden exportieren (große Bücher)."""

    def __init__(self, folder: Path, package: Path, interval: float = 20):
        self.folder, self.package, self.interval = folder, package, interval
        self.last = 0.0

    def maybe(self):
        if time.time() - self.last >= self.interval:
            self.now()

    def now(self):
        export(self.folder, self.package)
        self.last = time.time()
