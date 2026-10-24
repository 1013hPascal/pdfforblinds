@echo off
rem Startet das Leseprogramm. Optional: PDF, Foto oder .pdfforblinds als Argument.
rem Nimmt die Python-Umgebung .venv in diesem Ordner, sonst die aus der Entwicklung (..\..\ocr_test\.venv).
cd /d "%~dp0"
set PYTHONUTF8=1
set PY=.venv\Scripts\pythonw.exe
if not exist "%PY%" set PY=..\..\ocr_test\.venv\Scripts\pythonw.exe
if not exist "%PY%" (
    echo Keine Python-Umgebung gefunden. Siehe README.md, Abschnitt Installation.
    pause
    exit /b 1
)
start "" "%PY%" main.py %*
