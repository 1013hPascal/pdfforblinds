"""Zentrale Pfade und Schwellwerte des Konverters."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Modelle liegen in "modelle" neben dem Code (nicht im Git), oder dort, wohin PDFFORBLINDS_MODELLE zeigt.
MODELS_DIR = Path(os.environ.get("PDFFORBLINDS_MODELLE") or ROOT / "modelle")
UNLIMITED_MODEL_DIR = MODELS_DIR / "unlimited-ocr"
DOCLING_ARTIFACTS_DIR = MODELS_DIR / "docling"

# Auflösung, mit der Seiten für die OCR und als Vorschau gerendert werden.
RENDER_DPI = 200

# Auflösung, mit der Bilder aus der PDF ausgeschnitten werden (für Bildbeschreibungen).
IMAGE_DPI = 400

# Weiche: ab wann eine Seite an Unlimited-OCR geht.
MIN_TEXT_CHARS = 50          # weniger Zeichen in der Textebene -> Scan
SCAN_IMAGE_COVERAGE = 0.8    # ein Bild bedeckt mehr als 80 % der Seite -> Scan
BROKEN_TEXT_RATIO = 0.02     # Anteil unlesbarer Zeichen -> kaputte Textebene
MATH_FONT_CHARS = 10         # Zeichen in Mathe-Schriften
MATH_UNICODE_CHARS = 10      # Zeichen aus dem Unicode-Block "Mathematical Alphanumeric Symbols"
SCRIPT_SPANS = 3             # hoch-/tiefgestellte Textstücke (gehen bei Docling verloren)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
