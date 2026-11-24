"""Dónde vive cada cosa.

- Carpeta del PROGRAMA: el .exe, datos/ de serie (cartas de prueba, mazos oficiales, tutorial,
  glosario base) e idiomas/. Las actualizaciones la sustituyen entera.
- Carpeta de USUARIO: todo lo que es tuyo y las actualizaciones nunca tocan:
  config.ini (claves de DeepL), perfiles/, mazos/, fundas/, imagenes/, datos/cartas.json,
  datos/traducciones/ y datos/glosario/ (nombres que hayas corregido).

Con la app instalada, la carpeta de usuario es %APPDATA%\\SimuladorConan.
Modo portátil: si junto al .exe hay un archivo «portable.txt», todo se guarda junto al .exe.
Al ejecutar desde el código fuente (python app.py), se usa la carpeta del proyecto, como antes.
"""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

NOMBRE_APP = "SimuladorConan"

# lo que se copia al importar los datos de una versión anterior (carpeta antigua → usuario)
IMPORTABLE = ("config.ini", "perfiles", "mazos", "fundas", "imagenes",
              "datos/cartas.json", "datos/traducciones", "datos/glosario/nombres_es.csv",
              "datos/glosario/nombres_ca.csv")


@dataclass
class Rutas:
    programa: Path
    usuario: Path

    @property
    def datos_programa(self) -> Path:
        return self.programa / "datos"

    @property
    def datos_usuario(self) -> Path:
        return self.usuario / "datos"

    def preparar(self):
        """Crea la carpeta de usuario y copia los archivos editables la primera vez."""
        for sub in ("", "datos", "datos/traducciones", "datos/glosario", "perfiles", "mazos", "fundas"):
            (self.usuario / sub).mkdir(parents=True, exist_ok=True)
        origen = self.datos_programa / "glosario"
        if origen.resolve() != (self.datos_usuario / "glosario").resolve() and origen.exists():
            for f in origen.glob("nombres_*.csv"):
                destino = self.datos_usuario / "glosario" / f.name
                if not destino.exists():
                    shutil.copy2(f, destino)


def carpeta_programa() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def carpeta_usuario(programa: Path) -> Path:
    if os.environ.get("SIMULADOR_DATOS"):
        return Path(os.environ["SIMULADOR_DATOS"])
    if not getattr(sys, "frozen", False) or (programa / "portable.txt").exists():
        return programa
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / NOMBRE_APP


def rutas() -> Rutas:
    prog = carpeta_programa()
    r = Rutas(prog, carpeta_usuario(prog))
    r.preparar()
    return r


def parece_version_anterior(carpeta: Path) -> bool:
    return any((Path(carpeta) / x).exists() for x in ("config.ini", "perfiles", "datos/cartas.json"))


def importar(desde: Path, r: Rutas) -> list[str]:
    """Copia los datos de usuario de una instalación anterior. No borra nada del origen.
    Devuelve la lista de elementos copiados."""
    desde = Path(desde)
    copiados = []
    for rel in IMPORTABLE:
        origen = desde / rel
        if not origen.exists():
            continue
        destino = r.usuario / rel
        if origen.resolve() == destino.resolve():
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        if origen.is_dir():
            shutil.copytree(origen, destino, dirs_exist_ok=True)
        else:
            shutil.copy2(origen, destino)
        copiados.append(rel)
    return copiados
