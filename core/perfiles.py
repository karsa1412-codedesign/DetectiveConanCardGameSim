"""Perfiles de usuario locales y registro de accesos.

Se guardan junto al .exe, en la carpeta perfiles/:
- perfiles.json: datos de cada perfil.
- accesos.csv: una línea por evento (separador «;», se abre con Excel).
"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

EVENTOS = ("perfil_creado", "inicio_sesion", "cierre_sesion", "tutorial_recomendado",
           "tutorial_inicio", "tutorial_completado", "tutorial_saltado", "tutorial_abandonado",
           "partida_inicio", "partida_fin", "partida_abandonada", "partida_ia_inicio", "partida_ia_fin")


def ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class PerfilError(Exception):
    pass


class GestorPerfiles:
    def __init__(self, carpeta: Path):
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.ruta = self.carpeta / "perfiles.json"
        self.ruta_log = self.carpeta / "accesos.csv"
        self.perfiles: dict[str, dict] = {}
        if self.ruta.exists():
            self.perfiles = json.loads(self.ruta.read_text(encoding="utf-8")).get("perfiles", {})

    def guardar(self):
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps({"perfiles": self.perfiles}, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.ruta)

    def listar(self) -> list[dict]:
        return sorted(self.perfiles.values(), key=lambda p: p.get("ultimo_acceso", ""), reverse=True)

    def crear(self, nombre: str) -> dict:
        nombre = " ".join(nombre.split())
        if not nombre:
            raise PerfilError("El nombre no puede estar vacío.")
        if len(nombre) > 24:
            raise PerfilError("El nombre puede tener como mucho 24 caracteres.")
        if nombre.lower() in (n.lower() for n in self.perfiles):
            raise PerfilError("Ya existe un perfil con ese nombre.")
        p = {"nombre": nombre, "creado": ahora(), "ultimo_acceso": "", "accesos": 0,
             "tutorial_completado": False, "tutoriales_completados": 0, "tutorial_recomendado": False,
             "partidas_iniciadas": 0, "partidas_terminadas": 0}
        self.perfiles[nombre] = p
        self.guardar()
        self.registrar(nombre, "perfil_creado")
        return p

    def entrar(self, nombre: str) -> dict:
        p = self.perfiles[nombre]
        p["ultimo_acceso"] = ahora()
        p["accesos"] = p.get("accesos", 0) + 1
        self.guardar()
        self.registrar(nombre, "inicio_sesion")
        return p

    def es_nuevo(self, nombre: str) -> bool:
        """Perfil que aún no ha visto la recomendación del tutorial."""
        return not self.perfiles[nombre].get("tutorial_recomendado", False)

    def actualizar(self, nombre: str, **cambios):
        self.perfiles[nombre].update(cambios)
        self.guardar()

    def sumar(self, nombre: str, campo: str, n: int = 1):
        p = self.perfiles[nombre]
        p[campo] = p.get(campo, 0) + n
        self.guardar()

    def registrar(self, nombre: str, evento: str, detalle: str = ""):
        if evento not in EVENTOS:
            raise ValueError(evento)
        nuevo = not self.ruta_log.exists()
        with open(self.ruta_log, "a", encoding="utf-8-sig" if nuevo else "utf-8", newline="") as f:
            w = csv.writer(f, delimiter=";")
            if nuevo:
                w.writerow(["fecha", "perfil", "evento", "detalle"])
            w.writerow([ahora(), nombre, evento, detalle])

    # ---------------------------------------------------------------- estadísticas por mazo

    def mazos(self, nombre: str) -> dict:
        """{mazo: {partidas, victorias, derrotas, companeros: {id: n}, ultima}} del perfil.
        La primera vez se reconstruye con el registro de partidas que ya existía."""
        p = self.perfiles[nombre]
        if "mazos" not in p:
            p["mazos"] = self._mazos_desde_registro(nombre)
            self.guardar()
        return p["mazos"]

    def _mazos_desde_registro(self, nombre: str) -> dict:
        out: dict = {}
        actual = None
        for r in self.leer_registro(nombre):
            ev, det = r["evento"], r.get("detalle") or ""
            if ev in ("partida_inicio", "partida_ia_inicio") and " contra " in det:
                actual = det.split(" contra ")[0].strip()
                e = out.setdefault(actual, {"partidas": 0, "victorias": 0, "derrotas": 0, "companeros": {},
                                            "ultima": ""})
                e["partidas"] += 1
                e["ultima"] = r["fecha"]
            elif ev == "partida_ia_fin" and actual in out:
                out[actual]["victorias" if det.startswith("gana") else "derrotas"] += 1
                actual = None
        return out

    def uso_mazo(self, nombre: str, mazo: str, companero: str):
        e = self.mazos(nombre).setdefault(mazo, {"partidas": 0, "victorias": 0, "derrotas": 0,
                                                 "companeros": {}, "ultima": ""})
        e["partidas"] += 1
        e["companeros"][companero] = e["companeros"].get(companero, 0) + 1
        e["ultima"] = ahora()
        self.guardar()

    def resultado_mazo(self, nombre: str, mazo: str, gano: bool):
        e = self.mazos(nombre).get(mazo)
        if e is not None:
            e["victorias" if gano else "derrotas"] += 1
            self.guardar()

    def mazo_favorito(self, nombre: str) -> tuple[str, dict] | None:
        mz = self.mazos(nombre)
        if not mz:
            return None
        k = max(mz, key=lambda m: (mz[m]["partidas"], mz[m].get("ultima", "")))
        return k, mz[k]

    def leer_registro(self, nombre: str | None = None) -> list[dict]:
        if not self.ruta_log.exists():
            return []
        with open(self.ruta_log, encoding="utf-8-sig", newline="") as f:
            filas = list(csv.DictReader(f, delimiter=";"))
        return [r for r in filas if nombre is None or r["perfil"] == nombre]
