"""Rival controlado por la app.

Tres niveles que comparten las mismas piezas:
  · Fácil: reglas de prioridad como las de un jugador novato, con algún despiste a propósito.
  · Normal: prueba cada jugada en una copia de la partida, juega el resto de su decisión con
    las reglas y se queda con la que deja mejor la mesa (función de valoración).
  · Difícil: Monte Carlo. Para las mejores jugadas candidatas simula muchas continuaciones
    (los dos jugadores con las reglas) y elige la que más gana / mejor termina.

Juego limpio: la IA nunca mira la mano del rival ni el orden de los mazos. Antes de pensar,
«imagina» esa información: reparte al azar las cartas que no puede ver entre la mano rival y
los mazos (determinización), y piensa sobre varias de esas posibilidades.

Estilos: «equilibrado», «agresivo» (presiona las Pruebas rivales y ataca más) y «prudente»
(protege su escena, guarda más y valora la mano).
"""
from __future__ import annotations

import copy
import math
import random
import time
from dataclasses import dataclass

from . import acciones as A
from .cartas import PERSONAJE
from .estado import ACTIVO, DORMIDO
from .reglas import FILE_PARA_RESOLUCION, Motor, ReglaError

NIVELES = ("facil", "normal", "dificil")
ESTILOS = ("equilibrado", "agresivo", "prudente", "base")

# efectos que perjudican a la carta elegida (se eligen cartas del rival)
DANINAS = {"dormir", "aturdir", "retirar", "fondo_mazo", "a_mano", "boca_abajo"}

PESOS = {
    "equilibrado": dict(pruebas=10.0, pruebas_rival=10.0, file=3.0, mano=1.6, escena=1.0, ap=0.9, lp=2.2,
                        activo=0.6, amenaza=25.0, carrera=12.0),
    "agresivo": dict(pruebas=11.0, pruebas_rival=14.0, file=2.6, mano=1.2, escena=0.9, ap=1.2, lp=2.4,
                     activo=0.3, amenaza=30.0, carrera=12.0),
    "prudente": dict(pruebas=9.0, pruebas_rival=9.0, file=3.2, mano=2.2, escena=1.3, ap=0.8, lp=1.8,
                     activo=1.2, amenaza=22.0, carrera=12.0),
}
PESOS["base"] = dict(PESOS["equilibrado"], carrera=0.0)   # solo para comparar en el banco de pruebas


# ------------------------------------------------------------------ copiar y «imaginar»

def copiar(m: Motor) -> Motor:
    """Copia independiente de la partida (las definiciones de carta se comparten)."""
    p = m.p
    memo = {id(p.log): []}
    for c in p._uids.values():
        memo[id(c.defn)] = c.defn
    return Motor(copy.deepcopy(p, memo))


def imaginar(m: Motor, yo: int, rng: random.Random) -> Motor:
    """Copia en la que lo que «yo» no puede ver se ha repartido al azar."""
    c = copiar(m)
    p = c.p
    r = c.j(p.rival(yo))
    ocultas = r.mano + r.mazo
    rng.shuffle(ocultas)
    n = len(r.mano)
    r.mano, r.mazo = ocultas[:n], ocultas[n:]
    rng.shuffle(c.j(yo).mazo)
    p.rng = random.Random(rng.random())
    return c


# ------------------------------------------------------------------ valoración

def valor_carta(c) -> float:
    d = c.defn
    if d.tipo != PERSONAJE:
        return 1.0 + d.nivel * 0.3
    return 1.0 + c.ap / 1000 + c.lp * 1.5 + d.nivel * 0.2


def turnos_para_ganar(m: Motor, j) -> float:
    """Estimación de cuántos turnos propios le faltan para Resolver el caso."""
    nec = m.nivel_caso(j)
    if j.caso_resuelto:
        t_file = 0
    else:
        falta = max(0, FILE_PARA_RESOLUCION - j.cartas_file - 1)   # −1: la Asistencia cuenta
        t_file = math.ceil(falta / 2) + 1                          # +1: el turno de Asistir
    ritmo = sum(c.lp for c in j.escena if c.lp > 0) + 0.5           # Pruebas por turno deduciendo
    t_prueba = math.ceil(max(0, nec - len(j.pruebas)) / ritmo)
    return max(t_file, t_prueba) + 1


