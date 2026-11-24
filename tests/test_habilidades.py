"""Habilidades: intérprete del texto (japonés) y su aplicación en el motor.

Las cartas son inventadas para la prueba (nombres y textos propios, con la gramática de
las cartas oficiales), así no hace falta incluir datos oficiales en el repositorio.
"""
import pytest

from core import acciones as A
from core import habilidades as H
from core.cartas import Catalogo, CartaDef, Mazo
from core.estado import ACTIVO, DORMIDO
from core.reglas import ReglaError, nueva_partida


def carta(cid, tipo="personaje", nombre=None, nivel=1, ap=1000, lp=1, rasgos=(), texto="", colores=("azul",),
          caso=(5, 6)):
    return CartaDef.desde_dict({
        "id": cid, "nombre": {"ja": nombre or cid, "es": nombre or cid}, "tipo": tipo, "colores": list(colores),
        "nivel": nivel, "ap": ap, "lp": lp, "rasgos_ja": list(rasgos), "texto": {"ja": texto},
        "nivel_caso": list(caso)})


ESPECIALES = [
    # 【宣言】【スリープ】 que retira a otro Personaje (el fallo que se comunicó)
    carta("X01", nombre="探偵アルファ", nivel=4, ap=6000, rasgos=["警察"],
          texto="【宣言】【スリープ】：AP5000以下のキャラを1枚まで選び、リムーブする。"),
    carta("X02", nombre="探偵ベータ", nivel=2, ap=2000, rasgos=["警察"],
          texto="【登場時】カードを2枚引き、手札を2枚リムーブする。"),
    carta("X03", nombre="探偵ガンマ", nivel=3, ap=3000,
          texto="【疾風】キャラを1枚まで選び、スリープさせる。"),
    carta("X04", nombre="探偵デルタ", nivel=2, ap=3000, lp=0,
          texto="【パートナー青】〚突撃〛（登場したターンからすぐにアクションできる）"),
    carta("X05", nombre="探偵イプシロン", nivel=2, ap=3000,
          texto="【宣言】【ターン1】〚手札を1枚リムーブする〛：ターン終了時までこのキャラをAP＋1000し、〚突撃〛を持つ。"),
    carta("X06", nombre="謎の手紙", tipo="evento", nivel=1,
          texto="カードを1枚引く。キャラを1枚まで選び、スリープさせる。"),
    carta("X07", nombre="探偵ゼータ", nivel=1, ap=1000,
          texto="【ヒラメキ】（証拠からリムーブされるときに発動する）カードを2枚引く。"),
    carta("X08", nombre="探偵エータ", nivel=1, ap=1000,
          texto="【登場時】空に虹をかける。"),   # frase inventada que el intérprete no conoce
    carta("X10", nombre="囮の刑事", nivel=2, ap=5000,
          texto="【宣言】【スリープ】：相手のターン終了時までこのキャラは「相手の現場にいるキャラがアクションするとき、"
                "このキャラを指定できる場合、必ず指定する。」を持つ。"),
    carta("X09", nombre="探偵シータ", nivel=3, ap=4000,
          texto="【宣言】【スリープ】：AP5000以下のキャラを1枚まで選び、リムーブする。"
                "この能力は自分の現場に〚特徴［警察］〛のキャラが2枚以上いる場合に宣言できる。"),
]
RELLENO = [carta(f"R{i:02d}", nombre=f"助手{i}", nivel=1, ap=1000 + 100 * i) for i in range(1, 15)]
COMP_AZUL = carta("PA", tipo="companero", nombre="相棒青", lp=1)
COMP_ROJO = carta("PR", tipo="companero", nombre="相棒赤", lp=1, colores=("rojo",))
CASO = carta("CS", tipo="caso", nombre="事件ファイル", colores=("azul", "rojo"),
             texto="この事件が解決編になったとき、自分は手札を1枚リムーブする。")
CAT = Catalogo(ESPECIALES + RELLENO + [COMP_AZUL, COMP_ROJO, CASO])


def mazo(comp="PA"):
    cartas = {d.id: 3 for d in RELLENO[:13]}
    cartas["R14"] = 1
    return Mazo("prueba", comp, "CS", cartas)


def partida(comp0="PA"):
    m = nueva_partida(CAT, mazo(comp0), mazo(), semilla=5, primero=0)
    m.aplicar(A.Mulligan(0, ()))
    m.aplicar(A.Mulligan(1, ()))
    return m


def dar(m, jugador, cid, zona="mano"):
    """Mete una carta de prueba en la zona indicada."""
    from core.estado import Carta
    uid = max(m.p._uids) + 1
    c = Carta(uid, CAT[cid], jugador)
    m.p.registrar(c)
    j = m.j(jugador)
    if zona == "escena":
        c.turno_entrada = -5
        j.escena.append(c)
    else:
        getattr(j, zona).append(c)
    return c


# ------------------------------------------------------------------ intérprete

