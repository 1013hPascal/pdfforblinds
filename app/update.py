"""Selbst-Aktualisierung der Exe (übernommen aus Konzeptheft und CodeCockpit).

Quelle ist das neueste Release von 1013hPascal/pdfforblinds auf GitHub: eine Exe oder die
ZIP-Datei pdfforblinds.zip mit Exe, version.txt, README und Lizenz.

- Ein Update gibt es nur, wenn das Release eine höhere Versionsnummer hat als die laufende Exe
  (version.txt neben der Exe, sonst __version__) und eine andere Datei ist.
- Die neue Exe wird heruntergeladen, gegen die Prüfsumme (SHA-256) von GitHub geprüft und wartet
  im Ordner _neu. Nach dem Beenden tauscht ein kleines Skript sie aus. Es gibt keinen
  automatischen Neustart: Das Programm schließt sich nur, danach startet man es selbst
  (Lösung aus dem CodeCockpit).
- Fester Ordner wie im CodeCockpit: Läuft die Exe aus Release\\Name (oder einem alten
  Release\\Name-vX.Y.Z), kommt die neue Version immer nach Release\\Name. War die bisherige
  veröffentlicht (version.txt), heißt ihr Ordner danach Name-vX.Y.Z. Die letzten zwei alten
  Versionen bleiben daneben, ältere kommen in die Sicherheitskopien.
- Einstellungen und Projekte liegen nicht im Exe-Ordner und bleiben unberührt.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app import APP_NAME, __version__

OWNER, REPO = "1013hPascal", "pdfforblinds"
LATEST_URL = f"https://api.github.com/repos/{OWNER}/{REPO}/releases/latest"
ZIP_PREFIX = "pdfforblinds"               # nur pdfforblinds.zip, keine fremde ZIP-Datei
PENDING = "_neu"
VERSION_FILE = "version.txt"
BACKUP_FOLDER = "Sicherheitskopien"
KEEP_VERSIONS = 2
NO_CONNECTION = "Keine Verbindung zu GitHub. Bitte später erneut versuchen."
TIMEOUT = 20
FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_VERSION_HOME = re.compile(r"-v(\d+)\.(\d+)\.(\d+)$")


class UpdateError(Exception):
    """Fehler mit einfachem Text für den Nutzer und Details für das Log."""

    def __init__(self, message: str, details: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class Cancelled(Exception):
    """Der Nutzer hat abgebrochen."""


@dataclass
class Update:
    tag: str
    notes: str
    asset_name: str
    url: str
    size: int
    digest: str                           # SHA-256, klein geschrieben

    @property
    def version(self) -> str:
        return self.tag.lstrip("v")

    @property
    def is_zip(self) -> bool:
        return self.asset_name.lower().endswith(".zip")

    @property
    def size_text(self) -> str:
        return f"{max(1, round(self.size / (1024 * 1024)))} MB"


# -- Netz ---------------------------------------------------------------------------------------
def _request(url: str, accept: str = "application/vnd.github+json"):
    request = urllib.request.Request(url, headers={"Accept": accept,
                                                   "User-Agent": f"{REPO}/{__version__}"})
    return urllib.request.urlopen(request, timeout=TIMEOUT)


def fetch_json(url: str) -> dict | None:
    """JSON von GitHub, None bei 404 (noch kein Release oder Repository)."""
    try:
        with _request(url) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise UpdateError("GitHub hat die Anfrage nach Updates abgelehnt. Bitte später erneut "
                          "versuchen.", f"HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise UpdateError(NO_CONNECTION, repr(exc)) from None


def fetch_file(url: str, target: Path, cancel: threading.Event | None = None) -> str:
    """Datei laden, gibt ihre SHA-256 zurück."""
    digest = hashlib.sha256()
    try:
        with _request(url, "application/octet-stream") as response, open(target, "wb") as file:
            while chunk := response.read(256 * 1024):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                digest.update(chunk)
                file.write(chunk)
    except urllib.error.HTTPError as exc:
        raise UpdateError("Die neue Version ließ sich nicht herunterladen.",
                          f"HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError(NO_CONNECTION, repr(exc)) from None
    return digest.hexdigest()


# -- Prüfen -------------------------------------------------------------------------------------
def own_exe() -> Path | None:
    """Die laufende Exe, None beim Start aus dem Code."""
    return Path(sys.executable) if getattr(sys, "frozen", False) else None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", text.strip())
    return tuple(int(x) for x in match.groups()) if match else None


def own_version(exe_path: Path | None) -> tuple[int, int, int] | None:
    """Die höhere aus version.txt neben der Exe und __version__."""
    found = [v for v in (parse_version(__version__),) if v]
    if exe_path is not None:
        try:
            found += [v for v in (parse_version((exe_path.parent / VERSION_FILE).read_text(
                encoding="utf-8")),) if v]
        except OSError:
            pass
    return max(found) if found else None


def from_release(data: dict) -> Update | None:
    """Exe-Datei bevorzugt, sonst pdfforblinds.zip. Nur Dateien mit Prüfsumme."""
    usable = [a for a in data.get("assets") or []
              if (a.get("digest") or "").startswith("sha256:")]
    exes = [a for a in usable if a.get("name", "").lower().endswith(".exe")]
    zips = [a for a in usable if a.get("name", "").lower().endswith(".zip")
            and a.get("name", "").lower().startswith(ZIP_PREFIX)]
    for asset in exes + zips:
        return Update(data.get("tag_name", ""), data.get("body") or "", asset["name"],
                      asset["browser_download_url"], int(asset.get("size", 0)),
                      asset["digest"].split(":", 1)[1].lower())
    return None


def is_newer(update: Update, exe_path: Path) -> bool:
    if sha256(exe_path) == update.digest:
        return False
    mine, theirs = own_version(exe_path), parse_version(update.tag)
    return mine is not None and theirs is not None and theirs > mine


def check(exe_path: Path, skipped: str = "", fetch=fetch_json) -> Update | None:
    """Gibt es ein Update? skipped: vom Nutzer übersprungene Version (Tag)."""
    data = fetch(LATEST_URL)
    update = from_release(data) if data else None
    if update is None or (skipped and update.tag == skipped):
        return None
    return update if is_newer(update, exe_path) else None


# -- Ordner -------------------------------------------------------------------------------------
def fixed_home(exe_path: Path) -> Path | None:
    """Der feste Ordner der Exe, z. B. Release\\pdfforblinds. Läuft die Exe aus diesem Ordner oder
    aus einem alten Versionsordner wie Release\\pdfforblinds-v0.1.0, ist es Release\\pdfforblinds.
    Sonst None, dann wird die Exe an ihrem Ort getauscht."""
    folder, stem = exe_path.parent, exe_path.stem.lower()
    if folder.name.lower() == stem or (_VERSION_HOME.search(folder.name)
                                       and folder.name.lower().startswith(f"{stem}-v")):
        return folder.parent / exe_path.stem
    return None


def pending_dir(exe_path: Path) -> Path:
    """Wo die neue Version wartet. Beim festen Ordner daneben, damit sie nicht mit dem
    bisherigen Ordner umbenannt wird."""
    home = fixed_home(exe_path)
    return (home.parent if home is not None else exe_path.parent) / PENDING


def is_waiting(exe_path: Path) -> bool:
    return (pending_dir(exe_path) / exe_path.name).is_file()


def folder_version(folder: Path) -> str:
    """Veröffentlichte Version aus version.txt im Ordner, sonst leer."""
    try:
        text = (folder / VERSION_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return text if re.fullmatch(r"\d+\.\d+\.\d+", text) else ""


def backup_folder(reason: str) -> Path:
    """Ordner für Sicherheitskopien unter %LOCALAPPDATA%\\pdfforblinds\\Sicherheitskopien."""
    base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / REPO
    folder = base / BACKUP_FOLDER / f"{datetime.now():%Y-%m-%d_%H-%M-%S} {reason}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _running_from(folder: Path) -> bool:
    exe = own_exe()
    return exe is not None and folder.resolve() in exe.resolve().parents


def prune_versions(exe_path: Path) -> list[Path]:
    """Beim Start: nur die neuesten KEEP_VERSIONS alten Versionsordner behalten, ältere in die
    Sicherheitskopien. Ein Ordner, aus dem das Programm gerade läuft, bleibt."""
    home = fixed_home(exe_path)
    if home is None or not home.parent.is_dir():
        return []
    prefix = f"{home.name.lower()}-v"

    def version_of(path: Path):
        match = _VERSION_HOME.search(path.name)
        return tuple(int(x) for x in match.groups()) if match else ()

    folders = sorted((p for p in home.parent.iterdir() if p.is_dir() and _VERSION_HOME.search(p.name)
                      and p.name.lower().startswith(prefix)), key=version_of, reverse=True)
    moved = []
    for folder in folders[KEEP_VERSIONS:]:
        if _running_from(folder):
            continue
        try:
            shutil.move(str(folder), str(backup_folder(f"Alte Version {folder.name}") / folder.name))
            moved.append(folder)
        except OSError:
            pass
    return moved


# -- Laden --------------------------------------------------------------------------------------
def _beside(name: str) -> bool:
    """Was aus der ZIP-Datei neben die Exe kommt: README, Lizenz und version.txt."""
    lower = Path(name).name.lower()
    return (lower.startswith("readme") or lower.split(".")[0] in ("license", "licence", "copying")
            or lower == VERSION_FILE)


def download(update: Update, exe_path: Path, cancel: threading.Event | None = None,
             fetch=fetch_file) -> Path:
    """Neue Exe nach _neu laden, unter dem Namen der laufenden Exe. Prüft die Prüfsumme."""
    pending = pending_dir(exe_path)
    shutil.rmtree(pending, ignore_errors=True)
    pending.mkdir(parents=True)
    target = pending / (update.asset_name if update.is_zip else exe_path.name)
    try:
        digest = fetch(update.url, target, cancel)
        if digest != update.digest:
            raise UpdateError("Die heruntergeladene Datei ist beschädigt oder verändert. Sie "
                              "wurde gelöscht, die bisherige Version bleibt.", "SHA-256 weicht ab")
        if update.is_zip:
            return _exe_from_zip(target, pending / exe_path.name)
        return target
    except BaseException:
        shutil.rmtree(pending, ignore_errors=True)
        raise


def _exe_from_zip(archive: Path, target: Path) -> Path:
    """Die Exe aus der geprüften ZIP-Datei holen, unter dem Namen der laufenden Exe. Nur diese
    Datei und README, Lizenz, version.txt aus demselben Ordner werden geschrieben, an einen festen
    Ort, egal welche Pfade in der ZIP stehen."""
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = [m for m in bundle.infolist()
                       if not m.is_dir() and m.filename.lower().endswith(".exe")]
            same = [m for m in members if Path(m.filename).name.lower() == target.name.lower()]
            chosen = (same or members)[:1]
            if not chosen or len(members) > 1 and not same:
                raise UpdateError("In der ZIP-Datei der neuen Version steckt keine passende Exe. "
                                  "Die bisherige Version bleibt.",
                                  ", ".join(m.filename for m in members) or "keine Exe")
            if any("_internal/" in m.filename.replace("\\", "/") for m in bundle.infolist()):
                raise UpdateError(f"Die neue Version ist ein Programmordner. Den kann {APP_NAME} "
                                  "nicht selbst austauschen. Laden Sie die ZIP-Datei bitte von "
                                  "der Release-Seite.", archive.name)
            with bundle.open(chosen[0]) as source, open(target, "wb") as file:
                shutil.copyfileobj(source, file)
            folder = Path(chosen[0].filename.replace("\\", "/")).parent
            for member in bundle.infolist():
                path = Path(member.filename.replace("\\", "/"))
                if member.is_dir() or path.parent != folder or not _beside(path.name):
                    continue
                with bundle.open(member) as source, open(target.parent / path.name, "wb") as file:
                    shutil.copyfileobj(source, file)
    except zipfile.BadZipFile as exc:
        raise UpdateError("Die ZIP-Datei der neuen Version ist beschädigt. Die bisherige Version "
                          "bleibt.", repr(exc)) from None
    archive.unlink()
    return target


# -- Austauschen --------------------------------------------------------------------------------
def swap(exe_path: Path, version: str) -> Path:
    """Austausch-Skript für die wartende Exe (ohne Neustart). Beim festen Ordner: War die bisherige
    Version veröffentlicht (version.txt), heißt ihr Ordner danach Name-vVersion, sonst kommt sie in
    die Sicherheitskopien. Die neue kommt in den festen Ordner."""
    pending = pending_dir(exe_path)
    new = pending / exe_path.name
    if not new.is_file():
        raise UpdateError("Es wartet keine neue Version.")
    backup = backup_folder(f"vor Version {version}")
    docs = sorted(p for p in pending.iterdir() if p.is_file() and _beside(p.name))
    home = fixed_home(exe_path)
    if home is None:
        old = [exe_path] + [exe_path.parent / d.name for d in docs
                            if (exe_path.parent / d.name).is_file()]
        return swap_script(pending, old, [new] + docs, backup, exe_path.parent)
    old: list = []
    if home.exists():
        before = folder_version(home)
        target = home.parent / f"{home.name}-v{before}"
        old = [(home, target) if before and not target.exists() else home]
    return swap_script(pending, old, [new] + docs, backup, home)


def swap_script(pending: Path, old_items: list, new_items: list[Path], backup: Path,
                new_dir: Path, pid: int | None = None) -> Path:
    """Skript, das auf das Ende des Programms wartet, old_items in die Sicherheitskopie backup
    verschiebt (ein Eintrag (Quelle, Ziel) kommt nach Ziel, z. B. Name-v0.1.0), new_items nach
    new_dir holt und _neu löscht. Startet nichts. Muster aus dem CodeCockpit (exe_restart.py)."""
    old_moves = [item if isinstance(item, tuple) else (item, backup / item.name)
                 for item in old_items]
    pid = pid or os.getpid()
    system = r"%SystemRoot%\System32"
    lines = ["@echo off", "chcp 65001 >nul", "set versuche=0", ":warten",
             f'"{system}\\tasklist.exe" /FI "PID eq {pid}" /NH | "{system}\\find.exe" " {pid} " >nul',
             "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto warten)"]
    # Kurz nach dem Beenden kann Windows die alte Exe noch sperren: bis zu 30 Versuche
    moves = old_moves + [(item, new_dir / item.name) for item in new_items]
    for number, (source, target) in enumerate(moves, start=1):
        if number == len(old_moves) + 1:
            lines.append(f'if not exist "{new_dir}" mkdir "{new_dir}"')
        lines += [f":schieben{number}",
                  f'move /Y "{source}" "{target}" >nul 2>nul',
                  f"if not errorlevel 1 goto fertig{number}",
                  "set /a versuche+=1",
                  "if %versuche% geq 30 goto aufgeben",
                  "timeout /t 1 /nobreak >nul",
                  f"goto schieben{number}",
                  f":fertig{number}"]
    lines.append(f'rmdir /S /Q "{pending}"')
    lines.append('(goto) 2>nul & del "%~f0"')
    lines.append(":aufgeben")
    # Klappt das Tauschen nicht, kommt schon Verschobenes zurück; die neue Exe wartet weiter in _neu
    for item, target in old_moves:
        lines.append(f'if exist "{target}" if not exist "{item}" move /Y "{target}" "{item}" >nul 2>nul')
    lines.append('(goto) 2>nul & del "%~f0"')
    script = Path(tempfile.gettempdir()) / f"{REPO}-update.bat"
    script.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    return script


def clean_environment() -> dict[str, str]:
    """Umgebung ohne die Variablen, die eine Exe von PyInstaller für sich selbst setzt."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("_PYI_", "_MEIPASS"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def launch(script: Path) -> None:
    """Skript unsichtbar starten. Es läuft weiter, wenn das Programm sich beendet."""
    subprocess.Popen(["cmd.exe", "/c", str(script)], close_fds=True, env=clean_environment(),
                     creationflags=FLAGS | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
