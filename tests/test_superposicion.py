"""La superposición del texto traducido: no toca el original y tapa del todo el texto impreso."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtGui = pytest.importorskip("PySide6.QtGui")

from core.cartas import CartaDef  # noqa: E402
from gui.superposicion import componer  # noqa: E402

QtWidgets = pytest.importorskip("PySide6.QtWidgets")
_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _carta(tipo="personaje", **kw):
    d = {"id": "X1", "nombre": {"ja": "てすと", "es": "Prueba"}, "tipo": tipo, "colores": ["azul"],
         "texto": {"ja": "【登場時】カードを1枚引く。", "es": "[Al entrar] Roba 1 carta."}, **kw}
    return CartaDef.desde_dict(d)


def _imagen(w=716, h=1000):
    pix = QtGui.QPixmap(w, h)
    pix.fill(QtGui.QColor("black"))
    return pix


@pytest.mark.parametrize("tipo,w,h", [("personaje", 716, 1000), ("evento", 716, 1000),
                                      ("companero", 716, 1000), ("caso", 1000, 716)])
def test_compone_sin_tocar_el_original(tipo, w, h):
    orig = _imagen(w, h)
    out = componer(orig, _carta(tipo), "es")
    assert out is not None and out.size() == orig.size()
    assert orig.toImage().pixelColor(w // 2, int(h * 0.85)).name() == "#000000"   # original intacto
    # en la caja (zona baja) el velo aclara el fondo
    img = out.toImage()
    y = int(h * 0.80) if tipo != "caso" else int(h * 0.90)
    aclarados = sum(1 for x in range(int(w * 0.3), int(w * 0.7), 7) if img.pixelColor(x, y).lightness() > 30)
    assert aclarados > 0


def test_sin_traduccion_no_compone():
    d = CartaDef.desde_dict({"id": "X2", "nombre": {"ja": "てすと"}, "tipo": "personaje", "texto": {"ja": "あ"}})
    assert componer(_imagen(), d, "es") is None


def test_fundas_propias_y_del_usuario(tmp_path):
    from gui.fundas import ALTO, ANCHO, Fundas
    img = QtGui.QImage(800, 600, QtGui.QImage.Format_RGB32)
    img.fill(QtGui.QColor("purple"))
    img.save(str(tmp_path / "Mi funda.png"))
    f = Fundas(tmp_path)
    assert "Noche" in f.disponibles() and "Mi funda" in f.disponibles()
    for nombre in f.disponibles():
        pix = f.pixmap(nombre)
        assert (pix.width(), pix.height()) == (ANCHO, ALTO)
    assert f.pixmap("no existe").width() == ANCHO      # vuelve a la funda por defecto


def test_texto_japones_queda_borroso():
    """Un patrón nítido (como el texto impreso) pierde casi todo su contraste bajo la caja."""
    img = QtGui.QImage(716, 1000, QtGui.QImage.Format_RGB32)
    img.fill(QtGui.QColor("white"))
    p = QtGui.QPainter(img)
    for x in range(0, 716, 6):
        p.fillRect(x, 760, 3, 100, QtGui.QColor("black"))
    p.end()
    out = componer(QtGui.QPixmap.fromImage(img), _carta(), "es").toImage()
    fila = [out.pixelColor(x, 845).lightness() for x in range(200, 600)]
    assert max(fila) - min(fila) < 120          # el original va de 0 a 255
