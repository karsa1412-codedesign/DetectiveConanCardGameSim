"""Definición de las cartas (los datos fijos que vienen impresos en la carta)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

PERSONAJE = "personaje"
EVENTO = "evento"
COMPANERO = "companero"
CASO = "caso"
TIPOS = (PERSONAJE, EVENTO, COMPANERO, CASO)

# Palabras clave del reglamento (p. 25). Las que llevan número guardan su valor.
RAPIDEZ = "rapidez"            # 迅速
ASALTO = "asalto"              # 突撃
ASALTO_PERSONAJE = "asalto_personaje"  # 突撃[キャラ]
ASALTO_CASO = "asalto_caso"    # 突撃[事件]
BALA = "bala"                  # ブレット
PISTA_FALSA = "pista_falsa"    # ミスリードX
INVESTIGACION = "investigacion"  # 捜査X
RASTRO = "rastro"              # 痕跡


@dataclass
class CartaDef:
    id: str
    nombre: dict                 # {"ja": "...", "es": "...", "ca": "..."}
    tipo: str
    colores: tuple = ()
    nivel: int = 0
    ap: int = 0
    lp: int = 0
    rasgos: tuple = ()
    nivel_caso: tuple = (0, 0)   # (si juegas primero, si juegas segundo)
    palabras_clave: dict = field(default_factory=dict)
    irrupcion_ap: int | None = None   # カットイン AP+X
    disfraz: bool = False             # 変装
    inspiracion: bool = False         # ヒラメキ
    mr: bool = False
    texto: dict = field(default_factory=dict)
    rareza: str = ""
    imagen: str = ""
    id_regla: str = ""        # ID de reglas: las versiones paralelas comparten ID (p. 7)
    limite: int = 3           # copias máximas por ID de reglas
    paquete: str = ""
    imagen_url: str = ""
    rasgos_ja: tuple = ()
    rasgos_trad: dict = field(default_factory=dict)   # {idioma: [rasgos traducidos]}

    def __post_init__(self):
        if not self.id_regla:
            self.id_regla = self.id

    def nombre_en(self, idioma: str = "es") -> str:
        return self.nombre.get(idioma) or self.nombre.get("es") or self.nombre.get("ja") or self.id

    def rasgos_en(self, idioma: str = "es") -> list:
        return list(self.rasgos_trad.get(idioma) or self.rasgos_trad.get("es") or self.rasgos or self.rasgos_ja)

    def texto_en(self, idioma: str = "es") -> str:
        return self.texto.get(idioma) or self.texto.get("es") or self.texto.get("ja") or ""

    def tiene(self, clave: str) -> bool:
        return clave in self.palabras_clave

    def valor(self, clave: str) -> int:
        v = self.palabras_clave.get(clave, 0)
        return v if isinstance(v, int) and not isinstance(v, bool) else 0

    @classmethod
    def desde_dict(cls, d: dict) -> "CartaDef":
        nombre = d["nombre"] if isinstance(d["nombre"], dict) else {"es": d["nombre"]}
        texto = d.get("texto", {})
        if isinstance(texto, str):
            texto = {"es": texto}
        tipo = d["tipo"]
        if tipo not in TIPOS:
            raise ValueError(f"Tipo de carta desconocido en {d['id']}: {tipo}")
        return cls(
            id=d["id"], nombre=nombre, tipo=tipo,
            colores=tuple(d.get("colores", ())), nivel=int(d.get("nivel", 0)),
            ap=int(d.get("ap", 0)), lp=int(d.get("lp", 0)),
            rasgos=tuple(d["rasgos"]) if isinstance(d.get("rasgos"), list) else (),
            rasgos_trad=d["rasgos"] if isinstance(d.get("rasgos"), dict) else {},
            nivel_caso=tuple(d.get("nivel_caso", (0, 0))),
            palabras_clave=dict(d.get("palabras_clave", {})),
            irrupcion_ap=d.get("irrupcion_ap"), disfraz=bool(d.get("disfraz", False)),
            inspiracion=bool(d.get("inspiracion", False)), mr=bool(d.get("mr", False)),
            texto=texto, rareza=d.get("rareza", ""), imagen=d.get("imagen", ""),
            id_regla=d.get("id_regla", ""), limite=int(d.get("limite", 3) or 3),
            paquete=d.get("paquete", ""), imagen_url=d.get("imagen_url", ""),
            rasgos_ja=tuple(d.get("rasgos_ja", ())),
        )


class Catalogo:
    """Todas las cartas conocidas, por ID."""

    def __init__(self, cartas: list[CartaDef]):
        self.por_id = {c.id: c for c in cartas}

    @classmethod
    def cargar(cls, *rutas: str | Path) -> "Catalogo":
        """Une uno o varios archivos de cartas (los que no existan se ignoran)."""
        cartas = []
        for ruta in rutas:
            if Path(ruta).exists():
                datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
                cartas += [CartaDef.desde_dict(d) for d in datos["cartas"]]
        return cls(cartas)

    def todas(self) -> list[CartaDef]:
        return list(self.por_id.values())

    def __getitem__(self, cid: str) -> CartaDef:
        return self.por_id[cid]

    def __contains__(self, cid: str) -> bool:
        return cid in self.por_id


@dataclass
class Mazo:
    nombre: str
    companero: str
    caso: str
    cartas: dict  # {id: copias}
    descripcion: str = ""
    companeros_alternativos: list = field(default_factory=list)

    @classmethod
    def cargar(cls, ruta: str | Path) -> "Mazo":
        d = json.loads(Path(ruta).read_text(encoding="utf-8"))
        return cls(d["nombre"], d["companero"], d["caso"], dict(d["cartas"]),
                   d.get("descripcion", ""), list(d.get("companeros_alternativos", [])))

    def a_dict(self) -> dict:
        d = {"nombre": self.nombre, "companero": self.companero, "caso": self.caso, "cartas": self.cartas}
        if self.descripcion:
            d["descripcion"] = self.descripcion
        if self.companeros_alternativos:
            d["companeros_alternativos"] = self.companeros_alternativos
        return d

    def guardar(self, ruta: str | Path):
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        Path(ruta).write_text(json.dumps(self.a_dict(), ensure_ascii=False, indent=1), encoding="utf-8")

    def total(self) -> int:
        return sum(self.cartas.values())

    def validar(self, cat: Catalogo) -> list[str]:
        """Reglas de construcción (p. 7). Devuelve la lista de errores; vacía = válido."""
        err = []
        if self.companero not in cat or cat[self.companero].tipo != COMPANERO:
            err.append("El Compañero no existe o no es de tipo Compañero.")
        if self.caso not in cat or cat[self.caso].tipo != CASO:
            err.append("El Caso no existe o no es de tipo Caso.")
        total = sum(self.cartas.values())
        if total != 40:
            err.append(f"El mazo debe tener exactamente 40 cartas (tiene {total}).")
        por_regla: dict[str, int] = {}
        for cid, n in self.cartas.items():
            if cid not in cat:
                err.append(f"Carta desconocida: {cid}.")
                continue
            if cat[cid].tipo not in (PERSONAJE, EVENTO):
                err.append(f"{cid} no puede ir en el mazo (solo Personajes y Eventos).")
            por_regla[cat[cid].id_regla] = por_regla.get(cat[cid].id_regla, 0) + n
        for regla, n in por_regla.items():
            limite = max(cat[c].limite for c in self.cartas if c in cat and cat[c].id_regla == regla)
            if n > limite:
                err.append(f"ID {regla}: máximo {limite} copias contando versiones paralelas (hay {n}).")
        return err

    def lista(self) -> list[str]:
        return [cid for cid, n in self.cartas.items() for _ in range(n)]
