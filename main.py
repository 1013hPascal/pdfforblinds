"""PDF für Blinde starten: python main.py [pdf | foto | datei.pdfforblinds]

Optionen:
  --selbsttest  kurz starten und mit Code 0 beenden, ohne Rückfragen (zum Beispiel nach dem Bau der Exe)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QTimer, QTranslator
from PySide6.QtWidgets import QApplication

from app import APP_NAME, __version__
from app.main_window import MainWindow


def _german_qt(app: QApplication) -> QTranslator:
    """Deutsche Texte für Qt-eigene Schaltflächen und Dialoge (zum Beispiel "Abbrechen")."""
    translator = QTranslator(app)
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(QLocale(QLocale.Language.German), "qtbase", "_", folder):
        app.installTranslator(translator)
    return translator


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    self_test = "--selbsttest" in args
    files = [a for a in args if not a.startswith("--")]
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    _german_qt(app)
    window = MainWindow(Path(files[0]).resolve() if files and not self_test else None)
    window.show()
    if self_test:
        # Selbsttest: Fenster aufbauen, kurz laufen lassen, beenden (keine Update-Suche, kein Ollama)
        def finish() -> None:
            ok = window.isVisible()
            window.close()                # beendet den Thread für Bildbeschreibungen ordentlich
            app.exit(0 if ok else 1)
        QTimer.singleShot(1500, finish)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
