# Von Hand angepasst (nicht mehr die Vorlage von CodeCockpit, damit das Cockpit sie nicht überschreibt).
# Pfade sind relativ zum Ordner Repository.
#
# Die Exe enthält das Leseprogramm mit Bildbeschreibung (Gemma über Ollama) und den Vektordaten aus
# der PDF. Die schweren Teile der Umwandlung (PyTorch, Docling, Unlimited-OCR) sind ausgeschlossen;
# sie werden erst beim Umwandeln geladen.

a = Analysis(['main.py'], pathex=[], binaries=[], datas=[],
             hiddenimports=[],
             excludes=[
                 # nur für page.find_tables() von PyMuPDF, lädt sonst ein ONNX-Modell
                 'pymupdf.layout', 'onnxruntime',
                 # Umwandlung: wird in der Exe nicht eingebaut
                 'torch', 'torchvision', 'transformers', 'docling', 'docling_core',
                 'docling_ibm_models', 'accelerate', 'safetensors', 'tokenizers',
                 'matplotlib', 'pandas', 'scipy', 'cv2',
             ])
pyz = PYZ(a.pure)

exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='pdfforblinds',
          console=False, icon=None, upx=False)
