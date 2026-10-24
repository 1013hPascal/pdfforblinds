"""Seitenanalyse ohne KI: entscheidet pro Seite, welche Engine sie bekommt."""

import re
from dataclasses import dataclass

import pymupdf

from . import config

UNLIMITED = "unlimited"
DOCLING = "docling"

MATH_FONT_RE = re.compile(r"CMMI|CMSY|CMEX|MSAM|MSBM|Math|STIX|Symbol", re.IGNORECASE)


@dataclass
class Decision:
    engine: str
    reason: str


def _is_broken(ch: str) -> bool:
    return ch == "�" or 0xE000 <= ord(ch) <= 0xF8FF


def _image_coverage(page: pymupdf.Page) -> float:
    page_area = abs(page.rect)
    if not page_area:
        return 0.0
    largest = 0.0
    for info in page.get_image_info():
        rect = pymupdf.Rect(info["bbox"]) & page.rect
        largest = max(largest, abs(rect))
    return largest / page_area


def decide(page: pymupdf.Page, force_ocr: bool = False) -> Decision:
    if force_ocr:
        return Decision(UNLIMITED, "OCR erzwungen")

    text = page.get_text()
    chars = [c for c in text if not c.isspace()]
    if len(chars) < config.MIN_TEXT_CHARS:
        return Decision(UNLIMITED, f"kaum Text in der PDF ({len(chars)} Zeichen), vermutlich Scan")

    coverage = _image_coverage(page)
    if coverage > config.SCAN_IMAGE_COVERAGE:
        return Decision(UNLIMITED, f"Bild bedeckt {coverage:.0%} der Seite, vermutlich Scan")

    broken = sum(1 for c in chars if _is_broken(c))
    if broken / len(chars) > config.BROKEN_TEXT_RATIO:
        return Decision(UNLIMITED, f"Textebene beschädigt ({broken} unlesbare Zeichen)")

    math_unicode = sum(1 for c in chars if 0x1D400 <= ord(c) <= 0x1D7FF)
    math_font_chars = 0
    script_spans = 0
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if not span["text"].strip():
                    continue
                if MATH_FONT_RE.search(span["font"]):
                    math_font_chars += len(span["text"].strip())
                if span["flags"] & pymupdf.TEXT_FONT_SUPERSCRIPT:
                    script_spans += 1

    if math_font_chars > config.MATH_FONT_CHARS:
        return Decision(UNLIMITED, f"Mathe-Schriften ({math_font_chars} Zeichen)")
    if math_unicode > config.MATH_UNICODE_CHARS:
        return Decision(UNLIMITED, f"Mathe-Zeichen ({math_unicode})")
    if script_spans >= config.SCRIPT_SPANS:
        return Decision(UNLIMITED, f"Hochstellungen ({script_spans})")

    return Decision(DOCLING, "normaler Text")
