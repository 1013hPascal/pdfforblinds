"""Vergleicht ein umgewandeltes Dokument mit einer von Hand erstellten Blinden-Fassung.

Aufruf: python tools/compare.py <datei.pdfforblinds | projektordner> <blindenfassung.doc|.docx|.txt> [--show 2]

Beide Texte werden pro <seite> verglichen. Vor dem Vergleich werden Tags,
Leerzeichen, $-Zeichen und Groß-/Kleinschreibung entfernt, damit nur der Inhalt zählt.
"""

import argparse
import difflib
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from converter import package as pkg  # noqa: E402

PAGE_RE = re.compile(r"<seite>\s*(\d+)\s*</seite>")
TAG_RE = re.compile(r"<[^<>]{1,40}>")


def read_reference(path: Path) -> str:
    if path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")
    import win32com.client  # pywin32

    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(str(path.resolve()), False, True)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ref.txt"
            # 7 = wdFormatUnicodeText, 65001 = UTF-8
            doc.SaveAs2(str(out), 7, False, "", False, "", False, False, False, False, False, 65001)
            doc.Close(False)
            return out.read_text(encoding="utf-8-sig", errors="replace")
    finally:
        word.Quit()


def split_pages(text: str) -> dict[int, str]:
    parts = PAGE_RE.split(text)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def normalize(text: str) -> str:
    text = TAG_RE.sub("", text)
    text = re.sub(r"[\s$]", "", text)
    return text.lower()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--show", type=int, help="Unterschiede dieser Seite zeilenweise anzeigen")
    args = parser.parse_args()

    if args.project.is_file():
        with tempfile.TemporaryDirectory() as tmp:
            pkg.unpack(args.project, Path(tmp))
            ours = split_pages(pkg.full_text(Path(tmp)))
    else:
        ours = split_pages(pkg.full_text(args.project))
    ref = split_pages(read_reference(args.reference))

    total_ours = total_ref = ""
    print("Seite  Ähnlichkeit")
    for nr in sorted(set(ours) | set(ref)):
        a, b = normalize(ours.get(nr, "")), normalize(ref.get(nr, ""))
        total_ours += a
        total_ref += b
        ratio = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
        print(f"{nr:5d}  {ratio:6.1%}")
    ratio = difflib.SequenceMatcher(None, total_ours, total_ref, autojunk=False).ratio()
    print(f"gesamt {ratio:6.1%}")

    if args.show:
        diff = difflib.unified_diff(
            ref.get(args.show, "").splitlines(), ours.get(args.show, "").splitlines(),
            "Blinden-Fassung", "Konverter", lineterm="", n=0,
        )
        print("\n".join(diff))


if __name__ == "__main__":
    main()
