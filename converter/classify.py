"""Bildart erkennen (Diagramm, Foto, Zeichnung …) mit dem Bildklassifizierer von Docling (IBM).

Kleines EfficientNet-Modell (16 MB), etwa 50 ms pro Bild auf der CPU.
"""

from functools import lru_cache

from PIL import Image

from . import config

LABELS_DE = {
    "logo": "Logo",
    "photograph": "Foto",
    "icon": "Symbol",
    "engineering_drawing": "Zeichnung",
    "line_chart": "Liniendiagramm",
    "bar_chart": "Balkendiagramm",
    "other": "sonstiges Bild",
    "table": "Tabelle",
    "flow_chart": "Flussdiagramm",
    "screenshot_from_computer": "Bildschirmfoto",
    "signature": "Unterschrift",
    "screenshot_from_manual": "Bildschirmfoto",
    "geographical_map": "Landkarte",
    "pie_chart": "Kreisdiagramm",
    "page_thumbnail": "Seitenvorschau",
    "stamp": "Stempel",
    "music": "Noten",
    "calendar": "Kalender",
    "qr_code": "QR-Code",
    "bar_code": "Strichcode",
    "full_page_image": "ganzseitiges Bild",
    "scatter_plot": "Streudiagramm",
    "chemistry_structure": "Strukturformel",
    "topographical_map": "topografische Karte",
    "crossword_puzzle": "Kreuzworträtsel",
    "box_plot": "Boxplot",
}

# Unter dieser Sicherheit heißt es "vermutlich …"
SURE = 0.5


@lru_cache(maxsize=1)
def _model():
    import warnings

    from transformers import AutoImageProcessor, AutoModelForImageClassification
    from transformers.utils import logging as hf_logging

    hf_logging.set_verbosity_error()
    warnings.filterwarnings("ignore")
    folder = config.DOCLING_ARTIFACTS_DIR / "docling-project--DocumentFigureClassifier-v2.5"
    processor = AutoImageProcessor.from_pretrained(folder)
    model = AutoModelForImageClassification.from_pretrained(folder).eval()
    return processor, model


def classify(image: Image.Image) -> tuple[str, float]:
    """Gibt die Bildart auf Deutsch und die Sicherheit (0..1) zurück."""
    import torch

    processor, model = _model()
    with torch.no_grad():
        logits = model(**processor(image.convert("RGB"), return_tensors="pt")).logits
    probs = logits.softmax(-1)[0]
    index = int(probs.argmax())
    label = model.config.id2label[index]
    return LABELS_DE.get(label, label), float(probs[index])


def kind_text(kind: str | None, certainty: float | None) -> str:
    """Bildart für die Anzeige, mit "vermutlich", wenn das Modell unsicher war."""
    if not kind:
        return ""
    return kind if certainty is None or certainty >= SURE else f"vermutlich {kind}"