def valorar(m: Motor, yo: int, estilo: str = "equilibrado") -> float:
    """Cuánto le gusta a «yo» la situación (positivo = va ganando)."""
    p = m.p
    if p.ganador is not None:
        return 1e6 if p.ganador == yo else -1e6
    w = PESOS.get(estilo, PESOS["equilibrado"])
    total = 0.0
    for idx, signo in ((yo, 1.0), (p.rival(yo), -1.0)):
        j = m.j(idx)
        nec = max(1, m.nivel_caso(j))
        pr = len(j.pruebas)
        s = (w["pruebas"] if signo > 0 else w["pruebas_rival"]) * (min(pr, nec) + 0.3 * max(0, pr - nec))
        s += w["file"] * min(j.cartas_file, FILE_PARA_RESOLUCION)
        if j.caso_resuelto:
            s += 6.0
            if pr >= nec:
                s += w["amenaza"]          # puede ganar en su próximo turno
        s += w["mano"] * min(len(j.mano), 8)
        for c in j.escena:
            s += w["escena"] + w["ap"] * c.ap / 1000 + w["lp"] * c.lp
            if c.estado == ACTIVO:
                s += w["activo"]
        if len(j.mazo) < 6:
            s -= (6 - len(j.mazo)) * 1.5
        s -= w.get("carrera", 0.0) * turnos_para_ganar(m, j)
        total += signo * s
    return total


# ------------------------------------------------------------------ reglas (nivel fácil y simulaciones)

def _id_dueno(m, uid):
    return m.p.carta(uid).dueno


def prioridad(m: Motor, a: A.Accion, yo: int) -> float:
    """Puntuación rápida de una jugada sin simularla (cómo jugaría alguien con reglas sencillas)."""
    p = m.p
    j = m.j(yo)
    r = m.j(p.rival(yo))
    if isinstance(a, A.ResolverCaso):
        return 1000 if len(j.pruebas) >= m.nivel_caso(j) else -50
    if isinstance(a, A.Mulligan):
        bajas = sum(1 for c in j.mano if c.defn.nivel <= 3)
        if not a.uids:
            return 10 if bajas >= 2 else 0
        return 5 if len(a.uids) == len(j.mano) and bajas < 2 else -5
    if isinstance(a, A.Asistir):
        if not j.caso_resuelto and j.cartas_file + 1 >= FILE_PARA_RESOLUCION:
            return 95
        return 30 if not j.caso_resuelto else -10
    if isinstance(a, A.Deducir):
        c = p.carta(a.uid)
        if c is j.companero and j.caso_resuelto:
            return 3       # en Resolución el Compañero se guarda para Resolver; solo deduce al final
        return 55 + c.lp * 18 - (10 if c is j.companero else 0)
    if isinstance(a, A.JugarCarta):
        c = p.carta(a.uid)
        castigo = 0 if a.retirar is None else 8 + valor_carta(p.carta(a.retirar)) * 3
        return 60 + c.defn.nivel * 4 + valor_carta(c) - castigo
    if isinstance(a, A.NoJugar):
        return 1
    if isinstance(a, A.SiguientePista):
        # gasta una carta de FILE (hace falta para la Resolución): solo si luego se puede jugar algo
        limite = j.cartas_file - 1
        if j.caso_resuelto or j.cartas_file > FILE_PARA_RESOLUCION:
            jugables = [c for c in j.mano + j.file[-1:] if c.defn.nivel <= limite]
        else:
            jugables = [c for c in j.mano + j.file[-1:] if c.defn.nivel <= limite and c.defn.nivel >= 4]
        if len(j.escena) >= 5 or not jugables:
            return -5
        return 18
    if isinstance(a, A.Declarar):
        return 38
    if isinstance(a, A.Atacar):
        at = p.carta(a.atacante)
        if a.objetivo is None:
            return 42 + 3 * min(len(r.pruebas), 4)
        t = p.carta(a.objetivo)
        if at.ap >= t.ap:
            return 48 + valor_carta(t) * 2
        return 4
    if isinstance(a, A.Guardia):
        info = p.pendiente.datos if p.pendiente else {}
        atac = p.carta(info["atacante"]) if info.get("atacante") is not None else None
        if a.uid is None:
            return 20
        g = p.carta(a.uid)
        if atac is not None and g.ap >= atac.ap:
            return 60 - valor_carta(g)
        if info.get("objetivo") is None and len(j.pruebas) >= m.nivel_caso(j) - 1:
            return 35 - valor_carta(g)          # defender las Pruebas cuando está cerca de ganar
        return 5
    if isinstance(a, A.Contactar):
        if a.uid is None:
            return 15
        return 30 if a.modo == "irrupcion" else 26
    if isinstance(a, A.PistaFalsa):
        return 30 + 5 * len(a.uids)
    if isinstance(a, A.Elegir):
        return _prioridad_eleccion(m, a, yo)
    if isinstance(a, A.FinTurno):
        return 0
    return 1


