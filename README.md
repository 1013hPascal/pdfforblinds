# PDF für Blinde (pdfforblinds)

PDF für Blinde wandelt PDFs und Fotos in einen Text um, den blinde Menschen gut lesen können. Mathematik wird als LaTeX geschrieben, Tabellen werden als Text dargestellt. Bilder beschreibt auf Wunsch ein Sprachmodell. Ein eigenes Leseprogramm zeigt das Ergebnis Seite für Seite an und lässt sich ganz mit der Tastatur und einem Screenreader (zum Beispiel NVDA oder JAWS) bedienen.

Alles läuft auf dem eigenen Rechner. Es werden keine Dokumente ins Internet geschickt. Die einzige Internetverbindung ist die Suche nach Updates auf GitHub.

## Inhalt

1. Was das Programm kann
2. Bedienung
3. Wie das Programm arbeitet
4. Verwendete Sprachmodelle
5. Mindestanforderungen an den Rechner
6. So finden Sie heraus, was in Ihrem Rechner steckt
7. Installation
8. Aufbau des Codes

## 1. Was das Programm kann

- **PDFs und Fotos umwandeln:** Das sind zum Beispiel Vorlesungsskripte, Übungsblätter, Paper mit Formeln, Bücher, PDFs aus dem Internet, eingescannte Briefe oder Handyfotos von Briefen.
- **Mathematik als LaTeX:** Formeln im Text stehen als `$...$`, abgesetzte Formeln als `$$...$$`.
- **Überschriften, Listen, Fußnoten** bleiben erhalten, Formatierung wie fett oder kursiv nicht. Seitenzahlen sowie Kopf- und Fußzeilen werden entfernt.
- **Tabellen:** Vor jeder Tabelle steht, wie viele Zeilen und Spalten sie hat. Danach folgt eine Zeile pro Tabellenzeile, die Spalten sind mit ` & ` getrennt (wie in LaTeX). Ein echtes & in einer Zelle wird zu `\&`.
- **Bilder:**
  - **Bildart:** Jedes Bild bekommt automatisch eine Bildart, zum Beispiel Zeichnung, Liniendiagramm, Foto, Landkarte, Logo oder Strukturformel. Ist das Modell unsicher, steht „vermutlich“ davor.
  - **Platzhalter:** Im Text steht an der Stelle des Bildes ein Platzhalter, zum Beispiel `<bild 1, Zeichnung: keine Beschreibung>`.
  - **Bildbeschreibung:** Eine ausführliche Beschreibung erstellt das Sprachmodell Gemma 4 auf Wunsch, für ein einzelnes Bild, für alle Bilder einer Seite oder für das ganze Dokument. Man kann auch eine Frage mitgeben, zum Beispiel „Wie lang ist der Pfeil a?“. Dann legt die Beschreibung den Schwerpunkt darauf.
  - **Exakte Werte aus der PDF:** Bei Zeichnungen in PDFs (zum Beispiel aus LaTeX) liest das Programm Koordinaten, Pfeile und Beschriftungen exakt aus der PDF aus. Das Sprachmodell muss sie dann nicht aus dem Bild schätzen.
- **Ablage neben der PDF:** Sobald die Umwandlung startet, entsteht neben der PDF ein Ordner, zum Beispiel:
  ```
  Skript.pdf
  pdfforblinds Skript\
      Skript.pdfforblinds   (das Dokument für das Leseprogramm)
      Skript.txt            (das komplette Dokument als Text, mit allen Bildbeschreibungen)
  ```
  Beide Dateien werden während der Umwandlung laufend aktualisiert, ebenso bei jeder neuen Bildbeschreibung. Die Textdatei lässt sich in jedem Editor oder auf einer Braillezeile lesen.
- **Fortsetzen:** Wird eine lange Umwandlung abgebrochen, macht das Programm beim nächsten Mal bei der nächsten Seite weiter.
- **Updates:** Das Programm prüft beim Start, ob es auf GitHub eine neue Version gibt, und fragt vorher nach (siehe Bedienung).

