"""Texto traducido superpuesto sobre la imagen de la carta, solo al mostrarla.

La imagen descargada no se modifica ni se guarda retocada: se dibuja una copia en memoria
con un velo difuminado sobre la zona de texto original y, encima, el texto de la
carta en el idioma elegido (sale de los datos de la carta, no del texto impreso).

Las zonas son plantillas por tipo de carta, en fracciones del tamaño de la imagen, para
que valgan para cualquier resolución.
"""
from __future__ import annotations

import math
import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap)

COLOR_MARCO = {"azul": "#1d4fa3", "rojo": "#b3261e", "verde": "#21804a", "amarillo": "#b8860b",
               "blanco": "#6b6b6b", "negro": "#2a2a2a"}

# x0, x1: bordes de la caja; abajo: borde inferior; linea: alto de una línea japonesa
# (con furigana); cap: caracteres japoneses por línea. Todo en fracción del ancho/alto.
PLANTILLAS = {
    "personaje": {"x0": 0.040, "x1": 0.968, "abajo": 0.888, "linea": 0.040, "cap": 34, "min_alto": 0.170},
    "evento":    {"x0": 0.030, "x1": 0.960, "abajo": 0.938, "linea": 0.036, "cap": 36, "min_alto": 0.150},
    "companero": {"x0": 0.040, "x1": 0.862, "abajo": 0.912, "linea": 0.036, "cap": 34, "min_alto": 0.140},
    "caso":      {"x0": 0.170, "x1": 0.830, "abajo": 0.968, "linea": 0.050, "cap": 40, "min_alto": 0.200},
}
NOMBRE = {
    "personaje": (0.150, 0.020, 0.775, 0.092),
    "evento":    (0.150, 0.020, 0.960, 0.092),
    "companero": (0.150, 0.020, 0.980, 0.092),
    "caso":      (0.200, 0.030, 0.800, 0.115),
}
# franjas que se tapan además de la caja (el texto del Compañero llega al borde por encima del LP)
EXTRA = {"companero": [(0.862, 0.968, 0.872), (0.862, 0.888, 0.910)]}   # x0, x1, abajo (arriba = la caja)

# rasgos: x0, x1, y del primero, alto, paso
RASGOS = {"personaje": (0.788, 0.950, 0.036, 0.017, 0.0235), "caso": (0.835, 0.978, 0.022, 0.040, 0.046)}



def _lineas_japonesas(texto: str, cap: int) -> int:
    return sum(max(1, math.ceil(len(seg.strip()) / cap)) for seg in texto.split("\n") if seg.strip()) or 1


# colores de las etiquetas, como los iconos impresos
AZUL, CIAN, OSCURO = QColor("#2a64d6"), QColor("#13a3c7"), QColor("#2b2f36")
VELO = QColor(250, 251, 255, 242)


def color_etiqueta(t: str) -> tuple[QColor, bool]:
    """(color, es_pastilla) de una etiqueta del glosario."""
    t = t.lower()
    if ("vez" in t or "veces" in t or "cop" in t) and ("turno" in t or "torn" in t) or t.startswith(("dormir", "adormir")):
        return CIAN, True
    if any(k in t for k in ("resoluc", "resolver", "resold", "asistir", "assistir", "fase caso", "fase cas",
                            "caso ", "cas ", "compañero", "company", "file", "vínculo", "vincle", "destruir")):
        return OSCURO, False
    return AZUL, False


