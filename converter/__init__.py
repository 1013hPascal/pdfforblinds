"""Wandelt PDFs und Fotos in einen seitenweisen, für Blinde lesbaren Projektordner um."""

import sys

# PyMuPDF 2.0 lädt beim Import das Zusatzmodul pymupdf.layout mit einem ONNX-Modell (gut 3 s).
# Es dient nur page.find_tables(), das hier nicht genutzt wird. In der Exe fehlten seine Dateien,
# und der Start brach ab. Mit None meldet Python ImportError, den PyMuPDF selbst abfängt.
sys.modules.setdefault("pymupdf.layout", None)