## 2. Bedienung

Programm starten: `start_app.bat` (oder später die Exe).

**Startseite** (beim Start ist kein Dokument geöffnet):
- **Alt+A**, PDF oder Foto auswählen: Es öffnet sich der normale Dateidialog. Gibt es zu der Datei schon eine Umwandlung, wird sie geöffnet. Sonst beginnt die Umwandlung.
- **Alt+Z**, Zuletzt: Das sind die letzten 50 geöffneten Dateien. Enter öffnet eine Datei, Entf nimmt sie aus der Liste (die Datei selbst bleibt).
- Mit Strg+O kann man auch direkt eine `.pdfforblinds`-Datei öffnen.

**Seitenliste:**
- **Pfeil hoch/runter** wählt eine Seite. Jeder Eintrag nennt die Seitenzahl, die Zahl der Bilder und wie viele davon beschrieben sind.
- **Pfeil rechts** klappt die Bilder einer Seite auf. Jedes Bild zeigt seine Bildart und ob es eine Beschreibung hat.
- **Enter** auf einer Seite öffnet den Seitentext. Enter auf einem Bild öffnet seine Beschreibung oder lässt sie erstellen.

**Seitentext:**
- **Enter** (oder ein Klick) auf einem Bild-Platzhalter öffnet die Beschreibung im zweiten Textfeld oder lässt sie erstellen.
- **Strg+Tab** wechselt zwischen Seitentext und Bildbeschreibung.
- **Strg+Bild ab / Strg+Bild auf** wechselt zur nächsten oder vorigen Seite.
- **Escape** schließt zuerst die Bildbeschreibung und führt dann zurück zur Seitenliste.

**Menü Bilder (Alt+B):**
- Bilder für gesamtes Dokument umsetzen
- Alle Bilder für Seite x umsetzen (wenn man gerade auf einer Seite ist)
- Neue Bildbeschreibung für Bild … (Strg+R, wenn eine Bildbeschreibung offen ist): fragt „Was willst du wissen, worauf soll der Fokus sein?“

**Weitere Tasten:**
- **Strg+W:** Dokument schließen
- **F1:** alle Tastenkürzel anzeigen

**Ansagen:** Wichtige Meldungen (zum Beispiel „Beschreibung ist fertig“) werden dem Screenreader direkt angesagt.

**Updates (Menü Hilfe):**
- **„Nach Updates suchen“:** Das Programm schaut im neuesten Release auf GitHub nach. Die neue Version wird heruntergeladen und auf Beschädigung geprüft (SHA-256).
- **Kein Neustart:** Das Programm startet sich nicht selbst neu. Es schließt sich auf Wunsch nur, die neue Exe wird beim Beenden ausgetauscht, und danach starten Sie es selbst wieder.
- **Alte Versionen:** Die bisherige Version bleibt als Ordner `pdfforblinds-vX.Y.Z` daneben. Die zwei letzten alten Versionen werden aufbewahrt.
- Updates gibt es nur für die Exe, nicht beim Start aus dem Code.

## 3. Wie das Programm arbeitet

### Schritt 1: Jede Seite einzeln prüfen (ohne KI)

Mit **PyMuPDF** schaut das Programm in die Textebene jeder PDF-Seite und entscheidet in Sekundenbruchteilen, welches Modell die Seite bekommt.

**Unlimited-OCR** (gründlich, etwa 35 bis 70 Sekunden pro Seite) bekommt eine Seite, wenn:
- es ein Foto ist,
- die Seite kaum Text in der PDF hat oder fast nur aus einem Bild besteht (dann ist sie vermutlich eingescannt),
- die Textebene kaputt ist, also viele unlesbare Zeichen hat,
- Mathe-Schriften vorkommen (zum Beispiel die LaTeX-Schriften CMMI, CMSY, CMEX), mathematische Unicode-Zeichen oder mehrere hochgestellte Textstücke.

