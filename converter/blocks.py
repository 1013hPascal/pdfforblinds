"""Gemeinsames Zwischenformat, das beide Erkennungs-Engines liefern."""

from dataclasses import dataclass, field

from PIL import Image

# Erlaubte Blocktypen
HEADING = "heading"
TEXT = "text"
LIST_ITEM = "list_item"
FORMULA = "formula"
TABLE = "table"
IMAGE = "image"
CAPTION = "caption"
FOOTNOTE = "footnote"
DROP = "drop"  # Seitenzahl, Kopf-/Fußzeile: wird nicht ausgegeben


@dataclass
class Block:
    type: str
    content: str = ""
    # Tabellen: Zeilen mit Zellen (Text, Mathe bereits als LaTeX)
    rows: list[list[str]] | None = None
    # Bilder: ausgeschnittenes Bild
    image: Image.Image | None = None
    # Position auf der Seite, Anteile 0..1: (x1, y1, x2, y2), Ursprung oben links
    bbox: tuple[float, float, float, float] | None = None
    extra: dict = field(default_factory=dict)
