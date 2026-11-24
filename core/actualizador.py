"""Buscar, descargar e instalar actualizaciones publicadas en GitHub Releases.

No depende de la interfaz: la ventana lo llama desde un hilo aparte.
- buscar(): consulta la última versión publicada y dice si es más nueva que la instalada.
- descargar(): baja el instalador a una carpeta temporal y comprueba su SHA-256
  (publicado junto al instalador como <instalador>.sha256).
- lanzar_instalador(): ejecuta el instalador en modo silencioso; al terminar vuelve a abrir la app.
Tus datos están en otra carpeta (ver core/rutas.py), así que la actualización no los toca.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .version import PATRON_INSTALADOR, VERSION, comparar

API = "https://api.github.com/repos/{repo}/releases/latest"
AGENTE = f"SimuladorConan/{VERSION}"


class ActualizacionError(Exception):
    pass


@dataclass
class Novedad:
    version: str
    notas: str
    url_instalador: str
    url_hash: str | None
    nombre: str
    tamano: int


def _get(url: str, timeout=20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ActualizacionError("No hay ninguna versión publicada (o el repositorio no es público).") from e
        raise ActualizacionError(f"GitHub respondió {e.code}.") from e
    except OSError as e:
        raise ActualizacionError(f"No se pudo conectar: {e}") from e


def interpretar(release: dict, actual: str = VERSION) -> Novedad | None:
    """Datos de una release de GitHub → Novedad si es más nueva que la versión actual."""
    if release.get("draft") or release.get("prerelease"):
        return None
    version = str(release.get("tag_name", "")).lstrip("vV")
    if not version or comparar(version, actual) <= 0:
        return None
    esperado = PATRON_INSTALADOR.format(version=version)
    activos = {a["name"]: a for a in release.get("assets", [])}
    inst = activos.get(esperado) or next((a for n, a in activos.items()
                                          if n.lower().endswith(".exe") and "setup" in n.lower()), None)
    if inst is None:
        return None
    sha = activos.get(inst["name"] + ".sha256")
    return Novedad(version, (release.get("body") or "").strip(), inst["browser_download_url"],
                   sha["browser_download_url"] if sha else None, inst["name"], int(inst.get("size", 0)))


def buscar(repo: str, actual: str = VERSION) -> Novedad | None:
    if not repo:
        return None
    return interpretar(json.loads(_get(API.format(repo=repo))), actual)


def descargar(n: Novedad, progreso: Callable[[float], None] | None = None,
              parar: Callable[[], bool] = lambda: False) -> Path:
    destino = Path(tempfile.gettempdir()) / "SimuladorConan-actualizacion" / n.nombre
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".part")
    req = urllib.request.Request(n.url_instalador, headers={"User-Agent": AGENTE})
    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or n.tamano or 0)
            hecho = 0
            while True:
                if parar():
                    raise ActualizacionError("Descarga cancelada.")
                trozo = r.read(256 * 1024)
                if not trozo:
                    break
                f.write(trozo)
                h.update(trozo)
                hecho += len(trozo)
                if progreso and total:
                    progreso(hecho / total)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise ActualizacionError(f"Falló la descarga: {e}") from e
    except ActualizacionError:
        tmp.unlink(missing_ok=True)
        raise
    if n.url_hash:
        esperado = _get(n.url_hash).decode("utf-8", "replace").split()[0].strip().lower()
        if esperado != h.hexdigest():
            tmp.unlink(missing_ok=True)
            raise ActualizacionError("El archivo descargado no coincide con la firma publicada; no se instala.")
    tmp.replace(destino)
    return destino


def lanzar_instalador(ruta: Path):
    """Ejecuta el instalador en silencio. La app debe cerrarse justo después."""
    if os.name != "nt":
        raise ActualizacionError("La actualización automática solo funciona en Windows.")
    args = [str(ruta), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELAUNCH"]
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(args, close_fds=True, creationflags=flags)


def instalada() -> bool:
    """True si la app corre como .exe instalado (no desde el código ni en modo portátil)."""
    if not getattr(sys, "frozen", False):
        return False
    return not (Path(sys.executable).parent / "portable.txt").exists()
