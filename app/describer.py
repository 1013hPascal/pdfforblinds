"""Bildbeschreibungen mit Gemma 4 über Ollama, nacheinander in einem Hintergrund-Thread."""

import base64
import json
import os
import queue
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from converter.vectors import extract

from .project_model import ImageInfo, PageInfo

OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = "gemma4:12b"
OLLAMA_EXE_CANDIDATES = [
    shutil.which("ollama"),
    str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"),
]

PROMPT = """Du beschreibst Bilder aus Lern- und Fachdokumenten für blinde Leserinnen und Leser.
Antworte auf Deutsch und nur in genau diesem Format, ohne Markdown (keine Sternchen, keine Aufzählungszeichen, keine Überschriften):
Typ: <Art des Bildes, z. B. Funktionsgraph, Vektordiagramm, Tabelle, Foto, Skizze>
x-Achse: <Beschriftung und Skala; Zeile weglassen, wenn es keine Achsen gibt>
y-Achse: <Beschriftung und Skala; Zeile weglassen, wenn es keine Achsen gibt>
Beschreibung: <sachliche, vollständige Beschreibung aller Elemente, Beschriftungen, Werte und Koordinaten>

Regeln:
- Mathematik als LaTeX in $...$.
- Koordinaten und Werte so genau angeben, wie sie im Bild ablesbar sind. Nichts erfinden: wenn ein Wert unsicher ist, schreibe "etwa" oder "nicht lesbar".
- Keine Einleitung, keine Bewertung, nichts über das Bild Hinausgehende.

{kind}{focus}{vectors}Zum Verständnis folgt der Text der Seite {page}. Das zu beschreibende Bild ist dort der Platzhalter <bild {number}>.{caption}

{page_text}"""

VECTOR_HINT = """Zu diesem Bild liegen exakt aus der PDF-Datei gemessene Zeichnungsdaten vor:
{data}

Diese Werte haben Vorrang vor deiner eigenen Schätzung aus dem Bild: Übernimm Koordinaten, Beschriftungen und Texte aus diesen Daten. Beschreibe aber mit eigenen Worten, was dargestellt ist, statt die Liste nur abzuschreiben. Die Daten zeigen, was gezeichnet ist. Ist die Zeichnung erkennbar nur eine ungenaue Skizze (z. B. weil der Seitentext andere exakte Werte nennt), gib die gezeichneten Werte mit "etwa" an und weise kurz darauf hin.

"""

KIND_HINT = "Eine automatische Einordnung hält das Bild für: {kind}. Prüfe das selbst.\n\n"

FOCUS_HINT = """Die Leserin oder der Leser möchte zu diesem Bild besonders wissen: „{focus}“
Lege den Schwerpunkt der Beschreibung darauf und beantworte diese Frage ausdrücklich, soweit das Bild es hergibt. Halte dabei das Format oben ein.

"""


def ollama_running() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2)
        return True
    except (urllib.error.URLError, OSError):
        return False


def ensure_ollama() -> None:
    if ollama_running():
        return
    exe = next((c for c in OLLAMA_EXE_CANDIDATES if c and Path(c).exists()), None)
    if exe is None:
        raise RuntimeError("Ollama wurde nicht gefunden.")
    subprocess.Popen(
        [exe, "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    for _ in range(40):
        time.sleep(0.5)
        if ollama_running():
            return
    raise RuntimeError("Ollama konnte nicht gestartet werden.")


def clean(text: str) -> str:
    text = text.replace("**", "")
    text = re.sub(r"^\s*[*\-•]\s+", "", text, flags=re.MULTILINE)
    return text.strip()


def vector_data(image: ImageInfo) -> str | None:
    """Exakte Zeichnungsdaten aus der Original-PDF, falls das Bild eine Vektorgrafik ist."""
    if image.source is None or not image.bbox:
        return None
    try:
        return extract(image.source, image.page, image.bbox)
    except Exception:  # beschädigte oder verschobene PDF: Beschreibung nur aus dem Bild
        return None


def describe(image: ImageInfo, page: PageInfo, focus: str = "") -> str:
    """focus: was die Nutzerin oder der Nutzer besonders wissen will (leer: allgemeine Beschreibung)."""
    ensure_ollama()
    caption = f"\nBildunterschrift: {image.caption}" if image.caption else ""
    data = vector_data(image)
    vectors = VECTOR_HINT.format(data=data) if data else ""
    kind = KIND_HINT.format(kind=image.kind_label) if image.kind else ""
    focus = FOCUS_HINT.format(focus=focus.strip()) if focus.strip() else ""
    prompt = PROMPT.format(page=page.number, number=image.number, caption=caption, kind=kind,
                           focus=focus, vectors=vectors, page_text=page.text())
    body = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "images": [base64.b64encode(image.path.read_bytes()).decode()],
        "stream": False,
        "think": False,
        "keep_alive": "15m",
        "options": {"num_ctx": 8192, "temperature": 0.2},
    }).encode()
    request = urllib.request.Request(f"{OLLAMA_URL}/api/generate", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=900) as resp:
        result = json.load(resp)
    text = clean(result.get("response", ""))
    if not text:
        raise RuntimeError("Das Modell hat keine Beschreibung geliefert.")
    return text


class _Loop(QThread):
    def __init__(self, target):
        super().__init__()
        self._target = target

    def run(self):
        self._target()


class Describer(QObject):
    """Nimmt Aufträge entgegen und arbeitet sie nacheinander in einem eigenen Thread ab."""

    started = Signal(object)          # ImageInfo
    finished = Signal(object, str, str)    # ImageInfo, Beschreibung, Fokus
    failed = Signal(object, str)      # ImageInfo, Fehlermeldung

    def __init__(self):
        super().__init__()
        self._queue: queue.Queue = queue.Queue()
        self._pending: set[tuple[int, int]] = set()
        self._thread = _Loop(self._run)
        self._thread.start()

    def is_pending(self, image: ImageInfo) -> bool:
        return (image.page, image.number) in self._pending

    def request(self, image: ImageInfo, page: PageInfo, focus: str = "") -> bool:
        """Gibt False zurück, wenn das Bild schon in Arbeit ist."""
        key = (image.page, image.number)
        if key in self._pending:
            return False
        self._pending.add(key)
        self._queue.put((image, page, focus))
        return True

    def waiting(self) -> int:
        """Anzahl der Bilder, die noch auf ihre Beschreibung warten (auch das laufende)."""
        return len(self._pending)

    def stop(self):
        self._queue.put(None)
        if not self._thread.wait(2000):
            # Eine Beschreibung läuft noch (HTTP-Anfrage an Ollama): beim Beenden hart abbrechen.
            self._thread.terminate()
            self._thread.wait()

    def _run(self):
        while True:
            job = self._queue.get()
            if job is None:
                return
            image, page, focus = job
            self.started.emit(image)
            try:
                text = describe(image, page, focus)
            except Exception as exc:  # Netzwerk, Ollama, Modell
                self._pending.discard((image.page, image.number))
                self.failed.emit(image, str(exc))
                continue
            self._pending.discard((image.page, image.number))
            self.finished.emit(image, text, focus)
