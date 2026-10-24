# Erstellt von CodeCockpit. Sie dürfen die Datei anpassen, das Cockpit nutzt sie
# bei jedem Bau weiter. Pfade sind relativ zum Ordner Repository.

a = Analysis(['main.py'], pathex=[], binaries=[], datas=[],
             hiddenimports=[], excludes=[])
pyz = PYZ(a.pure)

exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='pdfforblinds',
          console=False, icon=None, upx=False)
