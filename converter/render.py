"""Blöcke -> Seitentext im Stil der Blinden-Fassungen.

Mathe als $…$, Tabellen als <tabelle> mit <anmerkung>, Bilder als Platzhalter
<bild N: keine Beschreibung>, keine Schriftformatierung.
"""

import re

from .blocks import (CAPTION, DROP, FOOTNOTE, FORMULA, HEADING, IMAGE,
                     LIST_ITEM, TABLE, TEXT, Block)

_INLINE_RE = re.compile(r"\\\(\s*(.*?)\s*\\\)", re.DOTALL)
_DISPLAY_RE = re.compile(r"\\\[\s*(.*?)\s*\\\]", re.DOTALL)
_SPACES_RE = re.compile(r"[ \t]+")


def image_placeholder(number: int, described: bool = False, kind: str = "") -> str:
    status = "Beschreibung vorhanden" if described else "keine Beschreibung"
    kind = f", {kind}" if kind else ""
    return f"<bild {number}{kind}: {status}>"


def math_to_dollar(text: str) -> str:
    text = _DISPLAY_RE.sub(lambda m: "$$" + " ".join(m.group(1).split()) + "$$", text)
    text = _INLINE_RE.sub(lambda m: "$" + " ".join(m.group(1).split()) + "$", text)
    return _SPACES_RE.sub(" ", text)


def table_cell(text: str) -> str:
    """Ein & im Zellentext wird wie in LaTeX zu \\&, damit es nicht als Spaltentrenner gilt."""
    text = math_to_dollar(text).replace("\n", " ").strip()
    return re.sub(r"(?<!\\)&", r"\\&", text)


def render_table(rows: list[list[str]]) -> str:
    rows = [[table_cell(cell) for cell in row] for row in rows]
    columns = max((len(row) for row in rows), default=0)
    lines = [
        f"<anmerkung> Die nachfolgende Tabelle besitzt {len(rows)} Zeilen und {columns} Spalten. </anmerkung>",
        "<tabelle>",
        *(" & ".join(row) for row in rows),
        "</tabelle>",
    ]
    return "\n".join(lines)


def render_page(blocks: list[Block], kinds: list[str] | None = None) -> str:
    """kinds: Bildart je Bild in Reihenfolge, z. B. ["Zeichnung", "vermutlich Foto"]."""
    out: list[str] = []
    image_no = 0
    for block in blocks:
        if block.type == DROP:
            continue
        if block.type == IMAGE:
            image_no += 1
            kind = kinds[image_no - 1] if kinds and image_no <= len(kinds) else ""
            out.append(image_placeholder(image_no, kind=kind))
        elif block.type == TABLE:
            if block.rows:
                out.append(render_table(block.rows))
        elif block.type == FOOTNOTE:
            out.append(f"<fußnote> {math_to_dollar(block.content).strip()} </fußnote>")
        elif block.type == FORMULA:
            text = math_to_dollar(block.content).strip()
            if "$" not in text:
                text = f"$${text}$$"
            out.append(text)
        elif block.type == HEADING:
            if out:
                out.append("")
            out.append(math_to_dollar(block.content).strip())
        elif block.type in (TEXT, LIST_ITEM, CAPTION):
            out.append(math_to_dollar(block.content).strip())
    return "\n".join(out).strip() + "\n"
