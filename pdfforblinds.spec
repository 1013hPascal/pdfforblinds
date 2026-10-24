# Erstellt von CodeCockpit. Sie dürfen die Datei anpassen, das Cockpit nutzt sie
# bei jedem Bau weiter. Pfade sind relativ zum Ordner Repository.

a = Analysis(['main.py'], pathex=[], binaries=[], datas=[],
             hiddenimports=[],
             excludes=[
                 # nur für page.find_tables() von PyMuPDF, lädt sonst ein ONNX-Modell
                 'pymupdf.layout', 'onnxruntime',
                 # Umwandlung: läuft über die Python-Umgebung im Programmordner, nicht in der Exe
                 'torch', 'torchvision', 'transformers', 'docling', 'docling_core',
                 'docling_ibm_models', 'accelerate', 'safetensors', 'tokenizers',
                 'matplotlib', 'pandas', 'scipy', 'cv2',
             ])
pyz = PYZ(a.pure)

exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='pdfforblinds',
          console=False, icon=None, upx=False)
