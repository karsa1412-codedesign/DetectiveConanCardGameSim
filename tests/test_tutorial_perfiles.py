"""Pruebas del tutorial pregrabado y de los perfiles."""
from pathlib import Path

import pytest

from core import acciones as A
from core.perfiles import GestorPerfiles, PerfilError
from core.tutorial import Guion, GuionError

DATOS = Path(__file__).resolve().parent.parent / "datos"


def nuevo_guion():
    return Guion(DATOS / "tutorial" / "tutorial.json", DATOS)


def test_tutorial_completo_termina_con_victoria():
    """Recorre todo el guion como lo haría el jugador: cada jugada pedida debe ser legal."""
    g = nuevo_guion()
    while not g.terminado:
        if g.tipo() == "usuario":
            esperadas = g.esperadas()
            assert esperadas, f"paso {g.indice + 1}: el motor no permite la jugada pedida"
            g.jugar_usuario(esperadas[0])
        else:
            g.continuar()
    assert g.motor.p.ganador == 0
    assert g.motor.p.motivo == "Caso resuelto."


def test_tutorial_siempre_igual():
    def log():
        g = nuevo_guion()
        while not g.terminado:
            g.jugar_usuario(g.esperadas()[0]) if g.tipo() == "usuario" else g.continuar()
        return g.motor.p.log
    assert log() == log()


def test_tutorial_rechaza_otras_jugadas():
    g = nuevo_guion()
    while g.tipo() != "usuario":
        g.continuar()
    otra = next(a for a in g.motor.legales() if not g.es_esperada(a))
    with pytest.raises(GuionError):
        g.jugar_usuario(otra)
    with pytest.raises(GuionError):
        g.continuar()       # un paso del jugador no se salta con Continuar


def test_textos_del_tutorial_no_vacios():
    g = nuevo_guion()
    assert all(p["texto"]["es"].strip() for p in g.pasos)


def test_perfiles_y_registro(tmp_path):
    gp = GestorPerfiles(tmp_path)
    gp.crear("Albert")
    with pytest.raises(PerfilError):
        gp.crear("albert")
    with pytest.raises(PerfilError):
        gp.crear("   ")
    assert gp.es_nuevo("Albert")
    gp.entrar("Albert")
    gp.actualizar("Albert", tutorial_recomendado=True)
    gp.registrar("Albert", "tutorial_saltado")
    gp2 = GestorPerfiles(tmp_path)          # se conserva al reabrir
    assert not gp2.es_nuevo("Albert") and gp2.perfiles["Albert"]["accesos"] == 1
    eventos = [r["evento"] for r in gp2.leer_registro("Albert")]
    assert eventos == ["perfil_creado", "inicio_sesion", "tutorial_saltado"]
