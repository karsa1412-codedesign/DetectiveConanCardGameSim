"""Dorsos de carta: fundas de diseño propio y fundas del usuario (carpeta fundas/).

La app no incluye imágenes oficiales. Cada jugador puede poner en fundas/ las imágenes
que quiera usar (PNG, JPG o WEBP); se recortan al formato de carta automáticamente.
"""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient)

ANCHO, ALTO = 360, 504    # resolución de trabajo (proporción 5:7)

# nombre: (color principal, color secundario, motivo)
PROPIAS = {
    "Noche": ("#13213f", "#d9a845", "rombos"),
    "Granate": ("#4a1420", "#e3b56a", "rayas"),
    "Esmeralda": ("#0f3b2e", "#cfe3c8", "circulos"),
    "Pizarra": ("#2a2f38", "#9fb4d0", "cuadricula"),
    "Papel": ("#efe6d2", "#5a4632", "lupa"),
}


def _lupa(p: QPainter, c: QPointF, r: float, color: QColor, grosor: float):
    p.setPen(QPen(color, grosor, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(c, r, r)
    a = math.radians(45)
    p.drawLine(QPointF(c.x() + r * math.cos(a), c.y() + r * math.sin(a)),
               QPointF(c.x() + r * 2.1 * math.cos(a), c.y() + r * 2.1 * math.sin(a)))


def _dibujar_propia(nombre: str) -> QPixmap:
    base, acento, motivo = PROPIAS[nombre]
    pix = QPixmap(ANCHO, ALTO)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    marco = QPainterPath()
    marco.addRoundedRect(QRectF(0, 0, ANCHO, ALTO), 22, 22)
    p.setClipPath(marco)
    g = QRadialGradient(ANCHO / 2, ALTO / 2, ALTO * 0.75)
    g.setColorAt(0, QColor(base).lighter(135))
    g.setColorAt(1, QColor(base))
    p.fillRect(pix.rect(), QBrush(g))
    tenue = QColor(acento)
    tenue.setAlpha(55)
    p.setPen(QPen(tenue, 2))
    if motivo == "rombos":
        for y in range(-40, ALTO + 40, 36):
            for x in range(-40, ANCHO + 40, 36):
                d = 14
                p.drawPolygon([QPointF(x, y - d), QPointF(x + d, y), QPointF(x, y + d), QPointF(x - d, y)])
    elif motivo == "rayas":
        for i in range(-ALTO, ANCHO + ALTO, 22):
            p.drawLine(i, 0, i + ALTO, ALTO)
    elif motivo == "circulos":
        for y in range(0, ALTO + 60, 60):
            for x in range(0, ANCHO + 60, 60):
                p.drawEllipse(QPointF(x + (30 if (y // 60) % 2 else 0), y), 24, 24)
    elif motivo == "cuadricula":
        for x in range(0, ANCHO, 24):
            p.drawLine(x, 0, x, ALTO)
        for y in range(0, ALTO, 24):
            p.drawLine(0, y, ANCHO, y)
    elif motivo == "lupa":
        for y in range(30, ALTO, 90):
            for x in range(30, ANCHO, 90):
                _lupa(p, QPointF(x + (45 if (y // 90) % 2 else 0), y), 13, tenue, 3)
    # marco interior y emblema central (lupa propia)
    p.setPen(QPen(QColor(acento), 4))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(16, 16, ANCHO - 32, ALTO - 32), 14, 14)
    p.setPen(QPen(QColor(acento), 1.5))
    p.drawRoundedRect(QRectF(26, 26, ANCHO - 52, ALTO - 52), 10, 10)
    centro = QPointF(ANCHO / 2 - 14, ALTO / 2 - 18)
    fondo = QColor(base)
    fondo.setAlpha(230)
    p.setPen(Qt.NoPen)
    p.setBrush(fondo)
    p.drawEllipse(QPointF(ANCHO / 2, ALTO / 2), 92, 92)
    p.setPen(QPen(QColor(acento), 3))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(ANCHO / 2, ALTO / 2), 92, 92)
    _lupa(p, centro, 34, QColor(acento), 9)
    f = QFont()
    f.setBold(True)
    f.setPixelSize(22)
    f.setLetterSpacing(QFont.AbsoluteSpacing, 3)
    p.setFont(f)
    p.setPen(QColor(acento))
    p.drawText(QRectF(0, ALTO - 78, ANCHO, 30), Qt.AlignCenter, "CASE FILE")
    p.end()
    return pix


def _recortar(img: QPixmap) -> QPixmap:
    """Ajusta una imagen del usuario al formato de carta (recorte centrado) con esquinas redondeadas."""
    esc = img.scaled(ANCHO, ALTO, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x, y = (esc.width() - ANCHO) // 2, (esc.height() - ALTO) // 2
    esc = esc.copy(x, y, ANCHO, ALTO)
    pix = QPixmap(ANCHO, ALTO)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    camino = QPainterPath()
    camino.addRoundedRect(QRectF(0, 0, ANCHO, ALTO), 22, 22)
    p.setClipPath(camino)
    p.drawPixmap(0, 0, esc)
    p.setClipping(False)
    p.setPen(QPen(QColor(0, 0, 0, 120), 3))
    p.drawPath(camino)
    p.end()
    return pix


class Fundas:
    def __init__(self, carpeta: Path):
        self.carpeta = Path(carpeta)
        self.cache: dict[str, QPixmap] = {}

    def disponibles(self) -> list[str]:
        propias = list(PROPIAS)
        usuario = []
        if self.carpeta.exists():
            usuario = sorted(p.stem for p in self.carpeta.iterdir()
                             if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
        return propias + [u for u in usuario if u not in PROPIAS]

    def es_propia(self, nombre: str) -> bool:
        return nombre in PROPIAS

    def pixmap(self, nombre: str | None) -> QPixmap:
        nombre = nombre if nombre in self.disponibles() else "Noche"
        if nombre not in self.cache:
            if nombre in PROPIAS:
                self.cache[nombre] = _dibujar_propia(nombre)
            else:
                ruta = next(p for p in self.carpeta.iterdir() if p.stem == nombre)
                img = QPixmap(str(ruta))
                self.cache[nombre] = _recortar(img) if not img.isNull() else _dibujar_propia("Noche")
        return self.cache[nombre]

    def recargar(self):
        self.cache.clear()