**Docling** (schnell, etwa 2 Sekunden pro Seite) bekommt alle anderen Seiten mit normalem Text.

Der Grund für diese Aufteilung: Docling liest den Text direkt aus der PDF und ist dadurch sehr schnell und genau, bei LaTeX-PDFs aber unbrauchbar. Dort gingen in Tests Hochzahlen verloren (aus 10³⁰ W wurde „1030 W“), Umlaute zerfielen („¨U“ statt „Ü“), und Formeln wurden nicht erkannt. Unlimited-OCR liest die Seite dagegen als Bild und schreibt Formeln, Tabellen und Umlaute zuverlässig, braucht dafür aber 20- bis 30-mal so lange. Mit der Weiche bekommt jede Seite das passende Modell. Ein Buch ohne Formeln ist so in wenigen Minuten fertig.

### Schritt 2: Text erkennen

- **Docling** (von IBM) erkennt den Aufbau der Seite (Überschriften, Absätze, Listen, Tabellen, Bilder, Bildunterschriften, Fußnoten). Eine eigene Texterkennung (OCR) nutzt es hier nicht, weil diese Seiten ohnehin eine gute Textebene haben.
- **Unlimited-OCR** (von Baidu) bekommt die Seite als Bild mit 200 dpi und liefert für jeden Abschnitt die Art (Überschrift, Text, Formel, Tabelle, Bild …), die Position auf der Seite und den Inhalt. Formeln kommen als LaTeX, Tabellen als HTML.

### Schritt 3: In das Blinden-Format bringen

Beide Ergebnisse werden in dasselbe Format gebracht. Es orientiert sich an von Hand erstellten Übertragungen für Blinde: `<seite>`, `$...$`, `<anmerkung>`, `<tabelle>`, `<fußnote>`, `<bild ...>`. Seitenzahlen, Kopf- und Fußzeilen fallen weg.

### Schritt 4: Bilder ausschneiden und einordnen

- **Ausschneiden:** Jedes Bild wird mit 400 dpi direkt aus der PDF neu gerendert, nicht aus dem gröberen Seitenbild ausgeschnitten. Bei Fotos wird das Originalfoto beschnitten.
- **Einordnen:** Danach ordnet ein kleiner Bildklassifizierer von Docling (16 MB, etwa 50 Millisekunden pro Bild) das Bild einer von 26 Bildarten zu, zum Beispiel Liniendiagramm, Zeichnung, Foto, Landkarte, Logo oder Strukturformel.

### Schritt 5: Bildbeschreibung mit exakten Daten aus der PDF

Sprachmodelle lesen Koordinaten aus Bildern oft ungenau ab. In Tests las Gemma zum Beispiel einen Pfeil falsch ab, obwohl die Zeichnung eindeutig war. Ein höher aufgelöstes Bild half dabei nicht. Deshalb nutzt das Programm einen zweiten Weg.

- **Vektordaten auslesen:** Grafiken aus LaTeX und vielen anderen PDFs sind keine Pixelbilder, sondern Vektorgrafiken. Linien, Pfeile und Beschriftungen stehen mit exakten Koordinaten in der PDF. Mit **PyMuPDF** (`get_drawings`) liest das Programm diese Zeichnungsbefehle aus:
  - doppelte Striche entfernen,
  - Pfeilspitzen erkennen (kleine gefüllte Dreiecke) und den Linien zuordnen,
  - markierte Punkte erkennen,
  - kurze Beschriftungen (a, b, F1 …) dem nächsten Pfeil zuordnen,
  - das Koordinatensystem über die Achsenpfeile und die Zahlen an den Achsen eichen, sodass Punkte in Achsen-Einheiten angegeben werden, zum Beispiel „Pfeil a von (0 | 0) nach (1 | 0,5)“.
