"""Bilder in hoher Qualität ausschneiden: direkt aus der PDF bzw. dem Originalfoto."""

from functools import lru_cache
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from . import config

# Kleiner Rand um die erkannte Bildposition, damit nichts abgeschnitten wird
MARGIN = 0.005


@lru_cache(maxsize=2)
def _open_pdf(path: str) -> pymupdf.Document:
    return pymupdf.open(path)


def _padded(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = bbox
    return (max(0.0, x1 - MARGIN), max(0.0, y1 - MARGIN), min(1.0, x2 + MARGIN), min(1.0, y2 + MARGIN))


def crop_hires(source: Path, page_nr: int, bbox, dpi: int = config.IMAGE_DPI) -> Image.Image | None:
    """Schneidet den Bereich bbox (Anteile 0..1, oben links) in hoher Auflösung aus.

    PDF: der Bereich wird mit `dpi` neu gerendert (Vektorgrafiken bleiben scharf).
    Foto: Ausschnitt aus dem Original in voller Auflösung.
    """
    if not bbox:
        return None
    x1, y1, x2, y2 = _padded(bbox)
    if source.suffix.lower() in config.IMAGE_SUFFIXES:
        with Image.open(source) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            w, h = img.size
            return img.crop((int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)))

    page = _open_pdf(str(source))[page_nr - 1]
    r = page.rect
    clip = pymupdf.Rect(r.x0 + x1 * r.width, r.y0 + y1 * r.height, r.x0 + x2 * r.width, r.y0 + y2 * r.height)
    if clip.is_empty:
        return None
    pix = page.get_pixmap(clip=clip, dpi=dpi)
    return Image.frombytes("RGB" if pix.n < 4 else "RGBA", (pix.width, pix.height), pix.samples).convert("RGB")
