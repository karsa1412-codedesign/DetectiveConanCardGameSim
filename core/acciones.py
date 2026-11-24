"""Acciones que un jugador puede enviar al motor. Son datos simples para poder
guardarlas, repetir partidas y, más adelante, enviarlas por red."""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Accion:
    jugador: int

    def a_dict(self) -> dict:
        return {"tipo": type(self).__name__, **asdict(self)}


@dataclass(frozen=True)
class Mulligan(Accion):
    uids: tuple = ()          # cartas que se devuelven; () = quedarse la mano


@dataclass(frozen=True)
class JugarCarta(Accion):
    uid: int = 0
    retirar: int | None = None   # Cambio: Personaje a retirar si la escena está llena


@dataclass(frozen=True)
class SiguientePista(Accion):
    pass


@dataclass(frozen=True)
class NoJugar(Accion):
    """Renunciar a jugar carta tras Siguiente pista."""


@dataclass(frozen=True)
class Asistir(Accion):
    pass


@dataclass(frozen=True)
class ResolverCaso(Accion):
    pass


@dataclass(frozen=True)
class Deducir(Accion):
    uid: int = 0              # Compañero o Personaje que deduce


@dataclass(frozen=True)
class PistaFalsa(Accion):
    uids: tuple = ()          # Personajes con Pista falsa que se duermen; () = no responder


@dataclass(frozen=True)
class Atacar(Accion):
    """La acción 06 «Acción» del reglamento."""
    atacante: int = 0
    objetivo: int | None = None   # uid de un Personaje rival, o None para el Caso


@dataclass(frozen=True)
class Guardia(Accion):
    uid: int | None = None    # Personaje que guarda; None = no guardar


@dataclass(frozen=True)
class Contactar(Accion):
    uid: int | None = None    # carta de la mano; None = pasar
    modo: str = "irrupcion"   # irrupcion | disfraz


@dataclass(frozen=True)
class FinTurno(Accion):
    pass


@dataclass(frozen=True)
class Rendirse(Accion):
    """El jugador abandona: gana el rival. Se puede hacer en cualquier momento."""


@dataclass(frozen=True)
class Manual(Accion):
    """Herramienta de tablero para aplicar a mano efectos aún no programados."""
    op: str = ""              # ver Motor.OPS_MANUALES
    uid: int | None = None


TODAS = {c.__name__: c for c in (Mulligan, JugarCarta, SiguientePista, NoJugar, Asistir, ResolverCaso,
                                  Deducir, PistaFalsa, Atacar, Guardia, Contactar, FinTurno, Rendirse, Manual)}


def desde_dict(d: dict) -> Accion:
    d = dict(d)
    cls = TODAS[d.pop("tipo")]
    for k in ("uids",):
        if k in d:
            d[k] = tuple(d[k])
    return cls(**d)