def _prioridad_eleccion(m: Motor, a: A.Elegir, yo: int) -> float:
    d = m.p.pendiente.datos
    modo = d["modo"]
    if modo in ("si_no", "manual"):
        return 10 if a.opcion == 1 else 0
    if modo == "opcion":
        return 10 - a.opcion
    tras = d.get("tras")
    if tras in ("descartar", "cambio"):        # perder cartas propias: las menos valiosas
        return -sum(valor_carta(m.p.carta(u)) for u in a.uids)
    danina = d.get("accion") in DANINAS
    det = d.get("detalle", {})
    if d.get("accion") == "mod" and det.get("valor", 0) < 0:
        danina = True
    s = 0.0
    for u in a.uids:
        c = m.p.carta(u)
        propia = c.dueno == yo
        v = valor_carta(c)
        if tras == "tomar" or d.get("accion") in ("entrar", "usar"):
            s += v
        elif danina:
            s += v if not propia else -v
        else:
            s += v if propia else -v
    return s


def por_reglas(m: Motor, yo: int, rng: random.Random, despiste: float = 0.0) -> A.Accion:
    legales = m.legales()
    if len(legales) == 1:
        return legales[0]
    if despiste and rng.random() < despiste:
        opciones = [a for a in legales if not isinstance(a, (A.FinTurno, A.ResolverCaso))] or legales
        if rng.random() < 0.5:
            opciones = [a for a in opciones if not isinstance(a, A.Declarar)] or opciones
        return rng.choice(opciones)
    mejor = max(prioridad(m, a, yo) + rng.random() * 0.5 for a in legales)
    return next(a for a in legales if prioridad(m, a, yo) + 0.5 >= mejor)


# ------------------------------------------------------------------ IA

@dataclass
class Pensamiento:
    accion: A.Accion
    simulaciones: int = 0
    segundos: float = 0.0