def _difuminar(img: QImage, r: QRectF, factor: int = 14) -> QImage:
    trozo = img.copy(r.toRect())
    peq = trozo.scaled(max(1, trozo.width() // factor), max(1, trozo.height() // factor),
                       Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return peq.scaled(trozo.width(), trozo.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def _mascara(w: int, h: int, lado: float, arriba: float, abajo: float) -> QImage:
    """Máscara opaca en el centro que se desvanece en los bordes indicados (0 = borde nítido)."""
    m = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    m.fill(Qt.transparent)
    q = QPainter(m)
    gv = QLinearGradient(0, 0, 0, h)
    gv.setColorAt(0, QColor(0, 0, 0, 0 if arriba else 255))
    gv.setColorAt(min(0.49, arriba / h) if arriba else 0.0, QColor(0, 0, 0, 255))
    gv.setColorAt(max(0.51, 1 - abajo / h) if abajo else 1.0, QColor(0, 0, 0, 255))
    gv.setColorAt(1, QColor(0, 0, 0, 0 if abajo else 255))
    q.fillRect(QRectF(0, 0, w, h), QBrush(gv))
    if lado:
        q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        gh = QLinearGradient(0, 0, w, 0)
        gh.setColorAt(0, QColor(0, 0, 0, 0))
        gh.setColorAt(min(0.49, lado / w), QColor(0, 0, 0, 255))
        gh.setColorAt(max(0.51, 1 - lado / w), QColor(0, 0, 0, 255))
        gh.setColorAt(1, QColor(0, 0, 0, 0))
        q.fillRect(QRectF(0, 0, w, h), QBrush(gh))
    q.end()
    return m


def _capa(img: QImage, r: QRectF, velo: QColor, lado=0.0, arriba=0.0, abajo=0.0, factor=14) -> QImage:
    """Fondo difuminado de la propia carta + velo de color, desvanecido por los bordes."""
    r = r.intersected(QRectF(img.rect()))
    capa = QImage(r.size().toSize(), QImage.Format_ARGB32_Premultiplied)
    capa.fill(Qt.transparent)
    q = QPainter(capa)
    q.drawImage(0, 0, _difuminar(img, r, factor))
    q.fillRect(QRectF(0, 0, capa.width(), capa.height()), velo)
    q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    q.drawImage(0, 0, _mascara(capa.width(), capa.height(), lado, arriba, abajo))
    q.end()
    return capa


def _trozos(texto: str):
    out = []
    for parte in re.split(r"(\[[^\]]+\]|\n)", texto):
        if not parte:
            continue
        if parte == "\n":
            out.append(("br", ""))
        elif parte.startswith("[") and parte.endswith("]"):
            out.append(("et", parte[1:-1]))
        else:
            for w in re.split(r"(\s+)", parte):
                if w and not w.isspace():
                    out.append(("w", w))
                elif w:
                    out.append(("sp", " "))
    return out


def _maquetar(texto: str, ancho: float, px: float):
    """Reparte el texto en líneas. Devuelve (líneas, alto de línea, fuentes)."""
    f = QFont()
    f.setPixelSize(max(6, int(px)))
    fb = QFont(f)
    fb.setBold(True)
    fe = QFont(fb)
    fe.setPixelSize(max(6, int(px * 0.86)))
    fm, fmb, fme = QFontMetricsF(f), QFontMetricsF(fb), QFontMetricsF(fe)
    lineas, linea, x = [], [], 0.0
    alto_l = px * 1.32
    esp = fm.horizontalAdvance(" ")
    negrita = False
    for tipo, t in _trozos(texto):
        if tipo == "br":
            lineas.append(linea)
            linea, x = [], 0.0
            continue
        if tipo == "sp":
            if linea:
                x += esp
            continue
        if tipo == "et":
            item = ("et", t, fme.horizontalAdvance(t) + px * 0.7)
        else:
            if "«" in t:
                negrita = True
            item = ("w", t, (fmb if negrita else fm).horizontalAdvance(t), negrita)
            if "»" in t:
                negrita = False
        if x + item[2] > ancho and linea:
            lineas.append(linea)
            linea, x = [], 0.0
        linea.append((x, item))
        x += item[2] + (px * 0.18 if item[0] == "et" else 0)
    lineas.append(linea)
    return lineas, alto_l, (f, fb, fe)


def _pintar_texto(p: QPainter, lineas, alto_l, fuentes, x0: float, y0: float):
    f, fb, fe = fuentes
    for i, linea in enumerate(lineas):
        y = y0 + i * alto_l
        for x, item in linea:
            if item[0] == "et":
                _, t, w = item
                col, pastilla = color_etiqueta(t)
                h = alto_l * 0.80
                r = QRectF(x0 + x, y + (alto_l - h) / 2, w, h)
                radio = h / 2 if pastilla else h * 0.22
                camino = QPainterPath()
                camino.addRoundedRect(r, radio, radio)
                p.fillPath(camino.translated(0, max(1.0, h * 0.06)), QColor(0, 0, 0, 45))
                g = QLinearGradient(r.topLeft(), r.bottomLeft())
                g.setColorAt(0, col.lighter(118))
                g.setColorAt(1, col)
                p.fillPath(camino, QBrush(g))
                p.setPen(QPen(QColor(255, 255, 255, 70), 1))
                p.drawPath(camino)
                p.setFont(fe)
                p.setPen(QColor("white"))
                p.drawText(r, Qt.AlignCenter, t)
            else:
                _, t, w, b = item
                p.setFont(fb if b else f)
                p.setPen(QColor("#15171c"))
                p.drawText(QRectF(x0 + x, y, w + 4, alto_l), Qt.AlignVCenter | Qt.AlignLeft, t)


def _texto_ajustado(p: QPainter, r: QRectF, texto: str, color: QColor, negrita=True, px_max=None):
    f = QFont()
    f.setBold(negrita)
    px = px_max or r.height() * 0.62
    while px > 6:
        f.setPixelSize(int(px))
        p.setFont(f)
        if p.fontMetrics().horizontalAdvance(texto) <= r.width():
            break
        px *= 0.92
    p.setPen(color)
    p.drawText(r, Qt.AlignVCenter | Qt.AlignLeft, texto)


def componer(original: QPixmap, defn, idioma: str) -> QPixmap | None:
    """Copia en memoria con el texto traducido encima, o None si no hay traducción."""
    texto = defn.texto.get(idioma) or (defn.texto.get("es") if idioma != "es" else None)
    nombre = defn.nombre.get(idioma) or defn.nombre.get("es")
    if not texto and not nombre:
        return None
    tipo = defn.tipo if defn.tipo in PLANTILLAS else "personaje"
    if tipo == "caso" and original.width() < original.height():
        tipo = "personaje"          # por si una imagen de Caso viniera en vertical
    pix = original.copy()
    W, H = pix.width(), pix.height()
    marco = QColor(COLOR_MARCO.get(defn.colores[0] if defn.colores else "", "#333333"))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    img = original.toImage().convertToFormat(QImage.Format_ARGB32_Premultiplied)
    ref = min(W, H)

    # --- caja de texto: sin marco, fondo difuminado con fundido hacia arriba
    if texto:
        t = PLANTILLAS[tipo]
        x0, x1 = t["x0"] * W, t["x1"] * W
        abajo = t["abajo"] * H
        ja = defn.texto.get("ja", "")
        alto_original = (_lineas_japonesas(ja, t["cap"]) * t["linea"] + 0.018) * H if ja else t["min_alto"] * H
        alto_original = max(alto_original, t["min_alto"] * H)
        mx, my = 0.034 * W, 0.020 * ref
        ancho = x1 - x0 - 2 * mx
        # primero intenta caber en el hueco original; si no, crece hacia arriba hasta un 45 %
        px = 0.033 * ref
        while True:
            lineas, alto_l, fuentes = _maquetar(texto, ancho, px)
            alto_txt = len(lineas) * alto_l
            if alto_txt + 2 * my <= alto_original or px <= 0.021 * ref:
                break
            px *= 0.95
        while alto_txt + 2 * my > 0.45 * H and px > 0.016 * ref:
            px *= 0.95
            lineas, alto_l, fuentes = _maquetar(texto, ancho, px)
            alto_txt = len(lineas) * alto_l
        alto = max(alto_original, alto_txt + 2 * my)
        fundido = 0.07 * H
        caja = QRectF(x0, abajo - alto - fundido, x1 - x0, alto + fundido)
        for ex0, ex1, eabajo in EXTRA.get(tipo, []):
            tira = QRectF(caja.right() - 0.02 * W, caja.top(), ex1 * W - caja.right() + 0.02 * W,
                          eabajo * H - caja.top())
            p.drawImage(tira.topLeft(), _capa(img, tira, VELO, arriba=fundido))
        p.drawImage(caja.topLeft(), _capa(img, caja, VELO, arriba=fundido))
        _pintar_texto(p, lineas, alto_l, fuentes, x0 + mx, abajo - alto + my)

    # --- nombre: nube del color del marco, difuminada por los cuatro lados
    ja_nombre = defn.nombre.get("ja", "")
    if nombre and ja_nombre and nombre != ja_nombre and not ja_nombre.isascii():
        a, b, c, d = NOMBRE[tipo]
        zona = QRectF(a * W, b * H, (c - a) * W, (d - b) * H)
        fn = QFont()
        fn.setBold(True)
        px = zona.height() * 0.50
        while px > 8:
            fn.setPixelSize(int(px))
            if QFontMetricsF(fn).horizontalAdvance(nombre) <= zona.width() - 0.06 * W:
                break
            px *= 0.93
        pluma = 0.036 * W
        # cubre toda la zona del nombre original (el japonés suele ser más largo que la traducción)
        ancho_n = max(QFontMetricsF(fn).horizontalAdvance(nombre) + 2 * pluma + 0.02 * W,
                      zona.width() + 1.6 * pluma)
        # se alarga hacia abajo: las letras japonesas bajan más que la zona del nombre
        nube = QRectF(zona.left() - pluma * 0.6, zona.top() - 0.008 * H,
                      min(ancho_n, W - zona.left() + pluma * 0.6), zona.height() + 0.052 * H)
        velo = QColor(marco)
        velo.setAlpha(238)
        p.drawImage(nube.topLeft(), _capa(img, nube, velo, lado=pluma, arriba=0.016 * H, abajo=0.022 * H))
        p.setFont(fn)
        texto_r = QRectF(nube.left() + pluma, zona.top(), nube.width() - pluma, zona.height())
        sombra = max(1.0, px * 0.05)
        p.setPen(QColor(0, 0, 0, 110))
        p.drawText(texto_r.translated(sombra, sombra), Qt.AlignVCenter | Qt.AlignLeft, nombre)
        p.setPen(QColor("white"))
        p.drawText(texto_r, Qt.AlignVCenter | Qt.AlignLeft, nombre)

    # --- rasgos (cajitas de arriba a la derecha)
    rasgos = defn.rasgos_trad.get(idioma) or defn.rasgos_trad.get("es") or []
    if rasgos and tipo in RASGOS:
        a, b, y, h, paso = RASGOS[tipo]
        for i, rasgo in enumerate(rasgos[:4]):
            r = QRectF(a * W, (y + i * paso) * H, (b - a) * W, h * H)
            camino = QPainterPath()
            camino.addRoundedRect(r, r.height() * 0.2, r.height() * 0.2)
            p.fillPath(camino, QColor("white"))
            p.setPen(QPen(QColor("#888"), 1))
            p.drawPath(camino)
            interior = r.adjusted(r.height() * 0.25, 0, -r.height() * 0.15, 0)
            _texto_ajustado(p, interior, rasgo, QColor("#1a1a1a"), negrita=False, px_max=r.height() * 0.78)
    p.end()
    return pix
