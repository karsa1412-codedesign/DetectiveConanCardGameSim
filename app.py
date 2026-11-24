"""Simulador de Detective Conan Card Game (proyecto de fans, no oficial).

Uso:
    python app.py                 abre el tablero
    python app.py --prueba N      juega N partidas automáticas para comprobar el motor
"""
import random
import sys
from pathlib import Path


def carpeta_base() -> Path:
    """Junto al .exe cuando está empaquetado; junto a este archivo si no."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def prueba(n: int):
    from core import acciones as A
    from core.cartas import Catalogo, Mazo
    from core.reglas import nueva_partida
    base = carpeta_base() / "datos"
    cat = Catalogo.cargar(base / "cartas_demo.json")
    m0 = Mazo.cargar(base / "mazos" / "demo_azul.json")
    m1 = Mazo.cargar(base / "mazos" / "demo_rojo.json")
    for s in range(n):
        m = nueva_partida(cat, m0, m1, semilla=s)
        r = random.Random(s)
        while m.p.ganador is None:
            leg = m.legales()
            res = [a for a in leg if isinstance(a, A.ResolverCaso)]
            m.aplicar(res[0] if res else r.choice(leg))
        print(f"Partida {s + 1}: {m.p.turno} turnos · gana el jugador {m.p.ganador + 1} ({m.p.motivo})")


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--prueba":
        prueba(int(sys.argv[2]))
        return
    from PySide6.QtWidgets import QApplication
    from gui.ventana import Ventana
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    from gui.tema import QSS
    app.setStyleSheet(QSS)
    from core.rutas import rutas
    v = Ventana(rutas())
    v.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