def test_interpreta_tipos_costes_y_objetivos():
    h = H.habilidades(CAT["X01"])[0]
    assert h.clase == H.DECLARAR and h.coste_dormir and h.automatica
    p = h.pasos[0]
    assert p["op"] == "elegir" and p["accion"] == "retirar" and p["filtro"]["ap_max"] == 5000
    assert (p["min"], p["max"]) == (0, 1)
    h = H.habilidades(CAT["X05"])[0]
    assert h.limite == 1 and h.coste == [{"op": "descartar_mano", "n": 1}]
    assert H.habilidades(CAT["X04"])[0].clase == H.CLAVE
    assert H.habilidades(CAT["X04"])[0].condiciones == [("companero_color", ["azul"])]
    assert H.habilidades(CAT["X09"])[0].declarable_si[0][0] == "hay_en_escena"
    assert H.habilidades(CASO)[0].clase == H.CASO_RESOLUCION


def test_lo_que_no_entiende_queda_como_paso_manual():
    h = H.habilidades(CAT["X08"])[0]
    assert h.clase == H.ENTRADA and not h.automatica
    assert h.pasos[0]["op"] == "manual"


def test_modos_y_opcionales():
    d = carta("Y1", texto="【登場時】以下から1つ選んで行う。\n・カードを1枚引く。\n・キャラを1枚まで選び、スリープさせる。")
    h = H.habilidades(d)[0]
    assert h.pasos[0]["op"] == "modo" and len(h.pasos[0]["opciones"]) == 2
    d = carta("Y2", texto="【登場時】このキャラをスリープさせてもよい。そうした場合、カードを2枚引く。")
    pasos = H.habilidades(d)[0].pasos
    assert pasos[0]["op"] == "preguntar" and ("hecho",) in pasos[-1]["si"]


# ------------------------------------------------------------------ motor

def test_declarar_con_coste_dormir_el_turno_de_entrada_y_elegir_objetivo():
    m = partida()
    rival = dar(m, 1, "R05", "escena")        # AP 1500
    c = dar(m, 0, "X01")
    m.j(0).file += [m.j(0).mazo.pop() for _ in range(4)]
    m.aplicar(A.JugarCarta(0, c.uid))
    decl = [a for a in m.legales() if isinstance(a, A.Declarar)]
    assert decl == [A.Declarar(0, c.uid, 0)]          # recién llegado, pero 【宣言】 sí se puede
    m.aplicar(decl[0])
    assert c.estado == DORMIDO                          # coste pagado
    pend = m.p.pendiente
    assert pend.tipo == "efecto" and rival.uid in pend.datos["opciones"]
    assert c.uid not in pend.datos["opciones"]          # AP 6000 no cumple «AP5000以下»
    m.aplicar(A.Elegir(0, (rival.uid,)))
    assert rival not in m.j(1).escena and rival in m.j(1).descarte
    assert not any(isinstance(a, A.Declarar) for a in m.legales())   # ya está dormido


def test_no_se_puede_declarar_dormido_si_el_coste_es_dormir():
    m = partida()
    c = dar(m, 0, "X01", "escena")
    c.estado = DORMIDO
    with pytest.raises(ReglaError):
        m.aplicar(A.Declarar(0, c.uid, 0))


def test_condicion_para_declarar():
    m = partida()
    c = dar(m, 0, "X09", "escena")
    assert not any(isinstance(a, A.Declarar) for a in m.legales())
    dar(m, 0, "X01", "escena")
    dar(m, 0, "X02", "escena")                          # ya hay 2 「警察」
    assert A.Declarar(0, c.uid, 0) in m.legales()


def test_entrada_roba_y_descarta_eligiendo():
    m = partida()
    c = dar(m, 0, "X02")
    m.j(0).file += [m.j(0).mazo.pop() for _ in range(2)]
    mano = len(m.j(0).mano)
    m.aplicar(A.JugarCarta(0, c.uid))
    pend = m.p.pendiente
    assert pend.tipo == "efecto" and pend.datos["tras"] == "descartar"
    assert len(m.j(0).mano) == mano - 1 + 2
    with pytest.raises(ReglaError):
        m.aplicar(A.Elegir(0, tuple(pend.datos["opciones"][:1])))   # hay que elegir 2
    m.aplicar(A.Elegir(0, tuple(pend.datos["opciones"][:2])))
    assert len(m.j(0).mano) == mano - 1 and m.p.pendiente is None


def test_rafaga_solo_el_primero_del_turno():
    m = partida()
    a, b = dar(m, 0, "X03"), dar(m, 0, "X03")
    m.j(0).file += [m.j(0).mazo.pop() for _ in range(4)]
    m.aplicar(A.JugarCarta(0, a.uid))
    assert m.p.pendiente and m.p.pendiente.datos["modo"] == "elegir"
    m.aplicar(A.Elegir(0, ()))
    m.aplicar(A.SiguientePista(0))
    m.aplicar(A.JugarCarta(0, b.uid))
    assert m.p.pendiente is None                        # el segundo no dispara 【疾風】


