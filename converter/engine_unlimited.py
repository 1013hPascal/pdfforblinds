"""Unlimited-OCR (baidu) auf einer NVIDIA-GPU (CUDA), der Intel-GPU (XPU) oder notfalls der CPU.

Der Modellcode ruft fest .cuda() und torch.autocast("cuda") auf. Ohne NVIDIA-GPU
wird beides auf das verfügbare Gerät umgeleitet, ohne die Modelldateien zu ändern.
"""

import html
import re
import tempfile
import warnings
from html.parser import HTMLParser
from pathlib import Path

import torch
from PIL import Image

from . import config
from .blocks import (CAPTION, DROP, FOOTNOTE, FORMULA, HEADING, IMAGE, TABLE,
                     TEXT, Block)

if torch.cuda.is_available():
    DEVICE = "cuda"
elif hasattr(torch, "xpu") and torch.xpu.is_available():
    DEVICE = "xpu"
else:
    DEVICE = "cpu"

# --- CUDA -> DEVICE umleiten (nur ohne NVIDIA-GPU) ---------------------------
if DEVICE != "cuda":
    torch.Tensor.cuda = lambda self, *a, **k: self.to(DEVICE)
    _orig_autocast = torch.autocast

    class _Autocast(_orig_autocast):
        def __init__(self, device_type, *args, **kwargs):
            super().__init__(DEVICE if device_type == "cuda" else device_type, *args, **kwargs)

    torch.autocast = _Autocast
# -----------------------------------------------------------------------------

DET_RE = re.compile(r"<\|det\|>\s*([A-Za-z_][\w-]*)\s*(\[[^\]]*\])?\s*<\|/det\|>")

TYPE_MAP = {
    "title": HEADING,
    "sub_title": HEADING,
    "section_header": HEADING,
    "text": TEXT,
    "equation": FORMULA,
    "interline_equation": FORMULA,
    "table": TABLE,
    "image": IMAGE,
    "figure": IMAGE,
    "image_caption": CAPTION,
    "table_caption": CAPTION,
    "figure_caption": CAPTION,
    "table_footnote": FOOTNOTE,
    "footnote": FOOTNOTE,
    "page_footnote": FOOTNOTE,
    "header": DROP,
    "footer": DROP,
    "page_header": DROP,
    "page_footer": DROP,
    "page_number": DROP,
}


class _TableParser(HTMLParser):
    """Liest <table><tr><td>…</td></tr></table> in eine Liste von Zeilen."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            if not self.rows:
                self.rows.append([])
            self.rows[-1].append("".join(self._cell).strip())
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_table(markup: str) -> list[list[str]]:
    parser = _TableParser()
    parser.feed(markup)
    return [row for row in parser.rows if row]


def _bbox(box: str | None) -> tuple[float, float, float, float] | None:
    if not box:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in box.strip("[]").split(",")[:4])
    except ValueError:
        return None
    return (x1 / 999, y1 / 999, x2 / 999, y2 / 999)


def parse_output(raw: str, page_image: Image.Image) -> list[Block]:
    """Zerlegt die Modellausgabe an den <|det|>-Markierungen in Blöcke."""
    blocks = []
    matches = list(DET_RE.finditer(raw))
    width, height = page_image.size
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        content = raw[m.end():end].strip()
        label = m.group(1).lower()
        bbox = _bbox(m.group(2))
        block_type = TYPE_MAP.get(label, TEXT)
        block = Block(type=block_type, content=content, bbox=bbox, extra={"label": label})

        if block_type == TABLE:
            if "<table" in content:
                block.rows = parse_table(content)
            else:
                block.type = TEXT
        elif block_type == IMAGE:
            if bbox is None:
                continue
            x1, y1, x2, y2 = bbox
            crop = (int(x1 * width), int(y1 * height), int(x2 * width), int(y2 * height))
            if crop[2] - crop[0] < 5 or crop[3] - crop[1] < 5:
                continue
            block.image = page_image.crop(crop)
        elif not content:
            continue
        else:
            block.content = html.unescape(content)
        blocks.append(block)
    return blocks


class UnlimitedEngine:
    name = "unlimited"

    def __init__(self):
        from transformers import AutoModel, AutoTokenizer
        from transformers.utils import logging as hf_logging

        hf_logging.set_verbosity_error()
        warnings.filterwarnings("ignore")
        model_dir = str(config.UNLIMITED_MODEL_DIR)
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
        model = AutoModel.from_pretrained(
            model_dir,
            trust_remote_code=True,
            use_safetensors=True,
            dtype=torch.bfloat16,
            _attn_implementation="eager",
        )
        self.model = model.eval().to(DEVICE)
        self._tmp = tempfile.TemporaryDirectory(prefix="unlimited_")

    def recognize(self, image_path: Path) -> list[Block]:
        raw = self.model.infer(
            self.tokenizer,
            prompt="<image>document parsing.",
            image_file=str(image_path),
            output_path=self._tmp.name,
            base_size=1024, image_size=640, crop_mode=True,
            max_length=32768,
            no_repeat_ngram_size=35, ngram_window=128,
            eval_mode=True,
        )
        with Image.open(image_path) as img:
            page_image = img.convert("RGB")
        return parse_output(raw or "", page_image)
