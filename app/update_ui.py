"""Updates der Exe: Prüfung beim Start, Rückfrage, Austausch beim Beenden (aus Konzeptheft/CodeCockpit).

Die Prüfung läuft bei jedem Start still im Hintergrund, nur in der Exe. Nur wenn es eine neue
Version gibt, kommt eine Rückfrage. Hilfe, Nach Updates suchen prüft sofort und meldet auch
„aktuell“ und Fehler. Nach dem Download schließt sich das Programm auf Wunsch nur; die neue
Version wird beim Beenden übernommen und danach selbst gestartet (kein automatischer Neustart,
Lösung aus dem CodeCockpit).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app import APP_NAME, update
from app.tasks import Task

if TYPE_CHECKING:
    from app.main_window import MainWindow

log = logging.getLogger(__name__)

FIRST_CHECK_MS = 10_000                  # nach dem Start, damit das Fenster erst in Ruhe aufbaut
RETRY_MS = 60_000                        # Rückfrage verschieben, solange ein Dialog offen ist
TITLE = "Update"
CHECK_KEY = "update/check_at_start"
SKIPPED_KEY = "update/skipped"

UPDATE, NOTES, SKIP, LATER = "update", "notes", "skip", "later"


class Updater(QObject):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.window = window
        self.settings = window.settings
        self.task: Task | None = None
        self.waiting: update.Update | None = None     # heruntergeladen, Austausch beim Beenden
        self.exe_path = update.own_exe()

    @property
    def check_at_start(self) -> bool:
        return str(self.settings.value(CHECK_KEY, "true")).lower() == "true"

    @check_at_start.setter
    def check_at_start(self, value: bool) -> None:
        self.settings.setValue(CHECK_KEY, "true" if value else "false")

    def start(self) -> None:
        """Nur in der Exe: alte Versionen aufräumen, dann still prüfen."""
        if self.exe_path is None:
            return
        try:
            for folder in update.prune_versions(self.exe_path):
                log.info("Alte Version in die Sicherheitskopien: %s", folder)
        except OSError as exc:
            log.warning("Alte Versionen nicht aufgeräumt: %s", exc)
        if self.check_at_start:
            QTimer.singleShot(FIRST_CHECK_MS, lambda: self.run(manual=False))

    # -- Prüfen -----------------------------------------------------------------------------
    def check_now(self) -> None:
        """Hilfe, Nach Updates suchen."""
        if self.exe_path is None:
            QMessageBox.information(self.window, TITLE, f"Updates gibt es nur für die Exe. Sie haben "
                                    f"{APP_NAME} aus dem Code gestartet. Neuerungen holen Sie dort mit Git.")
            return
        if self.waiting is not None:
            self.offer_close(self.waiting)
            return
        self.window.announce("Suche nach Updates.")
        self.run(manual=True)

    def run(self, manual: bool) -> None:
        if self.task is not None or self.waiting is not None:
            return
        skipped = "" if manual else str(self.settings.value(SKIPPED_KEY, ""))
        exe_path = self.exe_path
        self._start_task(lambda task: update.check(exe_path, skipped),
                         lambda found: self.found(found, manual),
                         "Nach Updates suchen" if manual else None)

    def _start_task(self, work, done, failed_title: str | None) -> None:
        task = Task(work, self)
        self.task = task

        def finished() -> None:
            self.task = None

        def failed(message: str, details: str) -> None:
            log.warning("Update: %s %s", message, details)
            if failed_title is not None:
                QMessageBox.warning(self.window, failed_title, message)

        task.result.connect(done)
        task.error.connect(failed)
        task.finished.connect(finished)
        task.start()

    def found(self, found: update.Update | None, manual: bool) -> None:
        if found is None:
            if manual:
                QMessageBox.information(self.window, TITLE, f"{APP_NAME} ist aktuell.")
            return
        if not manual and QApplication.activeModalWidget() is not None:
            QTimer.singleShot(RETRY_MS, lambda: self.found(found, manual))
            return
        self.ask(found)

    # -- Rückfrage --------------------------------------------------------------------------
    def ask(self, found: update.Update) -> None:
        while True:
            answer = ask_update(self.window, found)
            if answer != NOTES:
                break
            QMessageBox.information(self.window, f"Versionshinweise {found.version}", found.notes)
        if answer == SKIP:
            self.settings.setValue(SKIPPED_KEY, found.tag)
            self.window.announce(f"Version {found.version} wird übersprungen.")
        elif answer == UPDATE:
            self.download(found)

    def download(self, found: update.Update) -> None:
        exe_path = self.exe_path
        self.window.announce("Update wird heruntergeladen.")
        self._start_task(lambda task: update.download(found, exe_path, task.cancel_event),
                         lambda _path: self.downloaded(found), "Update herunterladen")

    def downloaded(self, found: update.Update) -> None:
        self.waiting = found
        self.offer_close(found)

    def offer_close(self, found: update.Update) -> None:
        """Lösung aus dem CodeCockpit (20.10.2026): kein Neustart. Das Programm schließt sich nur,
        beim Beenden wird die neue Version übernommen, danach startet man sie selbst."""
        home = update.fixed_home(self.exe_path) if self.exe_path is not None else None
        where = f" aus dem Ordner {home.parent.name}\\{home.name}" if home is not None else ""
        box = QMessageBox(QMessageBox.Icon.Question, TITLE,
                          f"Version {found.version} ist heruntergeladen und geprüft. Zum Übernehmen "
                          f"schließen Sie {APP_NAME} und starten es danach selbst wieder{where}. "
                          "Dann läuft die neue Version. Jetzt schließen?",
                          QMessageBox.StandardButton.NoButton, self.window)
        close = box.addButton("Programm &schließen", QMessageBox.ButtonRole.AcceptRole)
        later = box.addButton("&Später", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(later)
        box.setEscapeButton(later)
        box.exec()
        if box.clickedButton() is not close:
            self.window.announce("Das Update wird beim Beenden übernommen.")
            return
        self.window.close()                       # shutdown() übernimmt das Update

    # -- Austausch --------------------------------------------------------------------------
    def shutdown(self) -> None:
        """Beim Beenden: laufende Prüfung abbrechen, wartendes Update übernehmen."""
        if self.task is not None:
            self.task.cancel()
            self.task.wait(5000)
        if self.waiting is None or self.exe_path is None or not update.is_waiting(self.exe_path):
            return
        try:
            script = update.swap(self.exe_path, self.waiting.version)
        except (update.UpdateError, OSError) as exc:
            log.warning("Update-Austausch: %s", exc)
            return
        self.waiting = None
        update.launch(script)


def ask_update(parent, found: update.Update) -> str:
    """Rückfrage mit Aktualisieren, Versionshinweise, Überspringen und Später (Vorgabe)."""
    box = QMessageBox(QMessageBox.Icon.Question, "Update verfügbar",
                      f"Version {found.version} von {APP_NAME} ist verfügbar ({found.size_text}). "
                      "Ihre Projekte und Einstellungen bleiben erhalten. Die bisherige Exe kommt in "
                      "die Sicherheitskopien. Jetzt aktualisieren?",
                      QMessageBox.StandardButton.NoButton, parent)
    buttons = {box.addButton("&Aktualisieren", QMessageBox.ButtonRole.AcceptRole): UPDATE}
    if found.notes.strip():
        buttons[box.addButton("&Versionshinweise", QMessageBox.ButtonRole.ActionRole)] = NOTES
    buttons[box.addButton("Diese Version ü&berspringen", QMessageBox.ButtonRole.DestructiveRole)] = SKIP
    later = box.addButton("&Später", QMessageBox.ButtonRole.RejectRole)
    buttons[later] = LATER
    box.setDefaultButton(later)
    box.setEscapeButton(later)
    box.exec()
    return buttons.get(box.clickedButton(), LATER)
