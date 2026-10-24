"""Startseite ohne offenes Projekt (wie im Konzeptheft): PDF auswählen und die zuletzt geöffneten Dateien."""

from pathlib import Path

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
                               QWidget)

RECENT_KEY = "recent_files"
MAX_RECENT = 50


def recent_files(settings: QSettings) -> list[Path]:
    value = settings.value(RECENT_KEY, [])
    if isinstance(value, str):            # QSettings liefert eine einzelne Zeichenkette statt Liste
        value = [value]
    return [Path(v) for v in value or []]


def add_recent(settings: QSettings, source: Path) -> None:
    """Datei nach vorne in die Liste, höchstens MAX_RECENT Einträge."""
    key = str(source.resolve()).lower()
    files = [source.resolve()] + [p for p in recent_files(settings) if str(p).lower() != key]
    settings.setValue(RECENT_KEY, [str(p) for p in files[:MAX_RECENT]])


def remove_recent(settings: QSettings, source: Path) -> None:
    key = str(source).lower()
    settings.setValue(RECENT_KEY, [str(p) for p in recent_files(settings) if str(p).lower() != key])


class RecentList(QListWidget):
    """Enter öffnet, Entf entfernt einen Eintrag aus der Liste (die Datei bleibt)."""

    chosen = Signal(object)              # Path
    removed = Signal(object)             # Path

    def keyPressEvent(self, e):
        item = self.currentItem()
        if item is not None and e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.chosen.emit(item.data(Qt.ItemDataRole.UserRole))
        elif item is not None and e.key() == Qt.Key.Key_Delete:
            self.removed.emit(item.data(Qt.ItemDataRole.UserRole))
        else:
            super().keyPressEvent(e)


class StartPage(QWidget):
    choose = Signal()                    # PDF auswählen …
    open_file = Signal(object)           # Path aus der Liste Zuletzt

    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings

        title = QLabel("Kein Projekt geöffnet")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = title.font()
        font.setPointSize(font.pointSize() + 6)
        title.setFont(font)

        self.choose_button = QPushButton("PDF oder Foto &auswählen …")
        self.choose_button.clicked.connect(self.choose)

        self.recent_button = QPushButton("&Zuletzt")
        self.recent_button.setCheckable(True)
        self.recent_button.setAccessibleDescription("Zeigt die zuletzt geöffneten Dateien")
        self.recent_button.toggled.connect(self._toggle_recent)

        self.recent = RecentList()
        self.recent.setAccessibleName("Zuletzt geöffnete Dateien")
        self.recent.itemDoubleClicked.connect(
            lambda item: self.open_file.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.recent.chosen.connect(self.open_file)
        self.recent.removed.connect(self._remove)
        self.recent.hide()
        self.empty = QLabel("Noch keine Dateien geöffnet.")
        self.empty.hide()

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(title)
        layout.addSpacing(20)
        layout.addWidget(self.choose_button)
        layout.addWidget(self.recent_button)
        layout.addWidget(self.empty)
        layout.addWidget(self.recent, 4)
        layout.addStretch(1)

    def refresh(self):
        self.recent.clear()
        for path in recent_files(self.settings):
            item = QListWidgetItem(f"{path.name} – {path.parent}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.recent.addItem(item)
        if self.recent.count():
            self.recent.setCurrentRow(0)
        self._toggle_recent(self.recent_button.isChecked(), focus=False)

    def focus_start(self):
        (self.recent if self.recent.isVisible() else self.choose_button).setFocus()

    def _toggle_recent(self, on: bool, focus: bool = True):
        has_files = self.recent.count() > 0
        self.recent.setVisible(on and has_files)
        self.empty.setVisible(on and not has_files)
        if on and has_files and focus:
            self.recent.setFocus()

    def _remove(self, path: Path):
        row = self.recent.currentRow()
        remove_recent(self.settings, path)
        self.refresh()
        if self.recent.count():
            self.recent.setCurrentRow(min(row, self.recent.count() - 1))
            self.recent.setFocus()
        else:
            self.recent_button.setFocus()
