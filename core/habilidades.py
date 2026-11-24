"""Intérprete de habilidades: convierte el texto japonés oficial de cada carta en reglas.

Cada línea de texto es una habilidad (reglamento p. 14 y 21-25):
  · prefijo de iconos: tipo (【宣言】, 【登場時】, 【疾風】...), condiciones (【パートナー青】,
    【事件X】, 【絆X】, 【FILE5】, 【解決編】, 【自分ターン中】...), límite (【ターン1】) y el coste
    【スリープ】;
  · coste escrito antes de «：» (〚手札を1枚リムーブする〛...);
  · efecto: frases que se traducen a una lista de «pasos». Cada paso es una operación del motor
    (core/efectos.py) con una función propia. Lo que no se reconoce queda como paso «manual»:
    se muestra el texto y el jugador lo aplica con las herramientas del tablero.

El resultado no depende de la interfaz ni del idioma de la traducción: se calcula una vez por
carta y se guarda en caché.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from .cartas import (ASALTO, ASALTO_CASO, ASALTO_PERSONAJE, BALA, EVENTO, PISTA_FALSA, RAPIDEZ,
                     CartaDef)

COLORES_JA = {"青": "azul", "赤": "rojo", "緑": "verde", "黄": "amarillo", "白": "blanco",
              "黒": "negro", "紫": "morado", "桃": "rosa"}
_ANCHO = str.maketrans("０１２３４５６７８９＋－", "0123456789+-")

# clases de habilidad
DECLARAR = "declarar"          # 【宣言】 (p. 14)
ENTRADA = "entrada"            # 【登場時】
RAFAGA = "rafaga"              # 【疾風】
SALIDA = "salida"              # 【現場リムーブ時】
ENTRADA_DISFRAZ = "entrada_disfraz"  # 【変装時】
INSPIRACION = "inspiracion"    # 【ヒラメキ】
IRRUPCION = "irrupcion"        # 【カットイン】
DISFRAZ = "disfraz"            # 【変装】 (lo gestiona el Contacto)
NUCLEO = "nucleo"              # 【事件解決】/【アシスト】 de los Compañeros (acciones básicas)
CASO_RESOLUCION = "caso_resolucion"  # «この事件が解決編になったとき»
DISPARO = "disparo"            # «このキャラが…したとき» y similares
EVENTO_EFECTO = "evento"       # texto principal de una carta de Evento
CLAVE = "clave"                # línea que solo da palabras clave (〚突撃〛...)
CONTINUA = "continua"          # efecto permanente que el motor calcula (AP, rasgos...)
INFO = "info"                  # permanente que aún no se calcula: se muestra como recordatorio

# momentos de los disparos genéricos
EV_DEDUCE = "deduce"
EV_ACCION = "accion"
EV_DEDUCE_O_ACCION = "deduce_o_accion"
EV_GANA_CONTACTO = "gana_contacto"
EV_GUARDIA = "guardia"
EV_FIN_TURNO = "fin_turno"
EV_CONTACTO = "contacto"
EV_ACCION_PERSONAJE = "accion_personaje"
EV_ACCION_CASO = "accion_caso"
EV_RIVAL_RETIRADO = "rival_retirado"
EV_CONTACTO_MAYOR = "contacto_mayor"

CLAVES_JA = [
    (r"〚突撃\s*［キャラ］〛", ASALTO_PERSONAJE), (r"〚突撃\s*［事件］〛", ASALTO_CASO),
    (r"〚突撃〛", ASALTO), (r"〚迅速〛", RAPIDEZ), (r"〚ブレット〛", BALA),
    (r"〚ミスリード\s*(\d+)〛", PISTA_FALSA),
]


@dataclass
class Habilidad:
    indice: int
    texto: str                    # línea original (japonés)
    clase: str
    evento: str = ""              # para DISPARO
    condiciones: list = field(default_factory=list)
    limite: int | None = None     # usos por turno
    coste_dormir: bool = False
    coste: list = field(default_factory=list)     # pasos de coste
    pasos: list = field(default_factory=list)     # pasos de efecto
    declarable_si: list = field(default_factory=list)
    zona_companero: bool = False  # «パートナーエリアでも宣言できる/発動する»
    claves: dict = field(default_factory=dict)    # CLAVE: {clave: valor}
    continuas: list = field(default_factory=list)  # CONTINUA: [paso]
    irrupcion: dict = field(default_factory=dict)  # IRRUPCION: {"ap", "alt": (nombre, ap), "solo": nombre}
    fijada: bool = False          # la tiene el Personaje al que está fijado este Evento

    @property
    def automatica(self) -> bool:
        """True si el motor sabe aplicar todo lo que dice."""
        if self.clase == INFO:
            return False
        return not any(p["op"] == "manual" for p in self.coste + self.pasos)

    @property
    def es_disparada(self) -> bool:
        return self.clase in (ENTRADA, RAFAGA, SALIDA, ENTRADA_DISFRAZ, INSPIRACION, CASO_RESOLUCION, DISPARO)


# ------------------------------------------------------------------ utilidades de texto

def normalizar(s: str) -> str:
    s = s.translate(_ANCHO)
    s = re.sub(r"（[^（）]*）", "", s)    # texto recordatorio
    s = re.sub(r"\([^()]*\)", "", s)
    return s.strip()


def _n(s: str | None, defecto: int = 1) -> int:
    return int(s) if s else defecto


def _nombres(s: str) -> list[str]:
    return re.findall(r"(?:〚(?:カード名)?|カード名)［([^］]*)］", s)


# ------------------------------------------------------------------ iconos

_ICONO_TIPO = {"宣言": DECLARAR, "登場時": ENTRADA, "疾風": RAFAGA, "現場リムーブ時": SALIDA,
               "変装時": ENTRADA_DISFRAZ, "ヒラメキ": INSPIRACION, "カットイン": IRRUPCION,
               "変装": DISFRAZ, "事件解決": NUCLEO, "アシスト": NUCLEO, "証拠隠滅": DECLARAR}


def _icono(txt: str, h: Habilidad) -> bool:
    """Interpreta un icono del prefijo. False si no es un icono de prefijo (p. ej. 【青】)."""
    t = txt.translate(_ANCHO)
    if t in _ICONO_TIPO:
        if h.clase in ("", NUCLEO) or t != "証拠隠滅":
            h.clase = _ICONO_TIPO[t]
        return True
    if t == "スリープ":
        h.coste_dormir = True
        return True
    m = re.fullmatch(r"ターン(\d+)", t)
    if m:
        h.limite = int(m.group(1))
        return True
    m = re.fullmatch(r"パートナー(.+)", t)
    if m:
        h.condiciones.append(("companero_color", [COLORES_JA.get(c, c) for c in m.group(1)]))
        return True
    m = re.fullmatch(r"事件(.+)", t)
    if m and t not in ("事件編",):
        partes = m.group(1).split("＆")
        if all(p in COLORES_JA for p in partes):
            h.condiciones.append(("caso_colores", [COLORES_JA[p] for p in partes]))
        else:
            h.condiciones.append(("caso_rasgo", m.group(1)))
        return True
    m = re.fullmatch(r"絆(.+)", t)
    if m:
        h.condiciones.append(("vinculo", m.group(1)))
        return True
    m = re.fullmatch(r"FILE(\d+)", t)
    if m:
        h.condiciones.append(("file", int(m.group(1))))
        return True
    m = re.fullmatch(r"(\d+)枚以上", t)
    if m:
        h.condiciones.append(("debajo", int(m.group(1))))
        return True
    simples = {"解決編": ("resolucion", True), "事件編": ("resolucion", False),
               "自分ターン中": ("turno", "propio"), "相手ターン中": ("turno", "rival")}
    if t in simples:
        h.condiciones.append(simples[t])
        return True
    return False


# ------------------------------------------------------------------ filtros de cartas

_FILTRO_TOKENS = [
    (r"このキャラ以外の", lambda m, f: f.__setitem__("no_esta", True)),
    (r"このイベント以外の", lambda m, f: f.__setitem__("no_esta", True)),
    (r"レベル(\d+)以下の", lambda m, f: f.__setitem__("nivel_max", int(m.group(1)))),
    (r"レベル(\d+)以上の", lambda m, f: f.__setitem__("nivel_min", int(m.group(1)))),
    (r"レベル(\d+)か(\d+)の", lambda m, f: f.__setitem__("niveles", [int(m.group(1)), int(m.group(2))])),
    (r"レベル(\d+)の", lambda m, f: f.__setitem__("niveles", [int(m.group(1))])),
    (r"自分のFILEエリアの枚数以下のレベルの", lambda m, f: f.__setitem__("nivel_max_file", True)),
    (r"このキャラのAP以下のAPの", lambda m, f: f.__setitem__("ap_max_esta", True)),
    (r"AP(\d+)以下の", lambda m, f: f.__setitem__("ap_max", int(m.group(1)))),
    (r"AP(\d+)以上の", lambda m, f: f.__setitem__("ap_min", int(m.group(1)))),
    (r"LP(\d+)の", lambda m, f: f.__setitem__("lp", int(m.group(1)))),
    (r"LP(\d+)以上の", lambda m, f: f.__setitem__("lp_min", int(m.group(1)))),
    (r"スリープ状態の", lambda m, f: f.__setitem__("estado", "dormido")),
    (r"アクティブ状態の", lambda m, f: f.__setitem__("estado", "activo")),
    (r"スタン状態の", lambda m, f: f.__setitem__("estado", "aturdido")),
    (r"【カットイン】を持つ", lambda m, f: f.__setitem__("irrupcion", True)),
    (r"((?:【[青赤緑黄白黒紫桃]】か?)+)以外の色を持つ",
     lambda m, f: f.__setitem__("sin_colores", [COLORES_JA[c] for c in re.findall(r"【(.)】", m.group(1))])),
    (r"((?:【[青赤緑黄白黒紫桃]】か?)+)の",
     lambda m, f: f.__setitem__("colores", [COLORES_JA[c] for c in re.findall(r"【(.)】", m.group(1))])),
    (r"((?:〚特徴［[^］]*］〛|特徴［[^］]*］)(?:か(?:〚特徴［[^］]*］〛|特徴［[^］]*］))*)(?:の|か)",
     lambda m, f: f.__setitem__("rasgos", re.findall(r"［([^］]*)］", m.group(1)))),
    (r"((?:〚(?:カード名)?［[^］]*］〛|カード名［[^］]*］)(?:か(?:〚(?:カード名)?［[^］]*］〛|カード名［[^］]*］))*)以外の",
     lambda m, f: f.__setitem__("no_nombres", _nombres(m.group(1)))),
    (r"((?:〚(?:カード名)?［[^］]*］〛|カード名［[^］]*］)(?:か(?:〚(?:カード名)?［[^］]*］〛|カード名［[^］]*］))*)(?:の|か)?",
     lambda m, f: f.__setitem__("nombres", _nombres(m.group(1)))),
]
_NUCLEOS = [("のキャラ", "personaje"), ("キャラ", "personaje"), ("のイベント", "evento"),
            ("イベント", "evento"), ("のカード", "carta"), ("カード", "carta")]


def filtro(frase: str) -> dict | None:
    """«レベル6以下の〚カード名［毛利蘭］〛のキャラ» → {"nivel_max": 6, "nombres": [...], "tipo": ...}.
    None si queda algo sin entender."""
    f: dict = {}
    s = frase
    for _ in range(12):
        if not s:
            break
        for pat, fn in _FILTRO_TOKENS:
            m = re.match(pat, s)
            if m and m.end() > 0:
                fn(m, f)
                s = s[m.end():]
                break
        else:
            break
    for suf, tipo in _NUCLEOS:
        if s == suf:
            f["tipo"] = tipo
            return f
    if s == "" and "nombres" in f:
        f["tipo"] = "carta"     # solo el nombre: Personaje o Evento según la zona
        return f
    return None


# ------------------------------------------------------------------ zonas

_ZONAS = [
    ("自分の現場にいる", ("escena", "propio")), ("相手の現場にいる", ("escena", "rival")),
    ("自分か相手の現場にいる", ("escena", "ambos")),
    ("自分のリムーブエリアにある", ("descarte", "propio")), ("相手のリムーブエリアにある", ("descarte", "rival")),
    ("自分のパートナーエリアにある", ("zona_companero", "propio")),
    ("自分の表向きの証拠", ("pruebas_arriba", "propio")), ("自分の裏向きの証拠", ("pruebas_abajo", "propio")),
    ("相手の表向きの証拠", ("pruebas_arriba", "rival")), ("相手の裏向きの証拠", ("pruebas_abajo", "rival")),
    ("自分の証拠", ("pruebas", "propio")), ("相手の証拠", ("pruebas", "rival")),
    ("手札から", ("mano", "propio")), ("自分の手札から", ("mano", "propio")),
]


def _zona(s: str):
    for pre, z in _ZONAS:
        if s.startswith(pre):
            return z, s[len(pre):]
    return ("escena", "ambos"), s


# ------------------------------------------------------------------ verbos de «選び、…»

_HASTA = r"(?:ターン終了時まで|相手のターン終了時まで)?"


def _verbo(v: str) -> dict | None:
    hasta = "turno" if v.startswith(("ターン終了時まで", "相手のターン終了時まで")) else ""
    simples = {
        "スリープさせる": {"accion": "dormir"}, "スタンさせる": {"accion": "aturdir"},
        "アクティブにする": {"accion": "activar"}, "リムーブする": {"accion": "retirar"},
        "デッキの下に移す": {"accion": "fondo_mazo"}, "手札に移す": {"accion": "a_mano"},
        "手札に加える": {"accion": "a_mano"}, "手札に加えてもよい": {"accion": "a_mano"},
        "登場させる": {"accion": "entrar"}, "スリープ状態で登場させる": {"accion": "entrar", "dormido": True},
        "パートナーエリアに移す": {"accion": "a_zona_companero"}, "表向きにする": {"accion": "boca_arriba"},
        "裏向きにする": {"accion": "boca_abajo"}, "このキャラの下に重ねる": {"accion": "debajo_esta"},
        "使用する": {"accion": "usar"}, "リムーブエリアに移す": {"accion": "retirar"},
    }
    if v in simples:
        return dict(simples[v])
    m = re.fullmatch(_HASTA + r"(AP|LP|レベル)([+-])(\d+)する", v)
    if m:
        campo = {"AP": "ap", "LP": "lp", "レベル": "nivel"}[m.group(1)]
        val = int(m.group(3)) * (1 if m.group(2) == "+" else -1)
        return {"accion": "mod", "campo": campo, "valor": val, "hasta": hasta or "turno"}
    m = re.fullmatch(_HASTA + r"(AP|LP)([+-])(\d+)するか、" + _HASTA + r"(AP|LP)([+-])(\d+)する", v)
    if m:
        return {"accion": "mod_o", "opciones": [
            {"campo": m.group(1).lower(), "valor": int(m.group(3)) * (1 if m.group(2) == "+" else -1)},
            {"campo": m.group(4).lower(), "valor": int(m.group(6)) * (1 if m.group(5) == "+" else -1)}]}
    m = re.fullmatch(_HASTA + r"((?:〚[^〛]*〛)+)を与える", v)
    if m:
        cl = _claves(m.group(1))
        if cl:
            return {"accion": "dar_claves", "claves": cl, "hasta": "turno"}
    m = re.fullmatch(r"この【宣言】能力のコストで表向きにした証拠1つにつき、ターン終了時まで(AP|LP)([+-])(\d+)する", v)
    if m:
        return {"accion": "mod", "campo": m.group(1).lower(), "hasta": "turno", "por_coste": True,
                "valor": int(m.group(3)) * (1 if m.group(2) == "+" else -1)}
    m = re.fullmatch(r"(自分|相手)のデッキのカードを上から(\d+)枚裏向きでセットする", v)
    if m:
        return {"accion": "poner_debajo", "n": int(m.group(2)), "de": "rival" if m.group(1) == "相手" else "propio"}
    return None


def _claves(s: str) -> dict:
    out = {}
    resto = s
    for pat, clave in CLAVES_JA:
        for m in re.finditer(pat, resto):
            out[clave] = int(m.group(1)) if m.groups() else True
        resto = re.sub(pat, "", resto)
    if re.sub(r"[、\s]", "", resto):
        return {}
    return out


# ------------------------------------------------------------------ condiciones en frases

def _condicion(s: str) -> tuple | None:
    """Texto antes de «場合» → condición evaluable por el motor."""
    c = _condicion_exacta(s)
    if c is None and s.endswith("の"):
        c = _condicion_exacta(s[:-1])
    return c


def _condicion_exacta(s: str) -> tuple | None:
    pats = [
        (r"自分の現場に(?:このキャラ以外の)?(.+?)が(?:(\d+)枚以上)?いる",
         lambda m: ("hay_en_escena", "propio", m.group(1), _n(m.group(2)), "このキャラ以外の" in m.group(0))),
        (r"相手の現場に(.+?)が(?:(\d+)枚以上)?いる",
         lambda m: ("hay_en_escena", "rival", m.group(1), _n(m.group(2)), False)),
        (r"自分の現場に(.+?)がいない", lambda m: ("no_hay_en_escena", "propio", m.group(1))),
        (r"自分の事件が解決編", lambda m: ("resolucion", True)),
        (r"自分の事件が事件編", lambda m: ("resolucion", False)),
        (r"相手の証拠が(\d+)つ以上ある", lambda m: ("pruebas", "rival", int(m.group(1)))),
        (r"自分の証拠が(\d+)つ以上ある", lambda m: ("pruebas", "propio", int(m.group(1)))),
        (r"自分の手札が(\d+)枚以上ある", lambda m: ("mano", int(m.group(1)), "min")),
        (r"自分の手札が(\d+)枚以下", lambda m: ("mano", int(m.group(1)), "max")),
        (r"自分のFILEエリアにあるカードが(\d+)枚以下", lambda m: ("file_max", int(m.group(1)))),
        (r"自分のFILEエリアにあるカードが(\d+)枚以上", lambda m: ("file", int(m.group(1)))),
        (r"自分のリムーブエリアに(.+?)が(\d+)枚以上ある", lambda m: ("en_descarte", m.group(1), int(m.group(2)))),
        (r"自分の事件が((?:【.】)+)以外の色を持たない",
         lambda m: ("caso_solo_colores", [COLORES_JA[c] for c in re.findall(r"【(.)】", m.group(1))])),
        (r"〚痕跡［未発見］〛", lambda m: ("rastro", False)),
        (r"〚痕跡［発見済み］〛", lambda m: ("rastro", True)),
        (r"カードを手札に加えた", lambda m: ("hecho",)),
        (r"(?:キャラを)?登場させた", lambda m: ("hecho",)),
        (r"重ねた", lambda m: ("hecho",)),
        (r"(〚[^〛]*〛)を登場させた", lambda m: ("hecho_nombre", filtro(m.group(1)) or {})),
        (r"レベル(\d+)以上のカードを手札に加えた", lambda m: ("hecho_nivel", int(m.group(1)))),
        (r"自分のキャラの能力によって登場した", lambda m: ("por_efecto",)),
        (r"公開したカードが(.+?)の", lambda m: ("revelada", m.group(1))),
    ]
    for pat, fn in pats:
        m = re.fullmatch(pat, s)
        if m:
            c = fn(m)
            if c[0] in ("hay_en_escena", "no_hay_en_escena"):
                f = filtro(c[2])
                if f is None:
                    return None
                c = c[:2] + (f,) + c[3:]
            elif c[0] == "en_descarte":
                f = filtro(c[1])
                if f is None:
                    return None
                c = (c[0], f, c[2])
            if c[0] == "revelada":
                f = filtro(c[1])
                if f is None:
                    return None
                c = ("revelada", f)
            return c
    return None


# ------------------------------------------------------------------ frases de efecto

def _frase(s: str) -> list[dict] | None:
    """Una frase (sin «。») → lista de pasos, o None si no se entiende."""
    s = s.strip()
    if not s:
        return []
    m = re.fullmatch(r"そうした場合、(.*)", s)
    if m:
        pasos = _frase(m.group(1))
        if pasos is None:
            return None
        for p in pasos:
            p.setdefault("si", []).append(("hecho",))
        return pasos
    m = re.fullmatch(r"(.+?)場合、(.*)", s)
    if m:
        cond = _condicion(m.group(1))
        if cond is not None:
            pasos = _frase(m.group(2))
            if pasos is None:
                return None
            for p in pasos:
                p.setdefault("si", []).append(cond)
            return pasos
    # opcional: «…してもよい» → pregunta sí/no y, si se acepta, el efecto
    if s.endswith("てもよい"):
        base = s[:-len("てもよい")]
        for viejo, nuevo in (("させ", "させる"), ("移し", "移す"), ("引い", "引く"), ("し", "する"),
                             ("え", "える"), ("け", "ける"), ("せ", "せる")):
            if base.endswith(viejo):
                pasos = _frase(base[:-len(viejo)] + nuevo)
                if pasos:
                    return [{"op": "preguntar", "texto": s}] + [
                        dict(p, si=p.get("si", []) + [("hecho",)]) for p in pasos]
                return None
        return None
    for fn in _PATRONES:
        r = fn(s)
        if r is not None:
            return r
    return None


def _p_simple(s: str):
    reglas = [
        (r"(?:自分は)?カードを(\d+)枚引く", lambda m: [{"op": "robar", "n": int(m.group(1))}]),
        (r"相手はカードを(\d+)枚引く", lambda m: [{"op": "robar", "n": int(m.group(1)), "quien": "rival"}]),
        (r"カードを(\d+)枚引き、手札を(\d+)枚リムーブする",
         lambda m: [{"op": "robar", "n": int(m.group(1))}, {"op": "descartar_mano", "n": int(m.group(2))}]),
        (r"(?:自分は)?手札を(\d+)枚リムーブする", lambda m: [{"op": "descartar_mano", "n": int(m.group(1))}]),
        (r"相手は手札を(\d+)枚リムーブする",
         lambda m: [{"op": "descartar_mano", "n": int(m.group(1)), "quien": "rival"}]),
        (r"手札から(.+?)を(\d+)枚リムーブする",
         lambda m: _con_filtro(m.group(1), lambda f: [{"op": "descartar_mano", "n": int(m.group(2)), "filtro": f}])),
        (r"(?:自分は)?証拠を(\d+)つ得る", lambda m: [{"op": "ganar_pruebas", "n": int(m.group(1))}]),
        (r"相手に証拠を(\d+)つ与える", lambda m: [{"op": "ganar_pruebas", "n": int(m.group(1)), "quien": "rival"}]),
        (r"自分のデッキのカードを上から(\d+)枚リムーブする", lambda m: [{"op": "moler", "n": int(m.group(1))}]),
        (r"相手のデッキのカードを上から(\d+)枚リムーブする",
         lambda m: [{"op": "moler", "n": int(m.group(1)), "quien": "rival"}]),
        (r"このキャラをスリープさせる", lambda m: [{"op": "esta", "accion": "dormir"}]),
        (r"このキャラをアクティブにする", lambda m: [{"op": "esta", "accion": "activar"}]),
        (r"このキャラを(?:現場から)?リムーブする", lambda m: [{"op": "esta", "accion": "retirar"}]),
        (r"自分の手札が(\d+)枚になるまでカードを引く", lambda m: [{"op": "robar_hasta", "n": int(m.group(1))}]),
        (r"すべてのキャラをスリープさせる", lambda m: [{"op": "todas", "accion": "dormir"}]),
        (r"自分のFILEエリアにあるカードを上から(\d+)枚手札に加える", lambda m: [{"op": "file_a_mano", "n": int(m.group(1))}]),
        (r"このキャラを(?:現場から)?デッキの下に移す", lambda m: [{"op": "esta", "accion": "fondo_mazo"}]),
        (r"このキャラはスリープ状態で登場する", lambda m: [{"op": "esta", "accion": "dormir"}]),
        (r"このキャラをスリープさせ、手札を(\d+)枚リムーブする",
         lambda m: [{"op": "esta", "accion": "dormir"}, {"op": "descartar_mano", "n": int(m.group(1))}]),
        (r"(?:ターン終了時まで)?このキャラを(AP|LP|レベル)([+-])(\d+)する",
         lambda m: [{"op": "esta", "accion": "mod", "campo": {"AP": "ap", "LP": "lp", "レベル": "nivel"}[m.group(1)],
                     "valor": int(m.group(3)) * (1 if m.group(2) == "+" else -1), "hasta": "turno"}]),
        (r"(?:ターン終了時まで)?このキャラは((?:〚[^〛]*〛)+)を持つ",
         lambda m: _con_claves(m.group(1), lambda cl: [{"op": "esta", "accion": "dar_claves", "claves": cl,
                                                         "hasta": "turno"}])),
        (r"ターン終了時までこのキャラを(AP)([+-])(\d+)し、((?:〚[^〛]*〛)+)を持つ",
         lambda m: _con_claves(m.group(4), lambda cl: [
             {"op": "esta", "accion": "mod", "campo": "ap",
              "valor": int(m.group(3)) * (1 if m.group(2) == "+" else -1), "hasta": "turno"},
             {"op": "esta", "accion": "dar_claves", "claves": cl, "hasta": "turno"}])),
        (r"自分のデッキのカードを上から(\d+)枚裏向きでこのキャラにセットする",
         lambda m: [{"op": "poner_debajo_esta", "n": int(m.group(1))}]),
        (r"(相手の)?ターン終了時までこのキャラは「相手の現場にいるキャラがアクションするとき、"
         r"このキャラを指定できる場合、必ず指定する。?」を持つ",
         lambda m: [{"op": "esta", "accion": "marcar", "marca": "provocar",
                     "hasta": "turno_rival" if m.group(1) else "turno"}]),
        (r"このカードを手札に加える", lambda m: [{"op": "esta", "accion": "a_mano"}]),
        (r"このカードをパートナーエリアに移す", lambda m: [{"op": "esta", "accion": "a_zona_companero"}]),
        (r"このカードを表向きのまま証拠として得る", lambda m: [{"op": "esta", "accion": "a_pruebas"}]),
        (r"相手はゲームに敗北する", lambda m: [{"op": "ganar"}]),
        (r"自分は?ゲームに勝利する", lambda m: [{"op": "ganar"}]),
        (r"デッキをシャッフルする", lambda m: [{"op": "barajar"}]),
        (r"相手は手札を公開する", lambda m: [{"op": "ver_mano_rival"}]),
        (r"このターン中、自分はネクストヒントできない", lambda m: [{"op": "sin_pista"}]),
        (r"このイベントを自分の現場にいる(.+?)(\d+)枚にセットする",
         lambda m: _con_filtro(m.group(1), lambda f: [{"op": "elegir", "zona": ("escena", "propio"), "filtro": f,
                                                       "max": int(m.group(2)), "min": int(m.group(2)),
                                                       "accion": "fijar_evento"}])),
        (r"自分のデッキのカードを下から(\d+)枚手札に加える", lambda m: [{"op": "robar_fondo", "n": int(m.group(1))}]),
        (r"自分のデッキのカードを上から(\d+)枚公開する", lambda m: [{"op": "revelar", "n": int(m.group(1))}]),
        (r"公開したカードがそれ以外の場合、(デッキの下に移す|手札に加える|リムーブする)",
         lambda m: [{"op": "revelada_destino", "destino": {"デッキの下に移す": "fondo", "手札に加える": "mano",
                                                           "リムーブする": "descarte"}[m.group(1)], "otra": True}]),
        (r"(?:それを)?手札に加える", lambda m: [{"op": "revelada_destino", "destino": "mano"}]),
    ]
    for pat, fn in reglas:
        m = re.fullmatch(pat, s)
        if m:
            return fn(m)
    return None


def _con_filtro(texto, fn):
    f = filtro(texto)
    return None if f is None else fn(f)


def _con_claves(texto, fn):
    cl = _claves(texto)
    return fn(cl) if cl else None


def _p_elegir(s: str):
    """«<zona><filtro>をN枚(まで)選び、<verbo>»."""
    m = re.fullmatch(r"(.+?)を(\d+)(?:枚|つ)(まで)?選び、(.+)", s)
    if not m:
        return None
    (zona, lado), resto = _zona(m.group(1))
    n = int(m.group(2))
    verbo = m.group(4)
    if zona.startswith("pruebas"):
        f = {"tipo": "carta"} if resto == "" else filtro(resto)
    else:
        f = filtro(resto)
    if f is None:
        return None
    extra = []
    # «…選び、自分のデッキのカードを上からN枚裏向きでセットし、ターン終了時までAP+Nする»
    mm = re.fullmatch(r"(自分のデッキのカードを上から\d+枚裏向きでセット)し、(.+)", verbo)
    if mm:
        v1, v2 = _verbo(mm.group(1) + "する"), _verbo(mm.group(2))
        if v1 is None or v2 is None:
            return None
        v = v1
        extra = [v2]
    else:
        v = _verbo(verbo)
    if v is None:
        return None
    if f.get("tipo") == "carta" and zona == "escena":
        f["tipo"] = "personaje"
    paso = {"op": "elegir", "zona": (zona, lado), "filtro": f, "max": n,
            "min": 0 if m.group(3) else n, **v}
    if extra:
        paso["despues"] = extra
    return [paso]


def _p_mano(s: str):
    """«手札から<filtro>をN枚(まで)登場させる/使用する»."""
    m = re.fullmatch(r"(?:自分の)?手札から(.+?)を(\d+)枚(まで)?(登場させる|スリープ状態で登場させる|使用する)", s)
    if not m:
        return None
    f = filtro(m.group(1))
    if f is None:
        return None
    acc = {"登場させる": "entrar", "スリープ状態で登場させる": "entrar", "使用する": "usar"}[m.group(4)]
    p = {"op": "elegir", "zona": ("mano", "propio"), "filtro": f, "max": int(m.group(2)),
         "min": 0 if m.group(3) else int(m.group(2)), "accion": acc}
    if "スリープ" in m.group(4):
        p["dormido"] = True
    return [p]


def _p_mirar(s: str):
    """«自分のデッキのカードを上からN枚見る» y lo que se hace con ellas."""
    m = re.fullmatch(r"自分のデッキのカードを上から(\d+)枚見る", s)
    if m:
        return [{"op": "mirar", "n": int(m.group(1))}]
    m = re.fullmatch(r"その中から(.+?)を(\d+)枚(まで)?(?:公開して)?手札に加え、残りを(好きな順番でデッキの下に移す|"
                     r"リムーブエリアに移す|デッキの下に移す)", s)
    if m:
        f = filtro(m.group(1))
        if f is None:
            return None
        return [{"op": "tomar_vistas", "filtro": f, "max": int(m.group(2)), "min": 0 if m.group(3) else 1,
                 "resto": "descarte" if "リムーブ" in m.group(4) else "fondo"}]
    m = re.fullmatch(r"自分のデッキのカードを上から(.+?)が出るまで1枚ずつ公開し、それを(手札に加える|登場させる)", s)
    if m:
        f = filtro(m.group(1))
        if f is None:
            return None
        return [{"op": "revelar_hasta", "filtro": f, "destino": "mano" if "手札" in m.group(2) else "escena"}]
    if s == "残りの公開したカードをデッキの下に移し、デッキをシャッフルする":
        return [{"op": "fin_revelar"}]
    return None


_PATRONES = [_p_simple, _p_elegir, _p_mano, _p_mirar, lambda s: _p_contacto(s)]


def frases(texto: str) -> list[str]:
    """Parte en frases por «。», sin cortar lo que va entre «」»."""
    out, actual, nivel = [], "", 0
    for ch in texto:
        nivel += (ch == "「") - (ch == "」")
        if ch == "。" and nivel <= 0:
            if actual.strip():
                out.append(actual.strip())
            actual = ""
        else:
            actual += ch
    if actual.strip():
        out.append(actual.strip())
    return out


def _efecto(texto: str) -> list[dict]:
    """Texto de efecto completo → pasos (lo no entendido, como paso manual)."""
    pasos: list[dict] = []
    m = re.match(r"以下から(\d+)つ選んで行う。?(.*)", texto, re.S)
    if m:
        ramas = [r.strip() for r in re.split(r"・", re.sub(r"[(（]上から順に行う[)）]", "", m.group(2))) if r.strip()]
        opciones = []
        for r in ramas:
            sub = _efecto(r)
            opciones.append({"texto": r, "pasos": sub})
        return [{"op": "modo", "n": int(m.group(1)), "opciones": opciones}]
    for frase in frases(texto):
        r = _frase(frase)
        if r is None:
            pasos.append({"op": "manual", "texto": frase.strip() + "。"})
        else:
            pasos += r
    return pasos


def _bloques(texto: str) -> list[str]:
    """«〚A〛〚B〚C〛〛» → ["A", "B〚C〛"] (respeta los 〚〛 anidados)."""
    out, nivel, actual = [], 0, ""
    for ch in texto:
        if ch == "〚":
            nivel += 1
            if nivel == 1:
                actual = ""
                continue
        elif ch == "〛":
            nivel -= 1
            if nivel == 0:
                out.append(actual)
                continue
        if nivel >= 1:
            actual += ch
    return out


def _coste(texto: str) -> list[dict]:
    """Coste de un 【宣言】 (texto entre 〚〛 antes de «：»)."""
    pasos = []
    for parte in _bloques(texto) or ([texto] if texto else []):
        parte = parte.strip()
        if not parte:
            continue
        reglas = [
            (r"手札を(\d+)枚リムーブする", lambda m: {"op": "descartar_mano", "n": int(m.group(1))}),
            (r"手札から(.+?)を(\d+)枚リムーブする",
             lambda m: (lambda f: f and {"op": "descartar_mano", "n": int(m.group(2)), "filtro": f})(filtro(m.group(1)))),
            (r"デッキのカードを上から(\d+)枚リムーブする", lambda m: {"op": "moler", "n": int(m.group(1)), "exacto": True}),
            (r"裏向きの証拠を(\d+)つ表向きにする", lambda m: {"op": "voltear_pruebas", "n": int(m.group(1))}),
            (r"裏向きの証拠を(\d+)つ以上表向きにする",
             lambda m: {"op": "voltear_pruebas", "n": int(m.group(1)), "o_mas": True}),
            (r"デッキの下に移す", lambda m: {"op": "esta", "accion": "fondo_mazo"}),
            (r"リムーブエリアに移す", lambda m: {"op": "esta", "accion": "retirar"}),
            (r"このキャラ以外の(.*?)キャラを(\d+)枚スリープさせる",
             lambda m: (lambda f: f and {"op": "elegir", "zona": ("escena", "propio"),
                                         "filtro": dict(f, no_esta=True, estado="activo"), "min": int(m.group(2)),
                                         "max": int(m.group(2)), "accion": "dormir"})(
                 filtro((m.group(1) or "") + "キャラ") if m.group(1) else {"tipo": "personaje"})),
            (r"(?:自分の)?現場にいる(.*?)キャラを(\d+)枚(リムーブする|デッキの下に移す)",
             lambda m: (lambda f: f and {"op": "elegir", "zona": ("escena", "propio"), "filtro": f,
                                         "min": int(m.group(2)), "max": int(m.group(2)),
                                         "accion": "retirar" if "リムーブ" in m.group(3) else "fondo_mazo"})(
                 filtro((m.group(1) or "") + "キャラ") if m.group(1) else {"tipo": "personaje"})),
            (r"(?:自分の)?リムーブエリアにある(.*?)を(\d+)枚デッキの下に移す",
             lambda m: (lambda f: f and {"op": "elegir", "zona": ("descarte", "propio"), "filtro": f,
                                         "min": int(m.group(2)), "max": int(m.group(2)), "accion": "fondo_mazo"})(
                 filtro(m.group(1)))),
            (r"証拠を事件レベルの数だけリムーブする", lambda m: {"op": "perder_pruebas_nivel"}),
            (r"FILEエリアにあるカードを上から(\d+)枚リムーブする",
             lambda m: {"op": "perder_file", "n": int(m.group(1))}),
            (r"このキャラに裏向きでセットされているカードを(\d+)枚リムーブする",
             lambda m: {"op": "quitar_debajo_esta", "n": int(m.group(1))}),
        ]
        for pat, fn in reglas:
            m = re.fullmatch(pat, parte.translate(_ANCHO))
            if m:
                r = fn(m)
                if r:
                    pasos.append(r)
                    break
        else:
            pasos.append({"op": "manual", "texto": parte})
    return pasos


# ------------------------------------------------------------------ línea completa

_DISPAROS = [
    (r"このキャラが推理かアクションしたとき、", EV_DEDUCE_O_ACCION),
    (r"このキャラが推理したとき、", EV_DEDUCE),
    (r"このキャラがアクションしたとき、", EV_ACCION),
    (r"相手の現場にいるキャラがこのキャラとのコンタクトによってリムーブされたとき、", EV_GANA_CONTACTO),
    (r"このキャラが指定されたアクションをガードしたとき、", EV_GUARDIA),
    (r"自分のターン終了時、", EV_FIN_TURNO),
    (r"このキャラがアクション［キャラ］したとき、", EV_ACCION_PERSONAJE),
    (r"このキャラがアクション［事件］したとき、", EV_ACCION_CASO),
    (r"このキャラがコンタクトしたとき、", EV_CONTACTO),
    (r"このキャラが、このキャラよりAPの高いキャラとコンタクトしたとき、", EV_CONTACTO_MAYOR),
    (r"相手の現場にいるキャラがコンタクトによってリムーブされたとき、", EV_RIVAL_RETIRADO),
]


def interpretar_linea(linea: str, indice: int, tipo_carta: str) -> Habilidad:
    h = Habilidad(indice, linea, "")
    t = linea.strip()
    while True:
        m = re.match(r"【([^】]*)】", t)
        if not m or not _icono(m.group(1), h):
            break
        t = t[m.end():]
    cuerpo = t
    if h.clase == NUCLEO:
        return h
    if h.clase == DISFRAZ:
        return h
    if h.clase == IRRUPCION:
        return _irrupcion(h, normalizar(cuerpo))
    # coste de 【宣言】: «〚…〛：» o solo «：»
    if h.clase == DECLARAR:
        m = re.match(r"^((?:〚[^〛]*(?:〚[^〛]*〛[^〛]*)*〛)*)：", cuerpo)
        if m:
            h.coste = _coste(m.group(1))
            cuerpo = cuerpo[m.end():]
    texto = normalizar(cuerpo)
    # notas de uso al final
    for pat, fn in [
        (r"この能力はパートナーエリアでも(?:宣言できる|発動する)。?", lambda m: setattr(h, "zona_companero", True)),
        (r"この能力は(.+?)場合に宣言できる。?",
         lambda m: h.declarable_si.append(_condicion(m.group(1)) or ("desconocida", m.group(1)))),
    ]:
        mm = re.search(pat, texto)
        if mm:
            fn(mm)
            texto = (texto[:mm.start()] + texto[mm.end():]).strip()
    if not h.clase:
        if re.match(r"この事件が解決編(?:になった|に移行した)とき、", texto):
            h.clase = CASO_RESOLUCION
            texto = re.sub(r"^この事件が解決編(?:になった|に移行した)とき、", "", texto)
        else:
            for pat, ev in _DISPAROS:
                if texto.startswith(pat.replace("\\", "")) or re.match(pat, texto):
                    h.clase, h.evento = DISPARO, ev
                    texto = re.sub("^" + pat, "", texto)
                    break
    if not h.clase:
        cl = _claves(texto) if texto else {}
        if cl:
            h.clase, h.claves = CLAVE, cl
            return h
        m = re.fullmatch(r"このイベントがセットされているキャラは「(.+)」を持つ。?", texto)
        if m and tipo_carta == EVENTO:
            interna = interpretar_linea(m.group(1), indice, "personaje")
            interna.texto, interna.condiciones = linea, h.condiciones + interna.condiciones
            interna.fijada = True
            return interna
        if tipo_carta == EVENTO:
            h.clase = EVENTO_EFECTO
        else:
            cont = _continua(texto)
            if cont is not None:
                h.clase, h.continuas = CONTINUA, cont
            else:
                h.clase = INFO
            return h
    # «【1枚以上】AP+1000、〚突撃［キャラ］〛» y similares: claves/ajustes condicionados
    if h.clase in ("",):
        return h
    h.pasos = _efecto(texto)
    # 【宣言】 de los Compañeros / Casos: el coste «スリープ» se aplica a la propia carta
    return h


def _continua(texto: str) -> list | None:
    """Efectos permanentes sencillos que el motor recalcula siempre."""
    out = []
    partes = [p for p in re.split(r"、|。", texto) if p]
    for p in partes:
        m = re.fullmatch(r"(AP|LP)([+-])(\d+)", p)
        if m:
            out.append({"op": "mod_esta", "campo": m.group(1).lower(),
                        "valor": int(m.group(3)) * (1 if m.group(2) == "+" else -1)})
            continue
        cl = _claves(p)
        if cl:
            out.append({"op": "claves_esta", "claves": cl})
            continue
        m = re.fullmatch(r"現場にいるこのキャラを(レベル|AP|LP)([+-])(\d+)する", p)
        if m:
            out.append({"op": "mod_esta", "campo": {"レベル": "nivel", "AP": "ap", "LP": "lp"}[m.group(1)],
                        "valor": int(m.group(3)) * (1 if m.group(2) == "+" else -1)})
            continue
        m = re.fullmatch(r"自分の現場にいる(.+?)を(AP|LP)([+-])(\d+)する", p)
        if m:
            f = filtro(m.group(1))
            if f is None:
                return None
            out.append({"op": "mod_aura", "filtro": f, "campo": m.group(2).lower(),
                        "valor": int(m.group(4)) * (1 if m.group(3) == "+" else -1)})
            continue
        m = re.fullmatch(r"自分の現場に(.+?)が(?:(\d+)枚以上)?いる場合、このキャラを(AP|LP)([+-])(\d+)する", p)
        if m:
            c = _condicion(f"自分の現場に{m.group(1)}が{(m.group(2) + '枚以上') if m.group(2) else ''}いる")
            if c is None:
                return None
            out.append({"op": "mod_esta", "campo": m.group(3).lower(), "si": [c],
                        "valor": int(m.group(5)) * (1 if m.group(4) == "+" else -1)})
            continue
        m = re.fullmatch(r"自分の現場に(.+?)が(?:(\d+)枚以上)?いる場合、このキャラは((?:〚[^〛]*〛)+)を持つ", p)
        if m:
            c = _condicion(f"自分の現場に{m.group(1)}が{(m.group(2) + '枚以上') if m.group(2) else ''}いる")
            cl = _claves(m.group(3))
            if c is None or not cl:
                return None
            out.append({"op": "claves_esta", "claves": cl, "si": [c]})
            continue
        m = re.fullmatch(r"現場にいるこのキャラは((?:〚特徴［[^］]*］〛)+)を持つ", p)
        if m:
            out.append({"op": "rasgos_esta", "rasgos": re.findall(r"［([^］]*)］", m.group(1))})
            continue
        m = re.fullmatch(r"このキャラは相手の現場にいる(.+?)を指定してアクションできる", p)
        if m:
            f = filtro(m.group(1))
            if f is None:
                return None
            out.append({"op": "objetivo_extra", "filtro": f})
            continue
        if p == "このキャラは事件を指定してアクションできない":
            out.append({"op": "sin_accion_caso"})
            continue
        if p == "このキャラはスリープ状態でもガードできる":
            out.append({"op": "guardia_dormido"})
            continue
        if p == "このキャラはスリープ状態で登場する":
            out.append({"op": "entra_dormido"})
            continue
        if p == "相手の能力や効果によって選ばれない":
            out.append({"op": "intocable"})
            continue
        if p == "相手は【カットイン】を使用できない":
            out.append({"op": "sin_irrupcion_rival"})
            continue
        return None
    return out or None


def _irrupcion(h: Habilidad, texto: str) -> Habilidad:
    """«AP+2000»; «AP+1000、<efecto>»; «NAMEに【カットイン】する場合、AP+3000»;
    «AP+1000、NAMEに【カットイン】する場合、代わりにAP+2000»."""
    m = re.fullmatch(r"(.+?)に【カットイン】する場合、AP\+(\d+)", texto)
    if m:
        f = filtro(m.group(1))
        h.irrupcion = {"ap": int(m.group(2)), "solo": f}
        return h
    m = re.match(r"AP\+(\d+)", texto)
    if not m:
        h.clase = INFO
        return h
    h.irrupcion = {"ap": int(m.group(1))}
    resto = texto[m.end():].lstrip("、")
    mm = re.fullmatch(r"(.+?)に【カットイン】(?:する|した)場合、代わりにAP\+(\d+)", resto)
    if mm:
        h.irrupcion["alt"] = (filtro(mm.group(1)), int(mm.group(2)))
        return h
    mm = re.fullmatch(r"(.+?)に【カットイン】した場合、(.+?)。?", resto)
    if mm:
        f = filtro(mm.group(1))
        pasos = _frase(mm.group(2))
        if f is not None and pasos is not None:
            for p in pasos:
                p.setdefault("si", []).append(("objetivo_irrupcion", f))
            h.pasos = pasos
            return h
    if resto:
        h.pasos = _efecto(resto)
    return h


def _p_contacto(s: str):
    """Efectos que duran el Contacto y los que se refieren a «そのキャラ»."""
    m = re.fullmatch(r"(?:その|この)コンタクト中、このキャラを(AP)([+-])(\d+)する", s)
    if m:
        return [{"op": "esta", "accion": "mod", "campo": "ap", "hasta": "contacto",
                 "valor": int(m.group(3)) * (1 if m.group(2) == "+" else -1)}]
    m = re.fullmatch(r"ガードしたキャラをアクティブにし、ターン終了時までAP([+-])(\d+)する", s)
    if m:
        return [{"op": "esta", "accion": "activar"},
                {"op": "esta", "accion": "mod", "campo": "ap", "hasta": "turno",
                 "valor": int(m.group(2)) * (1 if m.group(1) == "+" else -1)}]
    m = re.fullmatch(r"ターン終了時までそのキャラ(?:に|を)(.+)", s)
    if m:
        v = _verbo("ターン終了時まで" + m.group(1))
        if v:
            return [{"op": "ultima", **v}]
    return None


@lru_cache(maxsize=4096)
def _interpretar_texto(texto: str, tipo: str) -> tuple:
    lineas: list[str] = []
    for l in texto.splitlines():
        l = l.strip()
        if not l:
            continue
        if lineas and (l.lstrip().startswith(("・", "(上から", "（上から"))):
            lineas[-1] += l.strip()        # opciones de «以下から1つ選んで行う»
        else:
            lineas.append(l)
    return tuple(interpretar_linea(l, i, tipo) for i, l in enumerate(lineas))


def habilidades(defn: CartaDef) -> tuple:
    """Habilidades de una carta, a partir de su texto japonés (vacío si no lo tiene)."""
    ja = defn.texto.get("ja") or ""
    if not ja:
        return ()
    return _interpretar_texto(ja, defn.tipo)


def cobertura(defs: list) -> dict:
    """Cuántas líneas de habilidad se aplican de forma automática."""
    tot = auto = 0
    por_clase: dict = {}
    for d in defs:
        for h in habilidades(d):
            if h.clase in (NUCLEO, DISFRAZ):
                continue
            tot += 1
            ok = h.automatica
            auto += ok
            a, b = por_clase.get(h.clase, (0, 0))
            por_clase[h.clase] = (a + ok, b + 1)
    return {"total": tot, "automaticas": auto, "por_clase": por_clase}
