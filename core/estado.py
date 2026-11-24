"""Estado de una partida: cartas en juego, zonas de cada jugador y decisiones pendientes."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .cartas import CartaDef

ACTIVO = "activo"      # vertical
DORMIDO = "dormido"    # horizontal (スリープ)
ATURDIDO = "aturdido"  # invertida (スタン)

HASTA_CONTACTO = "contacto"
HASTA_TURNO = "turno"


@dataclass
class Mod:
    campo: str      # "ap" o "lp"
    valor: int
    hasta: str      # HASTA_CONTACTO / HASTA_TURNO / "" (permanente)


@dataclass
class Carta:
    """Una carta física concreta dentro de la partida."""
    uid: int
    defn: CartaDef
    dueno: int
    estado: str = ACTIVO
    turno_entrada: int = -1
    mods: list = field(default_factory=list)
    debajo: list = field(default_factory=list)  # cartas colocadas debajo (セット / 重ねる)

    @property
    def ap(self) -> int:
        return self.defn.ap + sum(m.valor for m in self.mods if m.campo == "ap")

    @property
    def lp(self) -> int:
        return self.defn.lp + sum(m.valor for m in self.mods if m.campo == "lp")

    def limpiar(self):
        """Al cambiar de zona la carta olvida estado y modificadores."""
        self.estado = ACTIVO
        self.turno_entrada = -1
        self.mods.clear()

    def __repr__(self):
        return f"<{self.defn.id}#{self.uid} {self.estado}>"


@dataclass
class Jugador:
    idx: int
    companero: Carta
    caso: Carta
    mazo: list = field(default_factory=list)       # el final de la lista es la parte de arriba
    mano: list = field(default_factory=list)
    escena: list = field(default_factory=list)
    file: list = field(default_factory=list)       # el final es la carta de arriba
    pruebas: list = field(default_factory=list)    # el final es la de arriba
    descarte: list = field(default_factory=list)
    zona_companero: list = field(default_factory=list)  # MR y cartas especiales
    companero_en_file: bool = False
    caso_resuelto: bool = False     # False = Fase Caso (事件編), True = Resolución (解決編)
    mulligan_hecho: bool = False
    jugo_mano: bool = False
    uso_pista: bool = False
    rastro_descubierto: bool = False

    @property
    def cartas_file(self) -> int:
        """Cartas en FILE contando al Compañero si ha Asistido (p. 11)."""
        return len(self.file) + (1 if self.companero_en_file else 0)


@dataclass
class Pendiente:
    """Decisión que la partida espera de un jugador concreto."""
    tipo: str        # mulligan | pista_jugar | pista_falsa | guardia | contacto
    jugador: int
    datos: dict = field(default_factory=dict)


@dataclass
class Contacto:
    atacante: int        # uid
    defensor: int        # uid
    orden: list          # [jugador que actúa 1º, jugador que actúa 2º]
    paso: int = 0
    actuo: dict = field(default_factory=dict)  # jugador -> bool


@dataclass
class Partida:
    jugadores: list
    primero: int
    semilla: int
    activo: int = 0
    turno: int = 0
    fase: str = "preparacion"   # preparacion | automatica | principal | final | terminada
    ganador: int | None = None
    motivo: str = ""
    pendiente: Pendiente | None = None
    contacto: Contacto | None = None
    log: list = field(default_factory=list)
    rng: random.Random = field(default_factory=random.Random)
    _uids: dict = field(default_factory=dict)

    def rival(self, j: int) -> int:
        return 1 - j

    def carta(self, uid: int) -> Carta:
        return self._uids[uid]

    def registrar(self, c: Carta):
        self._uids[c.uid] = c

    def quien_decide(self) -> int:
        return self.pendiente.jugador if self.pendiente else self.activo
