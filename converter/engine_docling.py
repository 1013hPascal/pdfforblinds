"""Docling (IBM): liest die Textebene der PDF und erkennt das Layout. Eigene OCR ist aus."""

import re
import unicodedata
import warnings
from pathlib import Path

from .blocks import (CAPTION, DROP, FOOTNOTE, FORMULA, HEADING, IMAGE,
                     LIST_ITEM, TABLE, TEXT, Block)
from . import config

LABEL_MAP = {
    "title": HEADING,
    "section_header": HEADING,
    "text": TEXT,
    "paragraph": TEXT,
    "code": TEXT,
    "reference": TEXT,
    "list_item": LIST_ITEM,
    "formula": FORMULA,
    "table": TABLE,
    "document_index": TABLE,
    "picture": IMAGE,
    "chart": IMAGE,
    "caption": CAPTION,
    "footnote": FOOTNOTE,
    "page_header": DROP,
    "page_footer": DROP,
}

# Alte LaTeX-PDFs speichern Umlaute als Akzent + Buchstabe ("¨U" statt "Ü").
_ACCENTS = {"¨": "̈", "´": "́", "`": "̀", "ˆ": "̂", "˜": "̃", "˚": "̊"}
_ACCENT_RE = re.compile("([" + "".join(_ACCENTS) + "])([A-Za-z])")


def fix_text(text: str) -> str:
    text = _ACCENT_RE.sub(lambda m: m.group(2) + _ACCENTS[m.group(1)], text)
    return unicodedata.normalize("NFC", text)


class DoclingEngine:
    name = "docling"

    def __init__(self):
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        warnings.filterwarnings("ignore")
        options = PdfPipelineOptions(artifacts_path=str(config.DOCLING_ARTIFACTS_DIR))
        options.do_ocr = False
        options.do_table_structure = True
        options.generate_picture_images = True
        options.images_scale = 2.0
        self.converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )

    def convert(self, pdf_path: Path, first: int, last: int) -> dict[int, list[Block]]:
        """Wandelt den Seitenbereich first..last um und liefert Blöcke pro Seitennummer."""
        doc = self.converter.convert(str(pdf_path), page_range=(first, last)).document
        result: dict[int, list[Block]] = {}
        for page_no, page in doc.pages.items():
            result[page_no] = [
                block for item, _ in doc.iterate_items(page_no=page_no)
                if (block := self._to_block(item, doc, page.size)) is not None
            ]
        return result

    def _to_block(self, item, doc, page_size) -> Block | None:
        label = getattr(item, "label", None)
        if label is None:
            return None
        block_type = LABEL_MAP.get(label.value)
        if block_type is None or block_type == DROP:
            return None

        bbox = None
        if getattr(item, "prov", None):
            box = item.prov[0].bbox.to_top_left_origin(page_size.height).normalized(page_size)
            bbox = (box.l, box.t, box.r, box.b)

        if block_type == TABLE and getattr(item, "data", None) is not None:
            rows = [[fix_text(cell.text) for cell in row] for row in item.data.grid]
            return Block(type=TABLE, rows=rows, bbox=bbox)
        if block_type == IMAGE:
            image = item.get_image(doc)
            if image is None:
                return None
            return Block(type=IMAGE, image=image, bbox=bbox)

        text = fix_text(getattr(item, "text", "") or "")
        if block_type == FORMULA and not text:
            text = "[Formel nicht erkannt]"
        if not text:
            return None
        marker = getattr(item, "marker", "")
        if block_type == LIST_ITEM and marker and marker not in ("-", "•", "·"):
            text = f"{marker} {text}"
        return Block(type=block_type, content=text, bbox=bbox)