- **Keine Erfindungen:** PyMuPDF liest nur, was wirklich in der Datei steht. Es rät nichts und kann sich deshalb nicht „verlesen“. Bei Fotos und Scans gibt es keine Vektordaten; dann beschreibt Gemma nur das Bild. Bei sehr vielen Zeichnungsbefehlen werden nur die Beschriftungen übergeben.
- **Was Gemma bekommt:**
  - das Bild,
  - den Text der ganzen Seite als Zusammenhang,
  - die Bildunterschrift,
  - die Bildart,
  - die exakten Vektordaten mit dem Hinweis, dass diese Vorrang vor der eigenen Schätzung haben,
  - auf Wunsch die Frage des Nutzers.
- **Antwortformat:** Gemma antwortet in einem festen Format (Typ, x-Achse, y-Achse, Beschreibung), auf Deutsch, mit Mathematik in LaTeX.

### Schritt 6: Speichern

- **Neben der PDF:** Ergebnis und Bilder kommen in die Datei `.pdfforblinds` neben der PDF (eine ZIP-Datei mit `project.json`, den Seitentexten und den Bildern). Dazu kommt das komplette Dokument als `.txt`.
- **Arbeitsordner:** Gearbeitet wird in einem Arbeitsordner unter `%LOCALAPPDATA%\pdfforblinds\Arbeitsordner`. Die Datei neben der PDF ist aber immer die gültige Fassung.

## 4. Verwendete Sprachmodelle

