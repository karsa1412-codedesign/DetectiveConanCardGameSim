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
HASTA_AURA = "aura"          # efectos permanentes: el motor los recalcula tras cada paso


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
    boca_arriba: bool = False   # solo para Pruebas: 表向きの証拠
    por_efecto: bool = False    # entró en escena por una habilidad o un efecto

    @property
    def ap(self) -> int:
        return max(0, self.defn.ap + sum(m.valor for m in self.mods if m.campo == "ap"))

    @property
    def lp(self) -> int:
        return max(0, self.defn.lp + sum(m.valor for m in self.mods if m.campo == "lp"))

    @property
    def nivel(self) -> int:
        return max(0, self.defn.nivel + sum(m.valor for m in self.mods if m.campo == "nivel"))

    def claves_extra(self) -> dict:
        """Palabras clave dadas por efectos (Mod campo «clave:<nombre>»)."""
        out = {}
        for m in self.mods:
            if m.campo.startswith("clave:"):
                out[m.campo[6:]] = m.valor
        return out

    def rasgos_extra(self) -> list:
        return [m.campo[6:] for m in self.mods if m.campo.startswith("rasgo:")]

    def marca(self, nombre: str) -> bool:
        return any(m.campo == "marca:" + nombre for m in self.mods)

    def limpiar(self):
        """Al cambiar de zona la carta olvida estado y modificadores."""
        self.estado = ACTIVO
        self.turno_entrada = -1
        self.mods.clear()
        self.boca_arriba = False
        self.por_efecto = False

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
    sin_pista: bool = False         # «このターン中、自分はネクストヒントできない»
    entradas_turno: int = 0         # Personajes que han entrado este turno (para 【疾風】)

    @property
    def cartas_file(self) -> int:
        """Cartas en FILE contando al Compañero si ha Asistido (p. 11)."""
        return len(self.file) + (1 if self.companero_en_file else 0)


@dataclass
class Pendiente:
    """Decisión que la partida espera de un jugador concreto."""
    tipo: str        # mulligan | pista_jugar | pista_falsa | guardia | contacto | efecto
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
class Disparo:
    """Habilidad que se ha disparado y espera a resolverse (p. 22)."""
    uid: int           # carta que tiene la habilidad
    indice: int        # línea de la habilidad
    jugador: int       # quien la controla
    ctx: dict = field(default_factory=dict)
    opcional: bool = False   # 【ヒラメキ】: su dueño decide si se aplica


@dataclass
class Ejecucion:
    """Habilidad o efecto que se está resolviendo paso a paso."""
    fuente: int        # uid de la carta
    jugador: int
    pasos: list
    titulo: str = ""
    i: int = 0
    ctx: dict = field(default_factory=dict)


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
    cola: list = field(default_factory=list)       # Disparo pendientes
    pila: list = field(default_factory=list)       # Ejecucion en curso (la última es la activa)
    diferida: tuple | None = None                  # qué hacer cuando terminen los efectos
    usos: dict = field(default_factory=dict)       # (uid, línea) -> veces este turno
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
