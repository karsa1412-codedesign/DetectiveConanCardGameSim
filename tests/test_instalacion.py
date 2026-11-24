"""Rutas de programa/usuario, importación de datos antiguos y actualizador (sin red)."""
import hashlib
import http.server
import json
import threading
from pathlib import Path

import pytest

from core import actualizador
from core import rutas as R
from core.version import VERSION, comparar


def test_comparar_versiones():
    assert comparar("0.7.0", "0.7.0") == 0
    assert comparar("v0.10.0", "0.9.9") == 1
    assert comparar("1.2", "1.2.1") == -1
    assert comparar("1.0.0-beta", "1.0.0") == 0


def test_preparar_copia_glosario_sin_pisar(tmp_path):
    prog, usu = tmp_path / "prog", tmp_path / "usu"
    (prog / "datos" / "glosario").mkdir(parents=True)
    (prog / "datos" / "glosario" / "nombres_es.csv").write_text("a;b\n", encoding="utf-8")
    r = R.Rutas(prog, usu)
    r.preparar()
    destino = usu / "datos" / "glosario" / "nombres_es.csv"
    assert destino.read_text(encoding="utf-8") == "a;b\n"
    destino.write_text("a;corregido\n", encoding="utf-8")
    r.preparar()                                     # una actualización no pisa lo del usuario
    assert destino.read_text(encoding="utf-8") == "a;corregido\n"
    assert (usu / "perfiles").is_dir() and (usu / "mazos").is_dir()


def test_importar_version_anterior(tmp_path):
    viejo = tmp_path / "viejo"
    (viejo / "perfiles").mkdir(parents=True)
    (viejo / "perfiles" / "perfiles.json").write_text("{}", encoding="utf-8")
    (viejo / "datos" / "traducciones").mkdir(parents=True)
    (viejo / "datos" / "traducciones" / "es.json").write_text("{}", encoding="utf-8")
    (viejo / "datos" / "cartas.json").write_text("{}", encoding="utf-8")
    (viejo / "config.ini").write_text("[deepl]\ngeneral = x\n", encoding="utf-8")
    (viejo / "app.py").write_text("", encoding="utf-8")         # el código no se copia
    assert R.parece_version_anterior(viejo)
    r = R.Rutas(tmp_path / "prog", tmp_path / "usu")
    r.preparar()
    copiados = R.importar(viejo, r)
    assert set(copiados) >= {"config.ini", "perfiles", "datos/cartas.json", "datos/traducciones"}
    assert (r.usuario / "datos" / "traducciones" / "es.json").exists()
    assert not (r.usuario / "app.py").exists()
    assert (viejo / "config.ini").exists()                       # el origen no se toca


def _release(version, base, con_hash=True):
    nombre = f"SimuladorConan-Setup-{version}.exe"
    activos = [{"name": nombre, "browser_download_url": f"{base}/{nombre}", "size": 11}]
    if con_hash:
        activos.append({"name": nombre + ".sha256", "browser_download_url": f"{base}/{nombre}.sha256"})
    return {"tag_name": f"v{version}", "body": "Novedades", "draft": False, "prerelease": False, "assets": activos}


def test_interpretar_release():
    assert actualizador.interpretar(_release(VERSION, "http://x")) is None          # misma versión
    assert actualizador.interpretar(_release("0.0.1", "http://x")) is None          # más antigua
    n = actualizador.interpretar(_release("99.0.0", "http://x"))
    assert n.version == "99.0.0" and n.url_instalador.endswith("Setup-99.0.0.exe") and n.url_hash
    assert actualizador.interpretar({**_release("99.0.0", "http://x"), "prerelease": True}) is None


@pytest.fixture
def servidor(tmp_path):
    contenido = b"instalador!"
    (tmp_path / "SimuladorConan-Setup-99.0.0.exe").write_bytes(contenido)
    (tmp_path / "SimuladorConan-Setup-99.0.0.exe.sha256").write_text(hashlib.sha256(contenido).hexdigest())
    (tmp_path / "malo.exe.sha256").write_text("0" * 64)

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(tmp_path), **k)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_descarga_verifica_firma(servidor, monkeypatch, tmp_path):
    monkeypatch.setattr(actualizador.tempfile, "gettempdir", lambda: str(tmp_path / "tmp"))
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    n = actualizador.interpretar(_release("99.0.0", servidor))
    ruta = actualizador.descargar(n)
    assert ruta.read_bytes() == b"instalador!"
    n.url_hash = servidor + "/malo.exe.sha256"
    with pytest.raises(actualizador.ActualizacionError):
        actualizador.descargar(n)


def test_spec_e_instalador_coherentes():
    raiz = Path(__file__).resolve().parent.parent
    iss = (raiz / "instalador" / "SimuladorConan.iss").read_text(encoding="utf-8")
    from core.version import PATRON_INSTALADOR
    assert "OutputBaseFilename=" + PATRON_INSTALADOR.replace("{version}", "{#Version}").removesuffix(".exe") in iss
    assert "/RELAUNCH" in iss and "PrivilegesRequired=lowest" in iss
