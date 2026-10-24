"""Aufruf: python -m app [pdf | foto | datei.pdfforblinds]"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PDF für Blinde")
    folder = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    window = MainWindow(folder)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
