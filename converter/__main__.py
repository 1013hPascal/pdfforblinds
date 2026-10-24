"""Aufruf: python -m converter <pdf|bild> [--paket datei.pdfforblinds | -o ordner] [--force-ocr] [--pages 1-5]

Standard: neben der Quelle entsteht sofort der Ordner "pdfforblinds <Name>" mit <Name>.pdfforblinds
und <Name>.txt; beide werden während der Umwandlung laufend aktualisiert.
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from . import config
from .analyze import DOCLING, UNLIMITED, Decision, decide
from .package import Exporter, package_path, unpack, work_dir
from .project import Project

DOCLING_CHUNK = 5   # Docling in kleinen Stücken, damit die Seiten im Programm früh erscheinen


def chunks(pages: list[int], size: int) -> list[list[int]]:
    """Aufeinanderfolgende Seiten in Stücke von höchstens size Seiten teilen."""
    result: list[list[int]] = []
    for nr in pages:
        if result and nr == result[-1][-1] + 1 and len(result[-1]) < size:
            result[-1].append(nr)
        else:
            result.append([nr])
    return result


def parse_range(spec: str | None, count: int) -> list[int]:
    if not spec:
        return list(range(1, count + 1))
    pages = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            pages.update(range(int(a), int(b) + 1))
        else:
            pages.add(int(part))
    return sorted(p for p in pages if 1 <= p <= count)


def fmt_duration(seconds: float) -> str:
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{sec:02d}" if hours else f"{minutes}:{sec:02d}"


def prepare(source: Path, project: Project, pages_spec: str | None, force_ocr: bool) -> dict[int, Decision]:
    """Rendert die Seitenbilder und entscheidet pro Seite über die Engine."""
    if source.suffix.lower() in config.IMAGE_SUFFIXES:
        project.set_page_count(1)
        render = project.render_path(1)
        if not render.exists():
            with Image.open(source) as img:
                ImageOps.exif_transpose(img).convert("RGB").save(render)
        return {1: Decision(UNLIMITED, "Foto")}

    doc = pymupdf.open(source)
    project.set_page_count(len(doc))
    decisions = {}
    for nr in parse_range(pages_spec, len(doc)):
        page = doc[nr - 1]
        render = project.render_path(nr)
        if not render.exists():
            page.get_pixmap(dpi=config.RENDER_DPI).save(render)
        decisions[nr] = decide(page, force_ocr)
    doc.close()
    return decisions


def main():
    parser = argparse.ArgumentParser(description="PDF oder Foto in einen Projektordner für Blinde umwandeln.")
    parser.add_argument("source", type=Path, help="PDF-Datei oder Foto (JPG/PNG)")
    parser.add_argument("--paket", type=Path,
                        help="Ziel-.pdfforblinds (Standard: neben der Quelle in 'pdfforblinds <Name>')")
    parser.add_argument("-o", "--output", type=Path,
                        help="nur einen Projektordner schreiben, ohne .pdfforblinds (für Tests)")
    parser.add_argument("--force-ocr", action="store_true", help="alle Seiten mit Unlimited-OCR erkennen")
    parser.add_argument("--pages", help="nur diese Seiten, z. B. 1-5 oder 2,4,7")
    parser.add_argument("--dry-run", action="store_true", help="nur anzeigen, welche Engine jede Seite bekäme")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)   # das Programm liest den Fortschritt zeilenweise mit

    source = args.source.resolve()
    if not source.exists():
        sys.exit(f"Datei nicht gefunden: {source}")
    exporter = None
    if args.output:
        folder = args.output
    else:
        package = (args.paket or package_path(source)).resolve()
        folder = work_dir(package)
        if package.exists() and not (folder / "project.json").exists():
            unpack(package, folder)          # Fortsetzen auf einem anderen Rechner oder nach Aufräumen
        exporter = Exporter(folder, package)
    project = Project(folder, source)
    if exporter:
        exporter.now()                       # Ordner und Dateien neben der Quelle gleich anlegen
        print(f"Ablage: {exporter.package}")

    decisions = prepare(source, project, args.pages, args.force_ocr)
    pending = {nr: d for nr, d in decisions.items() if not project.is_done(nr)}
    done = len(decisions) - len(pending)
    print(f"{source.name}: {len(decisions)} Seiten, {done} schon fertig, {len(pending)} offen")
    for nr, d in sorted(pending.items()):
        print(f"  Seite {nr}: {d.engine} ({d.reason})")
    if args.dry_run:
        return
    # Maschinenlesbare Zeilen für das Programm: @stand fertig/gesamt, @seite nr fertig/gesamt
    print(f"@stand {done}/{len(decisions)}")

    def saved(nr: int):
        nonlocal done
        done += 1
        print(f"@seite {nr} {done}/{len(decisions)}")
        if exporter:
            exporter.maybe()

    try:
        docling_pages = sorted(nr for nr, d in pending.items() if d.engine == DOCLING)
        if docling_pages:
            from .engine_docling import DoclingEngine

            t0 = time.time()
            print(f"\nDocling: {len(docling_pages)} Seiten …")
            engine = DoclingEngine()
            for chunk in chunks(docling_pages, DOCLING_CHUNK):
                results = engine.convert(source, chunk[0], chunk[-1])
                for nr in chunk:
                    project.save_page(nr, DOCLING, pending[nr].reason, results.get(nr, []))
                    saved(nr)
            print(f"Docling fertig in {fmt_duration(time.time() - t0)}")

        ocr_pages = sorted(nr for nr, d in pending.items() if d.engine == UNLIMITED)
        if ocr_pages:
            from .engine_unlimited import DEVICE, UnlimitedEngine

            print(f"\nUnlimited-OCR: {len(ocr_pages)} Seiten, lade Modell ({DEVICE}) …")
            engine = UnlimitedEngine()
            t_start = time.time()
            for i, nr in enumerate(ocr_pages, 1):
                t0 = time.time()
                blocks = engine.recognize(project.render_path(nr))
                project.save_page(nr, UNLIMITED, pending[nr].reason, blocks)
                saved(nr)
                remaining = (time.time() - t_start) / i * (len(ocr_pages) - i)
                print(f"  Seite {nr} ({i}/{len(ocr_pages)}): {time.time() - t0:.0f} s, "
                      f"Rest ca. {fmt_duration(remaining)}")
    except KeyboardInterrupt:
        if exporter:
            exporter.now()
        sys.exit("\nAbgebrochen. Erneut starten, um bei der nächsten Seite fortzusetzen.")

    if exporter:
        exporter.now()
        if project.is_complete():
            shutil.rmtree(folder / "renders", ignore_errors=True)   # nur für die Erkennung nötig
    print(f"\nFertig: {exporter.package if exporter else folder}")


if __name__ == "__main__":
    main()
