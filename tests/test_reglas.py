"""Pruebas del motor. Ejecutar con:  python -m pytest -q"""
import random
from pathlib import Path

import pytest

from core import acciones as A
from core.cartas import Catalogo, Mazo
from core.estado import ACTIVO, ATURDIDO, DORMIDO
from core.reglas import ReglaError, nueva_partida

DATOS = Path(__file__).resolve().parent.parent / "datos"
CAT = Catalogo.cargar(DATOS / "cartas_demo.json")
AZUL = Mazo.cargar(DATOS / "mazos" / "demo_azul.json")
ROJO = Mazo.cargar(DATOS / "mazos" / "demo_rojo.json")


def empezada(semilla=1):
    """Partida tras los mulligans: turno 1 del jugador 1 (índice 0), fase principal."""
    m = nueva_partida(CAT, AZUL, ROJO, semilla=semilla, primero=0)
    m.aplicar(A.Mulligan(0, ()))
    m.aplicar(A.Mulligan(1, ()))
    return m


def a_mano(m, j, cid):
    """Pone en la mano una copia de cid sacada del mazo (para preparar situaciones)."""
    jug = m.j(j)
    c = next(c for c in jug.mazo if c.defn.id == cid)
    jug.mazo.remove(c)
    jug.mano.append(c)
    return c


def a_escena(m, j, cid, estado=ACTIVO, turno_entrada=-5):
    c = a_mano(m, j, cid)
    m.j(j).mano.remove(c)
    c.estado, c.turno_entrada = estado, turno_entrada
    m.j(j).escena.append(c)
    return c


def llenar_file(m, j, n):
    jug = m.j(j)
    while jug.cartas_file < n:
        jug.file.append(jug.mazo.pop())


# ---------------------------------------------------------------- preparación

def test_mazos_demo_validos():
    assert AZUL.validar(CAT) == [] and ROJO.validar(CAT) == []


def test_mazo_invalido_por_copias_y_tamano():
    malo = Mazo("x", "DEMO-P01", "DEMO-C01", {"DEMO-A01": 4})
    errores = malo.validar(CAT)
    assert any("40" in e for e in errores) and any("3 copias" in e for e in errores)


def test_preparacion_y_primer_turno():
    m = nueva_partida(CAT, AZUL, ROJO, semilla=3, primero=1)
    assert all(len(j.mano) == 5 for j in m.p.jugadores)
    assert m.p.pendiente.tipo == "mulligan" and m.p.pendiente.jugador == 1
    with pytest.raises(ReglaError):
        m.aplicar(A.Mulligan(0, ()))   # primero decide quien empieza
    devolver = tuple(c.uid for c in m.j(1).mano[:2])
    m.aplicar(A.Mulligan(1, devolver))
    assert len(m.j(1).mano) == 5
    m.aplicar(A.Mulligan(0, ()))
    j1 = m.j(1)
    assert m.p.turno == 1 and m.p.activo == 1
    assert len(j1.mano) == 6          # roba también en su turno 1
    assert len(j1.file) == 1          # solo 1 carta a FILE en el primer turno
    m.aplicar(A.FinTurno(1))
    assert len(m.j(0).file) == 2 and len(m.j(0).mano) == 6


# ---------------------------------------------------------------- jugar cartas

def test_nivel_limitado_por_file():
    m = empezada()
    c4 = a_mano(m, 0, "DEMO-A08")     # nivel 4, FILE = 1
    with pytest.raises(ReglaError):
        m.aplicar(A.JugarCarta(0, c4.uid))
    llenar_file(m, 0, 4)
    m.aplicar(A.JugarCarta(0, c4.uid))
    assert c4 in m.j(0).escena and c4.turno_entrada == m.p.turno


def test_color_del_caso():
    m = empezada()
    llenar_file(m, 0, 5)
    roja = a_mano(m, 1, "DEMO-R01")
    m.j(1).mano.remove(roja)
    roja.dueno = 0
    m.j(0).mano.append(roja)
    with pytest.raises(ReglaError):
        m.aplicar(A.JugarCarta(0, roja.uid))


def test_una_carta_de_mano_por_turno():
    m = empezada()
    c1, c2 = a_mano(m, 0, "DEMO-A01"), a_mano(m, 0, "DEMO-A01")
    m.aplicar(A.JugarCarta(0, c1.uid))
    with pytest.raises(ReglaError):
        m.aplicar(A.JugarCarta(0, c2.uid))


def test_siguiente_pista():
    m = empezada()
    llenar_file(m, 0, 3)
    c = a_mano(m, 0, "DEMO-A04")      # nivel 2
    m.aplicar(A.SiguientePista(0))
    assert m.j(0).cartas_file == 2 and m.p.pendiente.tipo == "pista_jugar"
    m.aplicar(A.JugarCarta(0, c.uid))
    assert c in m.j(0).escena and m.p.pendiente is None
    otra = a_mano(m, 0, "DEMO-A01")
    with pytest.raises(ReglaError):    # tras Siguiente pista no se juega de la mano
        m.aplicar(A.JugarCarta(0, otra.uid))


