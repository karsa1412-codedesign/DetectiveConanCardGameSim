"""Vídeo de introducción al abrir la app (unos 6,8 s; se salta con un clic o una tecla).

0–3,6 s: fotogramas pregenerados (recursos/intro/*.jpg): pared de ladrillo con relieve, un
foco que barre de lado a lado y el título «DETECTIVE CONAN · Juego de cartas coleccionables»
con «Fan Sim». Calcular ese relieve en directo sería demasiado lento, por eso va pregenerado.
3,6–6,8 s: dibujado en directo: sale una cerradura del centro, la cámara entra por ella y
detrás aparece la pantalla real de la app con un zoom out.
Todo es diseño propio; no usa el logo ni material oficial.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

FPS = 30
DURACION = 6.8
FIN_FOTOGRAMAS = 3.6


def _suave(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _tramo(t: float, a: float, b: float) -> float:
    return _suave((t - a) / (b - a))


def forma_cerradura(c: QPointF, h: float) -> QPainterPath:
    r = h * 0.26
    circulo = QPainterPath()
    circulo.addEllipse(QPointF(c.x(), c.y() - h * 0.22), r, r)
    ranura = QPainterPath()
    ranura.addPolygon([QPointF(c.x() - r * 0.45, c.y() - h * 0.15), QPointF(c.x() + r * 0.45, c.y() - h * 0.15),
                       QPointF(c.x() + r * 0.85, c.y() + h * 0.50), QPointF(c.x() - r * 0.85, c.y() + h * 0.50)])
    ranura.closeSubpath()
    return circulo.united(ranura)


def placa(p: QPainter, c: QPointF, h: float, alfa: float):
    """Bocallave de latón alrededor de la cerradura."""
    p.save()
    p.setOpacity(alfa)
    pl = QPainterPath()
    pl.addRoundedRect(QRectF(c.x() - h * 0.36, c.y() - h * 0.62, h * 0.72, h * 1.24), h * 0.36, h * 0.36)
    g = QLinearGradient(c.x() - h * 0.36, c.y() - h * 0.62, c.x() + h * 0.36, c.y() + h * 0.62)
    g.setColorAt(0, QColor("#f3d38a"))
    g.setColorAt(0.45, QColor("#b98a3a"))
    g.setColorAt(1, QColor("#5e4216"))
    p.fillPath(pl.translated(h * 0.03, h * 0.05), QColor(0, 0, 0, 120))
    p.fillPath(pl, QBrush(g))
    p.setPen(QPen(QColor(60, 40, 15, 200), max(1.0, h * 0.012)))
    p.drawPath(pl)
    p.setBrush(QColor("#7a5a24"))
    for dy in (-0.48, 0.48):
        p.drawEllipse(QPointF(c.x(), c.y() + h * dy), h * 0.04, h * 0.04)
    p.restore()


class Intro(QWidget):
    terminada = Signal()

    def __init__(self, ventana, carpeta: Path):
        super().__init__(ventana)
        self.v = ventana
        rutas = sorted(Path(carpeta).glob("*.jpg"))
        self.fotogramas = [QPixmap(str(r)) for r in rutas]
        self.fotogramas = [f for f in self.fotogramas if not f.isNull()]
        self.detras: QPixmap | None = None
        self.t0 = 0.0
        self.t = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tic)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.iniciada = False
        self.hide()      # se muestra al llamar a empezar()

    @property
    def valida(self) -> bool:
        return len(self.fotogramas) > 10

    def empezar(self):
        if self.iniciada:
            return
        self.iniciada = True
        self.setGeometry(self.v.rect())
        self.raise_()
        self.show()
        self.setFocus()
        self.t0 = time.monotonic()
        self.timer.start(1000 // FPS)

    def _tic(self):
        self.t = time.monotonic() - self.t0
        if self.t >= 4.9 and self.detras is None:
            self._capturar()
        if self.t >= DURACION:
            self.terminar()
            return
        self.update()

    def _capturar(self):
        """Foto de la pantalla real que hay debajo, para verla a través de la cerradura."""
        self.hide()
        self.detras = self.v.grab()
        self.show()
        self.raise_()

    def terminar(self):
        self.timer.stop()
        self.hide()
        self.deleteLater()
        self.terminada.emit()

    def mousePressEvent(self, ev):
        self.terminar()

    def keyPressEvent(self, ev):
        self.terminar()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)

    def _cubrir(self, p: QPainter, pix: QPixmap):
        """Dibuja pix entero y centrado; el resto queda negro (los bordes del vídeo ya lo son)."""
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(0, 0, 0))
        esc = min(w / pix.width(), h / pix.height())
        dw, dh = pix.width() * esc, pix.height() * esc
        p.drawPixmap(QRectF((w - dw) / 2, (h - dh) / 2, dw, dh), pix, QRectF(pix.rect()))

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        t = self.t
        i = min(len(self.fotogramas) - 1, int(min(t, FIN_FOTOGRAMAS) * FPS))
        self._cubrir(p, self.fotogramas[i])
        W, H = self.width(), self.height()
        c = QPointF(W / 2, H / 2 + H * 0.014)
        crece = _tramo(t, 3.9, 4.7)
        if crece > 0:
            p.fillRect(self.rect(), QColor(0, 0, 0, int(110 * crece)))
            abre = _tramo(t, 5.0, 6.0)
            base = H / 720
            h = (20 + 230 * crece) * base + (H * 9) * abre ** 2.4
            placa(p, c, h, crece)
            p.save()
            p.setClipPath(forma_cerradura(c, h))
            p.fillRect(self.rect(), QColor(4, 5, 8))
            if abre > 0 and self.detras is not None:
                zoom = 1.22 - 0.22 * _tramo(t, 5.2, 6.6)
                p.setOpacity(_tramo(t, 5.0, 5.5))
                p.translate(W / 2, H / 2)
                p.scale(zoom, zoom)
                p.translate(-W / 2, -H / 2)
                p.drawPixmap(self.rect(), self.detras)
            p.restore()
        p.end()