def test_clave_condicionada_al_color_del_companero():
    m = partida("PA")
    c = dar(m, 0, "X04", "escena")
    c.turno_entrada = m.p.turno
    dar(m, 1, "R01", "pruebas")
    assert m.tiene(c, "asalto") and A.Atacar(0, c.uid, None) in m.legales()
    m2 = partida("PR")
    c2 = dar(m2, 0, "X04", "escena")
    c2.turno_entrada = m2.p.turno
    assert not m2.tiene(c2, "asalto")


def test_limite_por_turno_y_coste_de_mano():
    m = partida()
    c = dar(m, 0, "X05", "escena")
    m.j(0).mano.clear()
    assert not any(isinstance(a, A.Declarar) for a in m.legales())   # sin cartas para el coste
    dar(m, 0, "R01")
    dar(m, 0, "R02")
    m.aplicar(A.Declarar(0, c.uid, 0))
    m.aplicar(A.Elegir(0, (m.p.pendiente.datos["opciones"][0],)))
    assert c.ap == 4000 and m.tiene(c, "asalto")
    assert not any(isinstance(a, A.Declarar) for a in m.legales())   # 【ターン1】
    m.aplicar(A.FinTurno(0))
    assert c.ap == 3000 and not m.tiene(c, "asalto")


def test_evento_aplica_su_texto_y_va_a_retiradas():
    m = partida()
    ev = dar(m, 0, "X06")
    rival = dar(m, 1, "R03", "escena")
    m.j(0).file.append(m.j(0).mazo.pop())
    mano = len(m.j(0).mano)
    m.aplicar(A.JugarCarta(0, ev.uid))
    assert len(m.j(0).mano) == mano       # −1 jugada +1 robada
    m.aplicar(A.Elegir(0, (rival.uid,)))
    assert rival.estado == DORMIDO and ev in m.j(0).descarte


def test_paso_manual_y_hecho():
    m = partida()
    c = dar(m, 0, "X08")
    m.j(0).file.append(m.j(0).mazo.pop())
    m.aplicar(A.JugarCarta(0, c.uid))
    pend = m.p.pendiente
    assert pend.datos["modo"] == "manual"
    m.aplicar(A.Manual(0, "robar"))                  # las herramientas manuales siguen disponibles
    m.aplicar(A.Elegir(0, (), 1))
    assert m.p.pendiente is None and A.FinTurno(0) in m.legales()


def test_caso_en_resolucion_dispara_su_habilidad():
    m = partida()
    j = m.j(0)
    j.file += [j.mazo.pop() for _ in range(6)]
    m.aplicar(A.Asistir(0))
    assert j.caso_resuelto
    pend = m.p.pendiente
    assert pend.tipo == "efecto" and pend.datos["tras"] == "descartar"


def test_inspiracion_opcional_al_perder_una_prueba():
    m = partida()
    at = dar(m, 0, "R10", "escena")
    insp = dar(m, 1, "X07", "pruebas")
    m.j(1).escena.clear()
    mano = len(m.j(1).mano)
    m.aplicar(A.Atacar(0, at.uid, None))
    pend = m.p.pendiente
    assert pend.jugador == 1 and pend.datos["modo"] == "si_no" and pend.datos.get("inspiracion")
    m.aplicar(A.Elegir(1, (), 1))
    assert len(m.j(1).mano) == mano + 2 and insp in m.j(1).descarte


def test_partidas_aleatorias_con_habilidades_no_se_cuelgan():
    import random
    for semilla in range(8):
        m = partida()
        r = random.Random(semilla)
        for cid in ("X01", "X02", "X03", "X05", "X06", "X08", "X09"):
            dar(m, 0, cid)
            dar(m, 1, cid)
        for _ in range(400):
            if m.p.ganador is not None:
                break
            legales = m.legales()
            assert legales
            m.aplicar(r.choice(legales))


def test_provocar_obliga_a_elegirlo_hasta_el_fin_del_turno_rival():
    m = partida()
    se = dar(m, 0, "X10", "escena")
    m.aplicar(A.Declarar(0, se.uid, 0))
    assert se.estado == DORMIDO and se.marca("provocar")
    m.aplicar(A.FinTurno(0))
    at = dar(m, 1, "R12", "escena")
    otro = dar(m, 0, "R01", "escena")
    otro.estado = DORMIDO
    dar(m, 0, "R02", "pruebas")
    ataques = [a for a in m.legales() if isinstance(a, A.Atacar) and a.atacante == at.uid]
    assert ataques == [A.Atacar(1, at.uid, se.uid)]
    with pytest.raises(ReglaError):
        m.aplicar(A.Atacar(1, at.uid, None))
    m.aplicar(A.FinTurno(1))
    assert not se.marca("provocar")