def test_cambio_con_escena_llena():
    m = empezada()
    ya = [a_escena(m, 0, "DEMO-A0" + str(i)) for i in (1, 1, 1, 2, 2)]
    nueva = a_mano(m, 0, "DEMO-A03")
    with pytest.raises(ReglaError):
        m.aplicar(A.JugarCarta(0, nueva.uid))
    m.aplicar(A.JugarCarta(0, nueva.uid, retirar=ya[0].uid))
    assert ya[0] in m.j(0).descarte and len(m.j(0).escena) == 5


# ---------------------------------------------------------------- compañero y victoria

def test_asistir_pasa_a_resolucion_con_7():
    m = empezada()
    llenar_file(m, 0, 6)
    m.aplicar(A.Asistir(0))
    j = m.j(0)
    assert j.companero_en_file and j.cartas_file == 7 and j.caso_resuelto
    m.aplicar(A.FinTurno(0))
    m.aplicar(A.FinTurno(1))
    assert not j.companero_en_file and j.companero.estado == ACTIVO


def test_resolver_caso_gana():
    m = empezada()
    j = m.j(0)
    j.caso_resuelto = True
    for _ in range(6):
        j.pruebas.append(j.mazo.pop())
    m.aplicar(A.ResolverCaso(0))     # 6 de 7: no basta
    assert m.p.ganador is None
    m.aplicar(A.FinTurno(0))
    m.aplicar(A.FinTurno(1))
    j.pruebas.append(j.mazo.pop())
    m.aplicar(A.ResolverCaso(0))
    assert m.p.ganador == 0


def test_resolver_sin_resolucion_no_permitido():
    m = empezada()
    with pytest.raises(ReglaError):
        m.aplicar(A.ResolverCaso(0))


# ---------------------------------------------------------------- deducir

def test_deducir_da_pruebas_igual_a_lp():
    m = empezada()
    c = a_escena(m, 0, "DEMO-A05")    # LP 2
    m.aplicar(A.Deducir(0, c.uid))
    assert len(m.j(0).pruebas) == 2 and c.estado == DORMIDO


def test_recien_llegado_no_deduce_salvo_rapidez():
    m = empezada()
    lento = a_mano(m, 0, "DEMO-A02")
    m.aplicar(A.JugarCarta(0, lento.uid))
    with pytest.raises(ReglaError):
        m.aplicar(A.Deducir(0, lento.uid))
    rapido = a_escena(m, 0, "DEMO-A03", turno_entrada=m.p.turno)
    m.aplicar(A.Deducir(0, rapido.uid))
    assert len(m.j(0).pruebas) == 1


def test_pista_falsa():
    m = empezada()
    c = a_escena(m, 0, "DEMO-A05")            # LP 2
    pf = a_escena(m, 1, "DEMO-R11")           # Pista falsa 2
    m.aplicar(A.Deducir(0, c.uid))
    assert m.p.pendiente.tipo == "pista_falsa"
    m.aplicar(A.PistaFalsa(1, (pf.uid,)))
    assert len(m.j(0).pruebas) == 0 and pf.estado == DORMIDO


# ---------------------------------------------------------------- acción y contacto

def test_accion_al_caso_sin_guardia():
    m = empezada()
    atk = a_escena(m, 0, "DEMO-A08")
    rival = m.j(1)
    rival.pruebas += [rival.mazo.pop(), rival.mazo.pop()]
    m.aplicar(A.Atacar(0, atk.uid, None))     # el rival no tiene Personajes activos
    assert len(rival.pruebas) == 1 and len(m.j(0).pruebas) == 1


def test_no_se_ataca_a_un_caso_sin_pruebas():
    m = empezada()
    atk = a_escena(m, 0, "DEMO-A08")
    with pytest.raises(ReglaError):
        m.aplicar(A.Atacar(0, atk.uid, None))


def test_guardia_y_contacto_retira_al_de_menos_ap():
    m = empezada()
    atk = a_escena(m, 0, "DEMO-A11")          # AP 8000
    objetivo = a_escena(m, 1, "DEMO-R02", estado=DORMIDO)
    guardia = a_escena(m, 1, "DEMO-R04")      # AP 5000, activo
    m.aplicar(A.Atacar(0, atk.uid, objetivo.uid))
    assert m.p.pendiente.tipo == "guardia" and m.p.pendiente.jugador == 1
    m.aplicar(A.Guardia(1, guardia.uid))
    # el de menos AP (jugador 2) actúa primero
    assert m.p.pendiente.tipo == "contacto" and m.p.pendiente.jugador == 1
    m.aplicar(A.Contactar(1, None))
    m.aplicar(A.Contactar(0, None))
    assert guardia in m.j(1).descarte and objetivo in m.j(1).escena


def test_irrupcion_salva_al_defensor():
    m = empezada()
    atk = a_escena(m, 0, "DEMO-A08")          # AP 6000
    objetivo = a_escena(m, 1, "DEMO-R04", estado=DORMIDO)  # AP 5000
    cut = a_mano(m, 1, "DEMO-R07")            # Irrupción +3000
    m.aplicar(A.Atacar(0, atk.uid, objetivo.uid))
    m.aplicar(A.Contactar(1, cut.uid, "irrupcion"))   # 8000 > 6000
    m.aplicar(A.Contactar(0, None))
    assert objetivo in m.j(1).escena and objetivo.ap == 5000   # el +3000 caduca
    assert cut in m.j(1).descarte