class IA:
    def __init__(self, jugador: int, nivel: str = "normal", estilo: str = "equilibrado",
                 semilla: int | None = None, tiempo: float = 1.6):
        self.yo = jugador
        self.nivel = nivel if nivel in NIVELES else "normal"
        self.estilo = estilo if estilo in ESTILOS else "equilibrado"
        self.rng = random.Random(semilla)
        self.tiempo = tiempo

    def le_toca(self, m: Motor) -> bool:
        return m.p.ganador is None and m.p.quien_decide() == self.yo

    def pensar(self, m: Motor) -> Pensamiento:
        t0 = time.monotonic()
        legales = m.legales()
        if len(legales) == 1:
            return Pensamiento(legales[0])
        if self.nivel == "facil":
            return Pensamiento(por_reglas(m, self.yo, self.rng, despiste=0.22), 0, time.monotonic() - t0)
        if self.nivel == "normal":
            a, n = self._normal(m, legales)
        else:
            a, n = self._dificil(m, legales)
        return Pensamiento(a, n, time.monotonic() - t0)

    # -- normal: probar cada jugada y terminar la decisión propia con reglas
    def _seguir_mi_turno(self, c: Motor, limite: int = 40):
        """Juega con reglas mientras decida «yo» y siga siendo el mismo turno."""
        turno = c.p.turno
        for _ in range(limite):
            if c.p.ganador is not None or c.p.quien_decide() != self.yo or c.p.turno != turno:
                return
            try:
                c.aplicar(por_reglas(c, self.yo, self.rng))
            except ReglaError:
                return

    def _puntuar(self, m: Motor, legales, mundos: int) -> list:
        puntos = []
        for a in legales:
            total = 0.0
            for k in range(mundos):
                c = imaginar(m, self.yo, self.rng)
                try:
                    c.aplicar(a)
                except ReglaError:
                    total = -1e9
                    break
                self._seguir_mi_turno(c)
                total += valorar(c, self.yo, self.estilo)
            puntos.append((total / mundos, a))
        return puntos

    def _candidatas(self, m: Motor, legales, n: int) -> list:
        """Las n jugadas más prometedoras según las reglas (para no simularlas todas)."""
        orden = sorted(legales, key=lambda a: prioridad(m, a, self.yo), reverse=True)
        if not any(isinstance(a, A.FinTurno) for a in orden[:n]):
            fin = [a for a in orden if isinstance(a, A.FinTurno)]
            return orden[:n - 1] + fin if fin else orden[:n]
        return orden[:n]

    def _normal(self, m: Motor, legales):
        cand = self._candidatas(m, legales, 14)
        puntos = self._puntuar(m, cand, 2)
        mejor = max(p for p, _ in puntos)
        empatadas = [a for p, a in puntos if p >= mejor - 1e-6]
        return self.rng.choice(empatadas), len(cand) * 2

    # -- difícil: Monte Carlo con determinización
    def _simular(self, m: Motor, a: A.Accion, pasos: int = 300) -> float:
        """Juega la jugada en un mundo imaginado, acaba el turno propio y el del rival con reglas,
        y valora cómo queda la mesa al volver a tocarle (así ve los contraataques)."""
        c = imaginar(m, self.yo, self.rng)
        try:
            c.aplicar(a)
        except ReglaError:
            return -1e6
        turno = c.p.turno
        fin = turno + (2 if c.p.activo == self.yo else 1)
        for _ in range(pasos):
            if c.p.ganador is not None or c.p.turno >= fin:
                break
            q = c.p.quien_decide()
            try:
                c.aplicar(por_reglas(c, q, self.rng))
            except ReglaError:
                break
        return valorar(c, self.yo, self.estilo)

    def _dificil(self, m: Motor, legales):
        cand = self._candidatas(m, legales, 10)
        previa = sorted(self._puntuar(m, cand, 2), key=lambda x: x[0], reverse=True)
        cand = [a for _, a in previa[:6]]
        if len(cand) == 1:
            return cand[0], 1
        suma = [0.0] * len(cand)
        n = [0] * len(cand)
        limite = time.monotonic() + self.tiempo
        total = 0
        # rondas: cada candidata se prueba en los mismos mundos imaginados (comparación justa)
        while total < 4 * len(cand) or (time.monotonic() < limite and total < 30 * len(cand)):
            semilla = self.rng.random()
            for i, a in enumerate(cand):
                self.rng.seed(semilla)
                suma[i] += self._simular(m, a)
                n[i] += 1
                total += 1
            self.rng.seed(semilla + 1)
        mejor = max(range(len(cand)), key=lambda k: suma[k] / n[k])
        return cand[mejor], total
