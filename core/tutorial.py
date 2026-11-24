"""Partida tutorial pregrabada.

El guion (datos/tutorial/tutorial.json) fija los mazos, quién empieza y una lista de pasos:
- "continuar": solo explica; el usuario pulsa Continuar.
- "usuario": el usuario debe hacer exactamente la jugada indicada en "espera".
- "rival": la jugada del rival, que se aplica al pulsar Continuar.

Las jugadas se describen por ID de carta, no por uid, y se comparan con las acciones
legales del motor: si el motor no permite una jugada del guion, el tutorial lo detecta.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import acciones as A
from .cartas import Catalogo, Mazo
from .reglas import Motor, nueva_partida


class GuionError(Exception):
    pass


def _id(motor: Motor, uid) -> str | None:
    if uid is None:
        return None
    c = motor.p.carta(uid)
    jug = motor.j(c.dueno)
    if c is jug.companero:
        return "companero"
    return c.defn.id


def coincide(motor: Motor, a: A.Accion, spec: dict) -> bool:
    """¿La acción a es la que pide el guion?"""
    if type(a).__name__ != spec["tipo"]:
        return False
    if "jugador" in spec and a.jugador != spec["jugador"]:
        return False
    if isinstance(a, A.Mulligan):
        return sorted(_id(motor, u) for u in a.uids) == sorted(spec.get("cartas", []))
    if isinstance(a, A.Atacar):
        objetivo = "caso" if a.objetivo is None else _id(motor, a.objetivo)
        return _id(motor, a.atacante) == spec["carta"] and objetivo == spec["objetivo"]
    if isinstance(a, A.Contactar):
        return _id(motor, a.uid) == spec.get("carta") and (a.uid is None or a.modo == spec.get("modo", "irrupcion"))
    if isinstance(a, A.Guardia):
        return _id(motor, a.uid) == spec.get("carta")
    if isinstance(a, A.PistaFalsa):
        return sorted(_id(motor, u) for u in a.uids) == sorted(spec.get("cartas", []))
    if isinstance(a, (A.JugarCarta, A.Deducir)):
        if _id(motor, a.uid) != spec["carta"]:
            return False
        if isinstance(a, A.JugarCarta):
            return _id(motor, a.retirar) == spec.get("retirar")
    return True


def disponible(ruta: Path, base_datos: Path, catalogo: Catalogo) -> bool:
    """¿Están en el catálogo todas las cartas que usa este guion?"""
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    for idx in ("0", "1"):
        m = datos["mazos"][idx]
        mazo = Mazo.cargar(base_datos / "mazos" / m["mazo"])
        ids = [m.get("companero") or mazo.companero, mazo.caso, *mazo.cartas]
        if any(cid not in catalogo for cid in ids):
            return False
    return True


class Guion:
    def __init__(self, ruta: Path, base_datos: Path, catalogo: Catalogo | None = None):
        """catalogo: el de la app (cartas descargadas) para los guiones con cartas reales;
        si no se da, se carga el archivo que indica el guion dentro de base_datos."""
        self.datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        self.pasos = self.datos["pasos"]
        self.indice = 0
        cat = catalogo if catalogo is not None else Catalogo.cargar(base_datos / self.datos["catalogo"])
        self.catalogo = cat
        mazos, arriba = [], {}
        for idx in (0, 1):
            m = self.datos["mazos"][str(idx)]
            mazo = Mazo.cargar(base_datos / "mazos" / m["mazo"])
            if m.get("companero"):
                mazo.companero = m["companero"]
            mazos.append(mazo)
            arriba[idx] = m.get("arriba", [])
        self.motor = nueva_partida(cat, mazos[0], mazos[1], semilla=self.datos.get("semilla", 1),
                                   primero=self.datos["primero"], arriba=arriba)
        self.narrador = self.datos.get("narrador", "")

    # -------------------------------------------------------------- estado

    @property
    def paso(self) -> dict | None:
        return self.pasos[self.indice] if self.indice < len(self.pasos) else None

    @property
    def terminado(self) -> bool:
        return self.indice >= len(self.pasos)

    def texto(self, idioma: str = "es") -> str:
        p = self.paso
        if p is None:
            return ""
        t = p["texto"]
        t = (t.get(idioma) or t.get("es", "")) if isinstance(t, dict) else t
        # {D10016} → nombre de la carta en el idioma elegido
        def nombre(m):
            cid = m.group(1)
            return f"«{self.catalogo[cid].nombre_en(idioma)}»" if cid in self.catalogo else cid
        return re.sub(r"\{([A-Z0-9-]+)\}", nombre, t)

    def tipo(self) -> str:
        p = self.paso
        if p is None:
            return "fin"
        if "espera" in p:
            return "usuario"
        if "rival" in p:
            return "rival"
        return "continuar"

    def resaltar(self) -> list[str]:
        return (self.paso or {}).get("resaltar", [])

    def progreso(self) -> tuple[int, int]:
        return self.indice + 1, len(self.pasos)

    # -------------------------------------------------------------- avanzar

    def es_esperada(self, a: A.Accion) -> bool:
        return self.tipo() == "usuario" and coincide(self.motor, a, self.paso["espera"])

    def esperadas(self) -> list[A.Accion]:
        if self.tipo() != "usuario":
            return []
        return [a for a in self.motor.legales() if coincide(self.motor, a, self.paso["espera"])]

    def jugar_usuario(self, a: A.Accion):
        if not self.es_esperada(a):
            raise GuionError("Esa no es la jugada que toca ahora en el tutorial.")
        self.motor.aplicar(a)
        self.indice += 1

    def continuar(self):
        """Avanza un paso de explicación o aplica la jugada del rival."""
        t = self.tipo()
        if t == "usuario":
            raise GuionError("Este paso lo tiene que hacer el jugador.")
        if t == "rival":
            spec = self.paso["rival"]
            opciones = [a for a in self.motor.legales() if coincide(self.motor, a, spec)]
            if not opciones:
                raise GuionError(f"El motor no permite la jugada del guion en el paso {self.indice + 1}: {spec}")
            self.motor.aplicar(opciones[0])
        if t != "fin":
            self.indice += 1
