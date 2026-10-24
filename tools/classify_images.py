"""Bildart (Diagramm, Foto, Zeichnung …) für die Bilder eines schon umgewandelten Projekts nachtragen.

Neue Umwandlungen machen das automatisch. Die Platzhalter in den Seitentexten
werden angepasst, z. B. <bild 1, Zeichnung: keine Beschreibung>.

Aufruf: python tools/classify_images.py <datei.pdfforblinds | projektordner>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from app.project_model import Project  # noqa: E402
from converter.classify import classify, kind_text  # noqa: E402


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    project = Project.from_package(path) if path.is_file() else Project(path)
    count = 0
    for page in project.data["seiten"]:
        for img in page["bilder"]:
            with Image.open(project.folder / img["datei"]) as image:
                kind, certainty = classify(image)
            img["typ"], img["typ_sicherheit"] = kind, round(certainty, 2)
            print(f"Seite {page['nr']}, Bild {img['nr']}: {kind_text(kind, certainty)} ({certainty:.0%})")
            count += 1
    project.save()
    # neu laden, damit die Bildarten in den Text kommen; schreibt auch .pdfforblinds und .txt
    Project(project.folder, project.package).update_text_files()
    print(f"\n{count} Bilder eingeordnet.")


if __name__ == "__main__":
    main()
