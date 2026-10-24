"""Schneidet die Bilder eines schon umgewandelten Projekts neu in hoher Qualität aus.

Die OCR wird nicht wiederholt: Die gespeicherten Bildpositionen aus project.json
werden direkt aus der Original-PDF (bzw. dem Originalfoto) neu gerendert.

Aufruf: python tools/recrop.py <datei.pdfforblinds | projektordner> [--dpi 400] [--source datei.pdf]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from converter import config  # noqa: E402
from converter import package as pkg  # noqa: E402
from converter.images import crop_hires  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", type=Path)
    parser.add_argument("--dpi", type=int, default=config.IMAGE_DPI)
    parser.add_argument("--source", type=Path, help="Originaldatei, falls sie inzwischen verschoben wurde")
    args = parser.parse_args()

    package = args.project if args.project.is_file() else None
    folder = args.project
    if package is not None:
        folder = pkg.work_dir(package)
        pkg.unpack(package, folder)
    data = json.loads((folder / "project.json").read_text(encoding="utf-8"))
    source = args.source or Path(data["quelle"])
    if not source.exists():
        sys.exit(f"Originaldatei nicht gefunden: {source}\nMit --source den neuen Ort angeben.")

    done = skipped = 0
    for page in data["seiten"]:
        for img in page["bilder"]:
            image = crop_hires(source, page["nr"], img.get("bbox"), dpi=args.dpi)
            if image is None:
                skipped += 1
                continue
            image.save(folder / img["datei"])
            print(f"Seite {page['nr']}, Bild {img['nr']}: {image.width} x {image.height} Pixel")
            done += 1
    if package is not None:
        pkg.export(folder, package)
    print(f"\n{done} Bilder neu ausgeschnitten, {skipped} ohne Position übersprungen.")


if __name__ == "__main__":
    main()