| Aufgabe | Modell | Herkunft | Größe | Läuft auf |
|---|---|---|---|---|
| Texterkennung für Formeln, Scans, Fotos | Unlimited-OCR (auf Basis von DeepSeek-OCR, 3 Milliarden Parameter, Mixture of Experts) | Baidu, [huggingface.co/baidu/Unlimited-OCR](https://huggingface.co/baidu/Unlimited-OCR) | 6,3 GB | NVIDIA-GPU (CUDA), Intel-GPU (XPU) oder CPU |
| Seitenaufbau für normalen Text | Docling mit dem Layoutmodell Heron und TableFormer | IBM, [github.com/docling-project/docling](https://github.com/docling-project/docling) | 1,3 GB (alle Docling-Modelle) | CPU |
| Bildart | DocumentFigureClassifier v2.5 | IBM/Docling | 16 MB | CPU |
| Bildbeschreibung | Gemma 4 12B (`gemma4:12b`) über Ollama | Google, [ollama.com](https://ollama.com) | 8 GB | NVIDIA, AMD, Intel (Vulkan) oder CPU |

Zusammen sind das etwa 16 GB auf der Festplatte, dazu die Python-Umgebung (etwa 5 GB). Bei Gemma 4 sind zwei Einstellungen nötig: das Denken ist abgeschaltet (`think: false`), und das Kontextfenster ist 8192 Token groß. Sonst liefert das Modell bei langen Seiten leere Antworten.

## 5. Mindestanforderungen an den Rechner

Am meisten Leistung brauchen Unlimited-OCR (bei Seiten mit Formeln und Scans) und Gemma 4 (bei Bildbeschreibungen). Die übrigen Teile laufen auf jedem aktuellen Rechner. Beide großen Modelle müssen in den Grafikspeicher passen. Bei Grafikchips im Prozessor (Intel Core Ultra) teilen sich Grafik und Prozessor den normalen Arbeitsspeicher, deshalb zählt dort der Arbeitsspeicher.

### Mindestens

- Windows 10 oder 11, 64 Bit
- 16 GB Arbeitsspeicher. Dann nicht gleichzeitig umwandeln und Bilder beschreiben lassen.
- 25 GB freier Speicherplatz, am besten auf einer SSD
- Ein Prozessor mit mindestens 4 Kernen aus den letzten etwa 5 Jahren

### Empfohlen

- 32 GB Arbeitsspeicher, oder eine Grafikkarte mit mindestens 12 GB Grafikspeicher
- Eine der folgenden Grafiklösungen:

**Intel (so wurde das Programm entwickelt und getestet):**
- **Getestet:** Intel Core Ultra 7 258V mit Intel Arc 140V und 32 GB Arbeitsspeicher. Gemessen: Docling etwa 2 Sekunden pro Seite, Unlimited-OCR 35 bis 70 Sekunden pro Seite, Gemma etwa 1 Minute pro Bild.
- **Sollte ebenso laufen** (gleiche PyTorch-XPU-Unterstützung, nicht selbst getestet):
  - Intel Core Ultra 5/7/9 der Serie 200V (Lunar Lake, Arc 130V/140V)
  - Core Ultra der Serie 100H/200H (Meteor Lake, Arrow Lake mit Arc-Grafik)
  - Intel Arc A770/A750 (Desktop) und Arc B580/B570
- **Ältere Intel-Grafik** (Iris Xe, UHD Graphics) unterstützt PyTorch nicht. Dann läuft Unlimited-OCR auf dem Prozessor, siehe „Nur Prozessor“.

**NVIDIA** (Unterstützung eingebaut, aber noch nicht auf einem NVIDIA-Rechner getestet):
- **Mindestens** eine GeForce RTX der Serie 30 oder neuer mit 8 GB Grafikspeicher, zum Beispiel RTX 3060 Ti, 3070, 4060 oder 5060. Unlimited-OCR rechnet im Format bfloat16, das erst ab der RTX-30-Serie gut unterstützt wird.
- **Empfohlen** 12 GB oder mehr, zum Beispiel RTX 3060 12 GB, 4070, 4060 Ti 16 GB oder 5070. Mit 8 GB lagert Ollama einen Teil von Gemma in den Arbeitsspeicher aus. Das funktioniert, ist aber langsamer.
- **Ältere Karten** (GTX 10xx, GTX 16xx, RTX 20xx) werden voraussichtlich nicht oder nur langsam laufen.

**AMD:**
- **Bildbeschreibung:** Gemma 4 läuft über Ollama auch auf AMD-Grafikkarten (Radeon RX 6000/7000/9000).
- **Umwandlung:** Unlimited-OCR braucht PyTorch für die Grafikkarte, das unter Windows für AMD bisher nicht zuverlässig verfügbar ist. Die Umwandlung läuft dann auf dem Prozessor (siehe unten). Nicht getestet.

**Nur Prozessor, ohne passende Grafik:**
- **Funktioniert:** Seiten mit normalem Text (Docling) sind genauso schnell wie mit Grafikkarte.
- **Deutlich langsamer:** Seiten mit Formeln, Scans und Fotos (Unlimited-OCR) sowie Bildbeschreibungen. Das wurde nicht gemessen; rechnen Sie mit mehreren Minuten pro Seite oder Bild. Für einzelne Briefe geht das, für Bücher mit Formeln nicht.

## 6. So finden Sie heraus, was in Ihrem Rechner steckt

**Prozessor und Arbeitsspeicher:**
- Windows-Taste drücken, „Info“ eingeben, „Info zu Ihrem PC“ öffnen.
- Unter „Gerätespezifikationen“ stehen „Prozessor“ (zum Beispiel „Intel Core Ultra 7 258V“) und „Installierter RAM“ (zum Beispiel „32,0 GB“).

**Grafikkarte, mit dem Screenreader am bequemsten:**
- Windows-Taste+R drücken, `dxdiag` eingeben, Enter. Eine eventuelle Frage nach der Treibersignatur mit Ja beantworten.
- Auf „Alle Informationen speichern …“ gehen und die Textdatei speichern, zum Beispiel auf dem Desktop.
- In der Textdatei nach „Card name“ suchen (der Name der Grafikkarte, zum Beispiel „Intel(R) Arc(TM) 140V GPU“ oder „NVIDIA GeForce RTX 4060“). Unter „Dedicated Memory“ steht der Grafikspeicher. Steht dort sehr wenig (zum Beispiel 128 MB), ist es ein Grafikchip im Prozessor, der den Arbeitsspeicher mitbenutzt.
- Gibt es zwei Einträge „Card name“, hat der Rechner zwei Grafiklösungen. Für das Programm zählt die stärkere.

**Alternative mit dem Task-Manager:**
- Strg+Umschalt+Escape öffnet den Task-Manager. Dort „Leistung“ wählen, dann „GPU 0“ oder „GPU 1“.
- Oben steht der Name der Grafikkarte, unten „Dedizierter GPU-Speicher“ und „Gemeinsam genutzter GPU-Speicher“.

**Freier Speicherplatz:**
- Im Explorer „Dieser PC“ öffnen. Bei jedem Laufwerk steht, wie viel frei ist.

## 7. Installation

Noch gibt es keine fertige Exe. Bis dahin wird das Programm aus dem Code gestartet.

1. **Python 3.12 und uv installieren**, zum Beispiel mit `winget install astral-sh.uv`. Dann im Ordner des Programms:
   ```
   uv venv --python 3.12 .venv
   ```
2. **PyTorch passend zur Grafik installieren** (nur einer der drei Befehle):
   - Intel-Grafik (Arc, Core Ultra):
     ```
     uv pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/xpu
     ```
   - NVIDIA:
     ```
     uv pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cu128
     ```
   - Nur Prozessor:
     ```
     uv pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cpu
     ```
3. **Die übrigen Pakete installieren:**
   ```
   uv pip install -r requirements.txt
   ```
4. **Die Modelle in den Ordner `modelle` laden:**
   ```
   .venv\Scripts\hf download baidu/Unlimited-OCR --local-dir modelle\unlimited-ocr
   .venv\Scripts\docling-tools models download -o modelle\docling
   ```
   Wer die Modelle woanders ablegen will, setzt die Umgebungsvariable `PDFFORBLINDS_MODELLE` auf diesen Ordner.
5. **Ollama installieren** (von [ollama.com](https://ollama.com)) und Gemma 4 laden:
   ```
   ollama pull gemma4:12b
   ```
   Läuft Ollama noch nicht, startet das Programm es bei der ersten Bildbeschreibung selbst.
6. **Starten** mit `start_app.bat`.

Umwandeln geht auch ohne Leseprogramm, in der Eingabeaufforderung:

```
.venv\Scripts\python -m converter Skript.pdf
.venv\Scripts\python -m converter Skript.pdf --pages 1-5
.venv\Scripts\python -m converter Brief.jpg
.venv\Scripts\python -m converter Skript.pdf --dry-run
```

- **`--pages`** wandelt nur bestimmte Seiten um.
- **`--force-ocr`** schickt alle Seiten durch Unlimited-OCR.
- **`--dry-run`** zeigt nur, welche Seite welches Modell bekäme.

## 8. Aufbau des Codes

- **`app/`:** das Leseprogramm (PySide6)
  - `main_window.py`: Fenster, Seitenliste, Textfelder, Menüs
  - `start_page.py`: Startseite mit „Zuletzt“
  - `describer.py`: Bildbeschreibung mit Gemma über Ollama, nacheinander im Hintergrund
  - `project_model.py`: ein geöffnetes Dokument lesen und Beschreibungen speichern
  - `update.py`, `update_ui.py`: Updates über GitHub-Releases
- **`converter/`:** die Umwandlung
  - `analyze.py`: Weiche pro Seite
  - `engine_docling.py`, `engine_unlimited.py`: die beiden Erkennungswege
  - `render.py`: Blinden-Format
  - `images.py`: Bilder in hoher Auflösung ausschneiden
  - `classify.py`: Bildart
  - `vectors.py`: exakte Vektordaten aus der PDF
  - `package.py`: `.pdfforblinds` und `.txt` neben der Quelle
  - `config.py`: Pfade und Schwellwerte
- **`tools/`:** Hilfsprogramme
  - `compare.py`: mit einer von Hand erstellten Blinden-Fassung vergleichen
  - `recrop.py`: Bilder neu ausschneiden
  - `classify_images.py`: Bildart nachtragen
