"""Hauptfenster: Seitenliste, Seitentext und Bildbeschreibung, komplett per Tastatur bedienbar."""

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QProcess, QProcessEnvironment, QSettings, Qt, Signal
from PySide6.QtGui import (QAccessible, QAccessibleAnnouncementEvent, QAction,
                           QKeySequence, QTextCursor)
from PySide6.QtWidgets import (QFileDialog, QInputDialog, QLineEdit, QMainWindow, QMessageBox,
                               QPlainTextEdit, QSplitter, QStackedWidget,
                               QTreeWidget, QTreeWidgetItem)

from converter import package as pkg

from . import APP_NAME
from .describer import MODEL, Describer
from .project_model import PLACEHOLDER_RE, ImageInfo, PageInfo, Project
from .start_page import StartPage, add_recent
from .update_ui import Updater

ROOT = Path(__file__).resolve().parent.parent
CONVERTER_DIR_KEY = "converter_dir"   # in der Exe: Programmordner mit Python-Umgebung und Modellen
IMAGE_SUFFIXES = "*.pdf *.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp"

HELP_TEXT = """Startseite:
Alt+A: PDF oder Foto auswählen
Alt+Z: zuletzt geöffnete Dateien zeigen (Enter öffnet, Entf entfernt aus der Liste)

Seitenliste:
Pfeil hoch/runter: Seite wählen
Pfeil rechts/links: Bilder der Seite auf-/zuklappen
Enter auf einer Seite: Seitentext öffnen
Enter auf einem Bild: Beschreibung öffnen, oder erstellen lassen, wenn noch keine da ist

Seitentext:
Enter oder Klick auf einen Bild-Platzhalter: Beschreibung öffnen oder erstellen lassen
Strg+Tab: zwischen Seitentext und Bildbeschreibung wechseln
Strg+Bild ab / Strg+Bild auf: nächste / vorige Seite
Escape: zurück (Bildbeschreibung schließen, dann zur Seitenliste)

Menü Bilder (Alt+B):
Bilder für das gesamte Dokument umsetzen
Alle Bilder der aktuellen Seite umsetzen
Strg+R: neue Bildbeschreibung für das aktuelle Bild, mit Frage, worauf der Fokus liegen soll

Überall:
Strg+O: PDF, Foto oder .pdfforblinds öffnen (neben der PDF entsteht der Ordner "pdfforblinds Name")
Strg+W: Projekt schließen, zurück zur Startseite
F1: diese Hilfe"""


class TextView(QPlainTextEdit):
    """Schreibgeschütztes Textfeld mit Tastatur-Cursor, damit Screenreader zeilenweise lesen können."""

    escape = Signal()
    activated = Signal(int)   # Cursorposition bei Enter oder Klick
    switch = Signal()         # Strg+Tab

    def __init__(self, name: str):
        super().__init__()
        self.setReadOnly(True)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByKeyboard | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setAccessibleName(name)

    def event(self, e):
        if e.type() == QEvent.Type.KeyPress and e.modifiers() & Qt.KeyboardModifier.ControlModifier \
                and e.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.switch.emit()
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.escape.emit()
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.activated.emit(self.textCursor().position())
        else:
            super().keyPressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if e.button() == Qt.MouseButton.LeftButton and not self.textCursor().hasSelection():
            self.activated.emit(self.textCursor().position())

    def set_text_keep_cursor(self, text: str):
        pos = self.textCursor().position()
        self.setPlainText(text)
        cursor = self.textCursor()
        cursor.setPosition(min(pos, len(text)))
        self.setTextCursor(cursor)


