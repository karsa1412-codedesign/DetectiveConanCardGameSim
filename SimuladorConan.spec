# PyInstaller: genera dist\SimuladorConan\ (carpeta con el .exe, más rápida de arrancar que un
# único archivo). datos\ e idiomas\ van junto al .exe; el instalador empaqueta la carpeta entera.
import shutil
from pathlib import Path

a = Analysis(["app.py"], pathex=["."], hiddenimports=[], excludes=["pytest", "tests"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SimuladorConan", console=False,
          icon="instalador/icono.ico" if Path("instalador/icono.ico").exists() else None)
coll = COLLECT(exe, a.binaries, a.datas, name="SimuladorConan")

# datos de serie e idiomas, junto al .exe (sin los datos de usuario de quien compila)
destino = Path(DISTPATH) / "SimuladorConan"
for carpeta in ("datos", "idiomas"):
    shutil.copytree(carpeta, destino / carpeta, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.py", "cartas.json", "traducciones", "*.tmp"))
