"""IA: juega partidas completas, respeta las reglas y no mira las cartas ocultas."""
from pathlib import Path

from core import acciones as A
from core.cartas import Catalogo, Mazo
from core.ia import IA, copiar, imaginar, valorar
from core.reglas import nueva_partida
import random

BASE = Path(__file__).resolve().parent.parent / "datos"


def _motor(semilla=1):
    cat = Catalogo.cargar(BASE / "cartas_demo.json")
    m0 = Mazo.cargar(BASE / "mazos" / "demo_azul.json")
    m1 = Mazo.cargar(BASE / "mazos" / "demo_rojo.json")
    return nueva_partida(cat, m0, m1, semilla=semilla)


def _jugar(niveles, semilla):
    m = _motor(semilla)
    ias = [IA(0, niveles[0], semilla=semilla), IA(1, niveles[1], semilla=semilla + 50, tiempo=0.05)]
    for _ in range(2500):
        if m.p.ganador is not None:
            break
        q = m.p.quien_decide()
        a = ias[q].pensar(m).accion
        assert a in m.legales()          # la IA solo hace jugadas legales
        m.aplicar(a)
    return m


def test_partidas_completas_en_todos_los_niveles():
    for semilla, niveles in enumerate((("facil", "facil"), ("normal", "facil"), ("dificil", "normal"))):
        m = _jugar(niveles, semilla)
        assert m.p.ganador is not None


def test_copia_independiente():
    m = _motor()
    c = copiar(m)
    c.aplicar(c.legales()[0])
    assert m.p.pendiente is not None and m.p.pendiente.tipo == "mulligan"
    assert c.p.carta(m.j(0).mano[0].uid).defn is m.j(0).mano[0].defn   # definiciones compartidas


def test_imaginar_no_usa_la_mano_real_del_rival():
    m = _motor()
    real = sorted(c.uid for c in m.j(1).mano)
    vistas = set()
    for k in range(10):
        c = imaginar(m, 0, random.Random(k))
        assert sorted(x.uid for x in c.j(0).mano) == sorted(x.uid for x in m.j(0).mano)   # la propia, igual
        assert len(c.j(1).mano) == len(real)
        vistas.add(tuple(sorted(x.uid for x in c.j(1).mano)))
    assert len(vistas) > 1          # la mano rival se imagina de formas distintas


def test_valoracion_premia_las_pruebas():
    m = _motor()
    base = valorar(m, 0)
    m.j(0).pruebas.append(m.j(0).mazo.pop())
    assert valorar(m, 0) > base