class MainWindow(QMainWindow):
    def __init__(self, project_folder: Path | None = None):
        super().__init__()
        self.project: Project | None = None
        self.current_page: PageInfo | None = None
        self.current_image: ImageInfo | None = None   # Bild im Beschreibungsfeld
        self.settings = QSettings("pdfforblinds", "viewer")
        self.converter: QProcess | None = None

        self.describer = Describer()
        self.describer.started.connect(self._on_describe_started)
        self.describer.finished.connect(self._on_describe_finished)
        self.describer.failed.connect(self._on_describe_failed)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName("Seitenliste")
        self.tree.itemActivated.connect(self._on_item_activated)

        self.text = TextView("Seitentext")
        self.text.escape.connect(self.back_to_list)
        self.text.activated.connect(self._on_text_activated)
        self.text.switch.connect(self._switch_from_text)

        self.desc = TextView("Bildbeschreibung")
        self.desc.escape.connect(self.close_description)
        self.desc.switch.connect(self.text.setFocus)
        self.desc.hide()

        self.reader = QSplitter(Qt.Orientation.Horizontal)
        self.reader.addWidget(self.text)
        self.reader.addWidget(self.desc)

        self.start = StartPage(self.settings)
        self.start.choose.connect(self.choose_source)
        self.start.open_file.connect(self.open_path)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.start)
        self.stack.addWidget(self.tree)
        self.stack.addWidget(self.reader)
        self.setCentralWidget(self.stack)

        font = self.font()
        font.setPointSize(14)
        self.setFont(font)
        self.resize(1200, 800)
        self.updater = Updater(self)
        self._build_menu()
        self.statusBar()

        # Wie im Konzeptheft: Start ohne offenes Projekt (nur ein Ordner aus der Befehlszeile wird geöffnet)
        self.show_start()
        if project_folder:
            self.open_path(Path(project_folder))
        self.updater.start()

    # ---------------------------------------------------------------- Menü
    def _build_menu(self):
        def action(menu, text, shortcut, slot):
            act = QAction(text, self)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(slot)
            menu.addAction(act)
            return act

        datei = self.menuBar().addMenu("&Datei")
        action(datei, "PDF, Foto oder Projekt &öffnen …", "Ctrl+O", self.choose_source)
        action(datei, "Projekt &schließen", "Ctrl+W", self.close_project)
        datei.addSeparator()
        action(datei, "&Beenden", "Ctrl+Q", self.close)

        # Alt+B. Die Einträge erscheinen nur, wo sie passen; ihre Kürzel wirken trotzdem immer.
        bilder = self.menuBar().addMenu("&Bilder")
        self.act_all = action(bilder, "Bilder für gesamtes &Dokument umsetzen", None, self.describe_document)
        self.act_page = action(bilder, "Alle Bilder für &Seite umsetzen", None, self.describe_page)
        self.act_new = action(bilder, "&Neue Bildbeschreibung für Bild …", "Ctrl+R", self.new_description)
        bilder.aboutToShow.connect(self._update_image_menu)
        bilder.aboutToHide.connect(lambda: [a.setVisible(True) for a in bilder.actions()])

        seite = self.menuBar().addMenu("&Seite")
        action(seite, "&Nächste Seite", "Ctrl+PgDown", lambda: self.step_page(1))
        action(seite, "&Vorige Seite", "Ctrl+PgUp", lambda: self.step_page(-1))
        action(seite, "Zur Seiten&liste", "Ctrl+L", self.back_to_list)

        hilfe = self.menuBar().addMenu("&Hilfe")
        action(hilfe, "&Tastenkürzel", "F1", lambda: QMessageBox.information(self, "Tastenkürzel", HELP_TEXT))
        hilfe.addSeparator()
        action(hilfe, "Nach &Updates suchen", None, self.updater.check_now)
        check = action(hilfe, "Beim Start nach Updates s&uchen", None, lambda on: setattr(
            self.updater, "check_at_start", on))
        check.setCheckable(True)
        check.setChecked(self.updater.check_at_start)

    def _update_image_menu(self):
        page = self._context_page()
        image = self._context_image()
        self.act_all.setVisible(self.project is not None)
        self.act_page.setVisible(page is not None)
        if page is not None:
            self.act_page.setText(f"Alle Bilder für &Seite {page.number} umsetzen")
        self.act_new.setVisible(image is not None)
        if not any(a.isVisible() for a in (self.act_all, self.act_page, self.act_new)):
            self.act_all.setVisible(True)        # leeres Menü vermeiden; meldet "kein Projekt"

    # ---------------------------------------------------------- Ansagen
    def announce(self, message: str):
        self.statusBar().showMessage(message)
        QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(self, message))

    # ----------------------------------------------------------- Projekt
    def show_start(self):
        self.start.refresh()
        self.stack.setCurrentWidget(self.start)
        self.setWindowTitle(APP_NAME)
        self.start.focus_start()
        self.announce("Kein Projekt geöffnet. Alt+A wählt eine PDF oder ein Foto, Alt+Z zeigt die zuletzt "
                      "geöffneten Dateien.")

    def close_project(self):
        if self.project is None:
            return
        self.close_description(focus_text=False)
        self.project = self.current_page = None
        self.tree.clear()
        self.show_start()

    def show_project(self, project: Project):
        self.project = project
        self.current_page = None
        add_recent(self.settings, project.recent_entry)
        self.setWindowTitle(f"{self.project.title} – {APP_NAME}")
        self._fill_tree()
        self.back_to_list()
        self.announce(f"{self.project.title} geöffnet, {len(self.project.pages)} Seiten.")

    def open_path(self, path: Path):
        """PDF, Foto, .pdfforblinds oder (alter) Projektordner."""
        if path.is_dir() and (path / "project.json").exists():
            self.show_project(Project(path))
        elif path.suffix.lower() == pkg.SUFFIX:
            self.open_package(path)
        else:
            self.open_source(path)

    def open_source(self, source: Path):
        """PDF oder Foto öffnen: die .pdfforblinds daneben öffnen, sonst umwandeln."""
        if not source.exists():
            QMessageBox.warning(self, "Datei nicht gefunden", f"{source} gibt es nicht mehr.")
            return
        package = pkg.package_path(source.resolve())
        if package.exists():
            self.open_package(package)
        else:
            self.convert(source)

    def open_package(self, package: Path):
        if not package.exists():
            QMessageBox.warning(self, "Datei nicht gefunden", f"{package} gibt es nicht mehr.")
            return
        try:
            project = Project.from_package(package)
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.warning(self, "Datei beschädigt", f"{package.name} lässt sich nicht öffnen: {exc}")
            return
        if not project.is_complete and project.source.exists():
            done, total = len(project.pages), project.data.get("seitenzahl", 0)
            answer = QMessageBox.question(
                self, "Umwandlung unvollständig",
                f"Von {project.source.name} sind erst {done} von {total} Seiten umgewandelt. Umwandlung "
                "fortsetzen? Mit Nein öffnen Sie die fertigen Seiten.")
            if answer == QMessageBox.StandardButton.Yes:
                self.convert(project.source, package)
                return
        self.show_project(project)

    def _fill_tree(self):
        self.tree.clear()
        for page in self.project.pages:
            item = QTreeWidgetItem([self._page_label(page)])
            item.setData(0, Qt.ItemDataRole.UserRole, ("page", page.number))
            for image in page.images:
                child = QTreeWidgetItem([self._image_label(image)])
                child.setData(0, Qt.ItemDataRole.UserRole, ("image", page.number, image.number))
                item.addChild(child)
            self.tree.addTopLevelItem(item)
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _page_label(self, page: PageInfo) -> str:
        first_line = next((line.strip() for line in page.text().splitlines() if line.strip()), "")
        if PLACEHOLDER_RE.fullmatch(first_line):
            first_line = ""
        label = f"Seite {page.number}"
        if page.images:
            described = sum(img.described for img in page.images)
            label += f", {len(page.images)} {'Bild' if len(page.images) == 1 else 'Bilder'}, {described} beschrieben"
        if first_line:
            label += f": {first_line[:70]}"
        return label

    def _image_label(self, image: ImageInfo) -> str:
        if image.described:
            status = "Beschreibung vorhanden"
        elif self.describer.is_pending(image):
            status = "Beschreibung wird erstellt"
        else:
            status = "keine Beschreibung"
        kind = f", {image.kind_label}" if image.kind else ""
        label = f"Bild {image.number}{kind}: {status}"
        if image.caption:
            label += f", {image.caption[:70]}"
        return label

    def _refresh_tree_for(self, image: ImageInfo):
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole)[1] != image.page:
                continue
            item.setText(0, self._page_label(self.project.page(image.page)))
            for j in range(item.childCount()):
                child = item.child(j)
                if child.data(0, Qt.ItemDataRole.UserRole)[2] == image.number:
                    child.setText(0, self._image_label(image))

    # ------------------------------------------------------- Navigation
    def _on_item_activated(self, item: QTreeWidgetItem):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data[0] == "page":
            self.open_page(data[1])
        else:
            page = self.project.page(data[1])
            self.activate_image(page, page.image(data[2]), open_page=True)

    def open_page(self, number: int):
        page = self.project.page(number)
        if page is None:
            return
        self.current_page = page
        self.close_description(focus_text=False)
        self.text.setAccessibleName(f"Seitentext Seite {number}")
        self.text.setPlainText(page.text())
        self.text.moveCursor(QTextCursor.MoveOperation.Start)
        self.stack.setCurrentWidget(self.reader)
        self.text.setFocus()
        self.setWindowTitle(f"Seite {number} – {self.project.title}")

    def step_page(self, delta: int):
        if self.project is None or self.current_page is None or self.stack.currentWidget() is not self.reader:
            return
        numbers = [p.number for p in self.project.pages]
        index = numbers.index(self.current_page.number) + delta
        if 0 <= index < len(numbers):
            self.open_page(numbers[index])
        else:
            self.announce("Erste Seite." if delta < 0 else "Letzte Seite.")

    def back_to_list(self):
        if self.project is None:
            return
        self.close_description(focus_text=False)
        self.stack.setCurrentWidget(self.tree)
        self.setWindowTitle(f"{self.project.title} – {APP_NAME}")
        if self.current_page is not None:
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                if item.data(0, Qt.ItemDataRole.UserRole)[1] == self.current_page.number:
                    self.tree.setCurrentItem(item)
        self.tree.setFocus()

    # ---------------------------------------------------- Bilder
    def _on_text_activated(self, position: int):
        block = self.text.document().findBlock(position)
        column = position - block.position()
        for m in PLACEHOLDER_RE.finditer(block.text()):
            if m.start() <= column <= m.end():
                image = self.current_page.image(int(m.group(1)))
                if image:
                    self.activate_image(self.current_page, image, open_page=False)
                return

    def activate_image(self, page: PageInfo, image: ImageInfo, open_page: bool):
        if image.described:
            if open_page:
                self.open_page(page.number)
                self._place_text_cursor_at(image.number)
            self.show_description(image)
        elif self.describer.is_pending(image):
            self.announce(f"Die Beschreibung für Bild {image.number} wird gerade erstellt.")
        else:
            self.describer.request(image, page)
            self._refresh_tree_for(image)
            self.announce(f"Beschreibung für Seite {page.number}, Bild {image.number} wird erstellt. "
                          "Das dauert etwa eine Minute.")

    def _place_text_cursor_at(self, number: int):
        m = next((m for m in PLACEHOLDER_RE.finditer(self.text.toPlainText()) if int(m.group(1)) == number), None)
        if m:
            cursor = self.text.textCursor()
            cursor.setPosition(m.start())
            self.text.setTextCursor(cursor)

    def show_description(self, image: ImageInfo):
        self.current_image = image
        self.desc.setAccessibleName(f"Bildbeschreibung Seite {image.page}, Bild {image.number}")
        text = image.description
        if image.focus:
            text = f"Fokus: {image.focus}\n{text}"
        if image.caption:
            text = f"Bildunterschrift: {image.caption}\n{text}"
        self.desc.setPlainText(text)
        self.desc.moveCursor(QTextCursor.MoveOperation.Start)
        self.desc.show()
        self.desc.setFocus()

    def close_description(self, focus_text: bool = True):
        was_open = self.desc.isVisible()
        self.desc.hide()
        self.current_image = None
        if focus_text and was_open:
            self.text.setFocus()

    def _switch_from_text(self):
        if self.desc.isVisible():
            self.desc.setFocus()
        else:
            self.announce("Keine Bildbeschreibung geöffnet. Enter auf einem Bild-Platzhalter öffnet eine.")

    # ------------------------------------------------ Menü Bilder
    def _context_page(self) -> PageInfo | None:
        """Die Seite, auf der man gerade ist: im Seitentext oder in der Seitenliste ausgewählt."""
        if self.project is None:
            return None
        if self.stack.currentWidget() is self.reader:
            return self.current_page
        if self.stack.currentWidget() is self.tree and self.tree.currentItem():
            return self.project.page(self.tree.currentItem().data(0, Qt.ItemDataRole.UserRole)[1])
        return None

    def _context_image(self) -> ImageInfo | None:
        """Das Bild in der geöffneten Bildbeschreibung oder das in der Seitenliste ausgewählte Bild."""
        if self.project is None:
            return None
        if self.stack.currentWidget() is self.reader and self.desc.isVisible():
            return self.current_image
        if self.stack.currentWidget() is self.tree and self.tree.currentItem():
            data = self.tree.currentItem().data(0, Qt.ItemDataRole.UserRole)
            if data[0] == "image":
                return self.project.page(data[1]).image(data[2])
        return None

    def _describe_missing(self, pages: list[PageInfo]) -> int:
        """Alle Bilder ohne Beschreibung in die Warteschlange. Gibt die Anzahl neuer Aufträge zurück."""
        count = 0
        for page in pages:
            for image in page.images:
                if not image.described and self.describer.request(image, page):
                    self._refresh_tree_for(image)
                    count += 1
        return count

    def describe_document(self):
        if self.project is None:
            self.announce("Kein Projekt geöffnet.")
            return
        self._announce_queued(self._describe_missing(self.project.pages), "im Dokument")

    def describe_page(self):
        page = self._context_page()
        if page is None:
            self.announce("Keine Seite ausgewählt.")
            return
        self._announce_queued(self._describe_missing([page]), f"auf Seite {page.number}")

    def _announce_queued(self, count: int, where: str):
        if count == 0:
            self.announce(f"Alle Bilder {where} haben schon eine Beschreibung oder werden gerade beschrieben.")
            return
        waiting = self.describer.waiting()
        self.announce(f"{count} {'Bild' if count == 1 else 'Bilder'} {where} werden beschrieben, "
                      f"etwa eine Minute pro Bild. Insgesamt warten {waiting}.")

    def new_description(self):
        """Neue Beschreibung für das aktuelle Bild, auf Wunsch mit einer Frage als Schwerpunkt."""
        image = self._context_image()
        if image is None:
            self.announce("Kein Bild ausgewählt. Öffnen Sie zuerst eine Bildbeschreibung.")
            return
        if self.describer.is_pending(image):
            self.announce("Diese Beschreibung wird gerade schon erstellt.")
            return
        focus, ok = QInputDialog.getText(
            self, "Neue Bildbeschreibung",
            "Was willst du wissen, worauf soll der Fokus sein? (leer lassen für eine allgemeine Beschreibung)",
            QLineEdit.EchoMode.Normal, "")
        if not ok:
            return
        page = self.project.page(image.page)
        self.describer.request(image, page, focus.strip())
        self._refresh_tree_for(image)
        self.announce(f"Neue Beschreibung für Seite {image.page}, Bild {image.number} wird erstellt.")

    def _on_describe_started(self, image: ImageInfo):
        self.statusBar().showMessage(f"Erstelle Beschreibung für Seite {image.page}, Bild {image.number} …")

    def _belongs_to_project(self, image: ImageInfo) -> bool:
        """False, wenn das Projekt des Bildes inzwischen geschlossen wurde."""
        page = self.project.page(image.page) if self.project is not None else None
        return page is not None and page.image(image.number) is image

    def _on_describe_finished(self, image: ImageInfo, text: str, focus: str):
        if not self._belongs_to_project(image):
            return
        self.project.set_description(image, text, MODEL, focus)
        self._refresh_tree_for(image)
        if self.current_page is not None and self.current_page.number == image.page \
                and self.stack.currentWidget() is self.reader:
            self.text.set_text_keep_cursor(self.current_page.text())
            if self.current_image is image:
                self.show_description(image)
        self.announce(f"Beschreibung für Seite {image.page}, Bild {image.number} ist fertig.")

    def _on_describe_failed(self, image: ImageInfo, message: str):
        if not self._belongs_to_project(image):
            return
        self._refresh_tree_for(image)
        self.announce(f"Beschreibung für Seite {image.page}, Bild {image.number} fehlgeschlagen: {message}")

    # ------------------------------------------------ Umwandeln
    def choose_source(self):
        if self.converter is not None:
            self.announce("Es läuft bereits eine Umwandlung.")
            return
        start = str(self.settings.value("last_dir", "", type=str))
        file, _ = QFileDialog.getOpenFileName(self, "PDF oder Foto auswählen", start,
                                              f"PDF, Bilder und Projekte ({IMAGE_SUFFIXES} *{pkg.SUFFIX})")
        if file:
            self.settings.setValue("last_dir", str(Path(file).parent))
            self.open_path(Path(file))

    def convert(self, source: Path, package: Path | None = None):
        """Umwandeln. Der Ordner 'pdfforblinds <Name>' neben der Quelle entsteht sofort."""
        if self.converter is not None:
            self.announce("Es läuft bereits eine Umwandlung.")
            return
        command = self._converter_command()
        if command is None:
            return
        python, code_dir = command
        package = package or pkg.package_path(source.resolve())
        try:
            package.parent.mkdir(exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Ablage nicht möglich",
                                f"Neben {source.name} lässt sich der Ordner {package.parent.name} nicht "
                                f"anlegen: {exc}")
            return
        add_recent(self.settings, source)
        if self.stack.currentWidget() is self.start:
            self.start.refresh()
        self.converter = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        for key in env.keys():            # Variablen von PyInstaller nicht an Python weitergeben
            if key.upper().startswith(("_PYI_", "_MEIPASS")):
                env.remove(key)
        env.insert("PYTHONUTF8", "1")
        self.converter.setProcessEnvironment(env)
        self.converter.setWorkingDirectory(str(code_dir))
        self.converter.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.converter.readyReadStandardOutput.connect(self._on_converter_output)
        self.converter.finished.connect(lambda code, _status: self._on_converter_finished(code, package))
        self.converter.start(str(python), ["-m", "converter", str(source), "--paket", str(package)])
        self.announce(f"Umwandlung von {source.name} gestartet, Ablage im Ordner {package.parent.name}. "
                      "Das kann pro Seite bis zu einer Minute dauern.")

    @staticmethod
    def _python_in(folder: Path) -> Path | None:
        """Python der Umwandlung: .venv im Programmordner, sonst die Entwicklungsumgebung ocr_test\\.venv
        (wie in start_app.bat)."""
        if not (folder / "converter" / "__main__.py").is_file():
            return None
        for python in (folder / ".venv" / "Scripts" / "python.exe",
                       folder.parent.parent / "ocr_test" / ".venv" / "Scripts" / "python.exe"):
            if python.is_file():
                return python
        return None

    def _converter_command(self) -> tuple[Path, Path] | None:
        """(Python, Programmordner) für die Umwandlung. Aus dem Code: dieses Python. In der Exe stecken
        PyTorch, Docling und die Modelle nicht (über 10 GB); dort wird einmal nach dem Programmordner
        mit Python-Umgebung und Modellen gefragt."""
        if not getattr(sys, "frozen", False):
            return Path(sys.executable), ROOT
        saved = self.settings.value(CONVERTER_DIR_KEY, "", type=str)
        if saved and (python := self._python_in(Path(saved))):
            return python, Path(saved)
        QMessageBox.information(
            self, "Programmordner für die Umwandlung",
            "Zum Umwandeln braucht die Exe den Programmordner mit Python-Umgebung und Modellen, "
            "zum Beispiel repository\\main (darin liegen die Ordner converter und modelle). "
            "Bitte wählen Sie ihn im nächsten Dialog aus. Das ist nur einmal nötig.")
        folder = QFileDialog.getExistingDirectory(self, "Programmordner für die Umwandlung wählen", saved)
        if not folder:
            return None
        python = self._python_in(Path(folder))
        if python is None:
            QMessageBox.warning(self, "Ordner passt nicht",
                                f"In {folder} fehlt der Ordner converter oder die Python-Umgebung .venv. "
                                "Siehe README, Abschnitt Installation.")
            return None
        self.settings.setValue(CONVERTER_DIR_KEY, folder)
        return python, Path(folder)

    def _on_converter_output(self):
        output = bytes(self.converter.readAllStandardOutput()).decode("utf-8", errors="replace")
        for line in output.splitlines():
            if line.strip().startswith("Seite ") and "Rest ca." in line:
                self.statusBar().showMessage(f"Umwandlung: {line.strip()}")

    def _on_converter_finished(self, code: int, package: Path):
        self.converter = None
        if code == 0 and package.exists():
            self.announce("Umwandlung fertig.")
            self.open_package(package)
        else:
            self.announce(f"Umwandlung fehlgeschlagen (Code {code}).")

    def closeEvent(self, e):
        self.updater.shutdown()
        self.describer.stop()
        if self.converter is not None:
            self.converter.kill()
        super().closeEvent(e)