def test_tercer_turno_de_contacto():
    m = empezada()
    atk = a_escena(m, 0, "DEMO-A04")          # AP 4000, actúa primero
    objetivo = a_escena(m, 1, "DEMO-R09", estado=DORMIDO)  # AP 7000
    cut_a = a_mano(m, 0, "DEMO-A07")          # +3000
    cut_r = a_mano(m, 1, "DEMO-R01")          # +2000
    m.aplicar(A.Atacar(0, atk.uid, objetivo.uid))
    assert m.p.pendiente.jugador == 0
    m.aplicar(A.Contactar(0, None))           # el primero pasa
    m.aplicar(A.Contactar(1, cut_r.uid))      # el segundo actúa → el primero puede responder
    assert m.p.pendiente.jugador == 0
    m.aplicar(A.Contactar(0, cut_a.uid))      # 7000 vs 9000: no pasa nada
    assert objetivo in m.j(1).escena and m.p.pendiente is None


def test_bala_no_se_puede_guardar():
    m = empezada()
    m.p.activo = 1
    m.p.turno = 2
    atk = a_escena(m, 1, "DEMO-R08")          # Bala
    a_escena(m, 0, "DEMO-A04")                # posible guardián activo
    m.j(0).pruebas.append(m.j(0).mazo.pop())
    m.aplicar(A.Atacar(1, atk.uid, None))
    assert m.p.pendiente is None and len(m.j(1).pruebas) == 1


def test_aturdido_pasa_a_dormido_al_activar():
    m = empezada()
    c = a_escena(m, 1, "DEMO-R02", estado=ATURDIDO)
    m.aplicar(A.FinTurno(0))
    assert c.estado == DORMIDO


def test_disfraz_sustituye_en_contacto():
    m = empezada()
    m.p.activo, m.p.turno = 1, 2
    atk = a_escena(m, 1, "DEMO-R02")          # AP 3000
    objetivo = a_escena(m, 0, "DEMO-A04", estado=DORMIDO)  # AP 4000
    disfraz = a_mano(m, 1, "DEMO-R06")        # Disfraz, AP 5000
    m.aplicar(A.Atacar(1, atk.uid, objetivo.uid))
    assert m.p.pendiente.jugador == 1         # 3000 < 4000: el atacante actúa primero
    m.aplicar(A.Contactar(1, disfraz.uid, "disfraz"))
    m.aplicar(A.Contactar(0, None))
    assert disfraz in m.j(1).escena and atk in m.j(1).mazo and objetivo in m.j(0).descarte


# ---------------------------------------------------------------- reciclado

def test_reciclar_y_derrota():
    m = empezada()
    j = m.j(0)
    j.descarte += j.mazo[:-1]
    j.mazo = j.mazo[-1:]
    m.aplicar(A.Manual(0, "robar"))
    assert len(j.mazo) > 0 and len(m.j(1).pruebas) == 1
    j.descarte.clear()
    j.mano += j.mazo
    j.mazo.clear()
    m.aplicar(A.Manual(0, "robar"))
    assert m.p.ganador == 1


# ---------------------------------------------------------------- partidas completas

@pytest.mark.parametrize("semilla", range(40))
def test_partidas_aleatorias_terminan_sin_errores(semilla):
    """Juega partidas eligiendo al azar entre las acciones legales: ninguna debe ser rechazada."""
    m = nueva_partida(CAT, AZUL, ROJO, semilla=semilla)
    r = random.Random(semilla)
    for _ in range(5000):
        if m.p.ganador is not None:
            break
        legales = m.legales()
        assert legales, "sin acciones legales"
        no_fin = [a for a in legales if not isinstance(a, A.FinTurno)]
        a = r.choice(no_fin) if no_fin and r.random() < 0.85 else r.choice(legales)
        m.aplicar(a)
        for j in m.p.jugadores:
            assert len(j.escena) <= 5
    assert m.p.ganador is not None


def test_misma_semilla_misma_partida():
    def jugar():
        m = nueva_partida(CAT, AZUL, ROJO, semilla=99)
        r = random.Random(5)
        while m.p.ganador is None and len(m.p.log) < 3000:
            m.aplicar(r.choice(m.legales()))
        return m.p.log
    assert jugar() == jugar()


def test_rendirse_en_cualquier_momento():
    m = empezada()
    atk = a_escena(m, 0, "DEMO-A11")
    objetivo = a_escena(m, 1, "DEMO-R02", estado=DORMIDO)
    a_escena(m, 1, "DEMO-R04")
    m.aplicar(A.Atacar(0, atk.uid, objetivo.uid))     # pendiente: guardia del jugador 2
    m.aplicar(A.Rendirse(0))                          # aunque no le toque decidir
    assert m.p.ganador == 1 and "rendido" in m.p.motivo and m.legales() == []
    with pytest.raises(ReglaError):
        m.aplicar(A.FinTurno(1))
