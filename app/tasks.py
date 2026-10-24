"""Arbeit im Hintergrund-Thread mit Ergebnis-Signalen (für Update-Prüfung und Download)."""

import threading

from PySide6.QtCore import QThread, Signal


class Task(QThread):
    result = Signal(object)
    error = Signal(str, str)      # Text für den Nutzer, Details

    def __init__(self, work, parent=None):
        super().__init__(parent)
        self._work = work
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            value = self._work(self)
        except Exception as exc:
            self.error.emit(getattr(exc, "message", str(exc)), getattr(exc, "details", repr(exc)))
            return
        self.result.emit(value)
