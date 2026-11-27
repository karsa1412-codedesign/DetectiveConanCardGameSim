"""Menú principal: botones con forma repartidos por la pantalla según su función.

  · Arriba a la izquierda, tres óvalos superpuestos en diagonal: Tutorial (verde), En local
    (blanco) y Contra la IA (rojo). Al pasar el ratón, el óvalo crece un 15 %, se pone delante y
    se ilumina; los otros se oscurecen.
  · Arriba en el centro, el círculo VS Online (amarillo, próximamente).
  · A la derecha, dos cartas grandes (proporción 63×88): Creador de mazos y Cartas y descargas.
  · En el centro, el recuadro semitransparente con el mazo más usado.
  · Abajo, el cartel «Personalizaciones» y tres cartas: Traducciones, Fundas y Tapetes.
  · Al pie, Registro de accesos y Cambiar perfil, y una línea con el saludo y las estadísticas.

Todo se coloca sobre un lienzo de referencia (1280×800) que se escala al tamaño de la ventana.
Los botones tienen fondo de adoquín (recursos/adoquin.png, en gris) teñido de su color.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PySide6.QtWidgets import QAbstractButton, QPushButton, QWidget

REF_W, REF_H = 1280, 820
ORO = QColor("#d9a845")
CARTA = 88 / 63                 # alto / ancho de una carta de TCG

COLORES = {"verde": QColor("#56ad5e"), "blanco": QColor("#ffffff"), "rojo": QColor("#d8463c"),
           "amarillo": QColor("#ffdc55"), "marron": QColor("#9a6640")}


class Texturas:
    """Adoquín teñido de cada color, generado una vez."""

    def __init__(self, ruta):
        self.gris = QPixmap(str(ruta))
        self.cache: dict = {}

    def de(self, color: QColor) -> QPixmap:
        k = color.name()
        if k not in self.cache:
            pix = QPixmap(self.gris.size() if not self.gris.isNull() else QRect(0, 0, 64, 64).size())
            pix.fill(color)
            if not self.gris.isNull():
                p = QPainter(pix)
                p.setCompositionMode(QPainter.CompositionMode_Multiply)
                p.drawPixmap(0, 0, self.gris)
                p.end()
            self.cache[k] = pix
        return self.cache[k]


def _fuente(px: float, negrita=True) -> QFont:
    f = QFont()
    f.setPixelSize(max(7, int(px)))
    f.setBold(negrita)
    return f


def _texto(p: QPainter, rect: QRectF, texto: str, color: QColor, px: float):
    """Texto en mayúsculas y negrita, centrado; reduce la letra hasta que quepa cada palabra."""
    from PySide6.QtGui import QFontMetricsF
    texto = texto.upper()
    for _ in range(30):
        f = _fuente(px)
        fm = QFontMetricsF(f)
        ancho = max((fm.horizontalAdvance(w) for w in texto.split()), default=0)
        alto = fm.boundingRect(rect, int(Qt.AlignCenter | Qt.TextWordWrap), texto).height()
        if (ancho <= rect.width() and alto <= rect.height()) or px <= 7:
            break
        px *= 0.92
    p.setFont(_fuente(px))
    flags = Qt.AlignCenter | Qt.TextWordWrap
    if color.lightness() > 128:          # letra clara: sombra oscura para que se lea sobre el adoquín
        p.setPen(QColor(0, 0, 0, 160))
        p.drawText(rect.translated(1.2, 1.5), flags, texto)
    else:                                # letra oscura: halo claro alrededor
        p.setPen(QColor(255, 255, 255, 150))
        d = max(1.2, px * 0.07)
        for dx, dy in ((-d, 0), (d, 0), (0, -d), (0, d), (-d, -d), (d, d), (-d, d), (d, -d)):
            p.drawText(rect.translated(dx, dy), flags, texto)
    p.setPen(color)
    p.drawText(rect, flags, texto)


class BotonForma(QAbstractButton):
    """Base: dibuja una forma con adoquín teñido y borde; la zona de clic es la propia forma."""

    def __init__(self, menu, color: str, borde: QColor, letra: QColor):
        super().__init__(menu)
        self.menu = menu
        self.color = COLORES[color]
        self.borde = borde
        self.letra = letra
        self.titulo = ""
        self.subtitulo = ""
        self.oscuro = False
        self.encima = False
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

    def textos(self, titulo: str, subtitulo: str = ""):
        self.titulo, self.subtitulo = titulo, subtitulo
        self.setToolTip(subtitulo)
        self.update()

    def forma(self, r: QRectF) -> QPainterPath:
        raise NotImplementedError

    def zona_texto(self, r: QRectF) -> QRectF:
        return r.adjusted(r.width() * 0.12, r.height() * 0.15, -r.width() * 0.12, -r.height() * 0.15)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.setMask(QRegion(self.forma(QRectF(self.rect())).toFillPolygon().toPolygon()))

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        grosor = max(3.0, self.width() * 0.022)
        r = QRectF(self.rect()).adjusted(grosor / 2 + 1, grosor / 2 + 1, -grosor / 2 - 1, -grosor / 2 - 1)
        camino = self.forma(r)
        p.save()
        p.setClipPath(camino)
        tex = self.menu.texturas.de(self.color)
        p.drawPixmap(QRectF(self.rect()), tex, QRectF(0, 0, min(tex.width(), self.width() * 1.6),
                                                       min(tex.height(), self.height() * 1.6)))
        if self.encima:
            p.fillRect(self.rect(), QColor(255, 255, 255, 45))
        if self.oscuro:
            p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        elif not self.isEnabled():
            p.fillRect(self.rect(), QColor(20, 28, 48, 40))
        p.restore()
        borde = QColor(self.borde)
        if self.encima:
            borde = borde.lighter(125)
        p.setPen(QPen(borde, grosor))
        p.setBrush(Qt.NoBrush)
        p.drawPath(camino)
        letra = QColor(self.letra)
        if not self.isEnabled():
            letra.setAlpha(200)
        zt = self.zona_texto(r)
        alto = self.height()
        if self.subtitulo and not self.isEnabled():
            _texto(p, QRectF(zt.x(), zt.y(), zt.width(), zt.height() * 0.7), self.titulo, letra, self._px())
            _texto(p, QRectF(zt.x(), zt.y() + zt.height() * 0.6, zt.width(), zt.height() * 0.35),
                   self.subtitulo, letra, self._px() * 0.6)
        else:
            _texto(p, zt, self.titulo, letra, self._px())
        p.end()

    def _px(self) -> float:
        return self.menu.escala * 22

    def enterEvent(self, ev):
        self.encima = True
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.encima = False
        self.update()
        super().leaveEvent(ev)


class BotonOvalo(BotonForma):
    """Modo de juego: óvalo con borde dorado. Crece un 15 % con el ratón encima."""

    def __init__(self, menu, color, letra, orden: int):
        super().__init__(menu, color, ORO, letra)
        self.orden = orden
        self.base = QRect()

    def forma(self, r):
        c = QPainterPath()
        c.addEllipse(r)
        return c

    def zona_texto(self, r):
        # el texto va en la parte que no tapa el óvalo siguiente (arriba a la izquierda),
        # salvo en el de encima del todo o cuando está ampliado
        if self.encima or self.orden == 2:
            return r.adjusted(r.width() * 0.16, r.height() * 0.2, -r.width() * 0.16, -r.height() * 0.2)
        return QRectF(r.x() + r.width() * 0.14, r.y() + r.height() * 0.14, r.width() * 0.52, r.height() * 0.36)

    def _px(self):
        return self.menu.escala * (25 if self.encima else 22)

    def enterEvent(self, ev):
        super().enterEvent(ev)
        self.menu.resaltar_ovalo(self)

    def leaveEvent(self, ev):
        super().leaveEvent(ev)
        self.menu.resaltar_ovalo(None)


class BotonCirculo(BotonOvalo):
    def zona_texto(self, r):
        return r.adjusted(r.width() * 0.12, r.height() * 0.25, -r.width() * 0.12, -r.height() * 0.25)

    def _px(self):
        return self.menu.escala * 26


class BotonCarta(BotonForma):
    """Herramienta: carta vertical (63×88) con esquinas redondeadas y borde blanco."""

    def __init__(self, menu, escala_letra: float = 1.0):
        super().__init__(menu, "marron", QColor("white"), QColor("white"))
        self.escala_letra = escala_letra

    def forma(self, r):
        c = QPainterPath()
        radio = r.width() * 0.075
        c.addRoundedRect(r, radio, radio)
        return c

    def zona_texto(self, r):
        return r.adjusted(r.width() * 0.08, r.height() * 0.1, -r.width() * 0.08, -r.height() * 0.1)

    def _px(self):
        return self.menu.escala * 21 * self.escala_letra


class PanelMazo(QWidget):
    """Recuadro semitransparente con el mazo más usado y su Compañero."""

    def __init__(self, menu):
        super().__init__(menu)
        self.menu = menu
        self.titulo = ""
        self.nombre = ""
        self.lineas: list[str] = []
        self.imagen: QPixmap | None = None
        self.vacio = ""

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        e = self.menu.escala
        p.setPen(QPen(QColor(255, 255, 255, 70), 1.2))
        p.setBrush(QColor(255, 255, 255, 24))
        p.drawRoundedRect(r, 16 * e, 16 * e)
        p.setFont(_fuente(17 * e))
        p.setPen(ORO)
        p.drawText(QRectF(r.x(), r.y() + 12 * e, r.width(), 26 * e), Qt.AlignCenter, self.titulo.upper())
        if not self.nombre:
            p.setFont(_fuente(15 * e, False))
            p.setPen(QColor("#cfd6e4"))
            p.drawText(r.adjusted(30 * e, 50 * e, -30 * e, -20 * e), Qt.AlignCenter | Qt.TextWordWrap, self.vacio)
            p.end()
            return
        alto_img = r.height() - 70 * e
        ancho_img = alto_img / CARTA
        zona = QRectF(r.x() + 22 * e, r.y() + 50 * e, ancho_img, alto_img)
        if self.imagen is not None and not self.imagen.isNull():
            camino = QPainterPath()
            camino.addRoundedRect(zona, 8 * e, 8 * e)
            p.save()
            p.setClipPath(camino)
            p.drawPixmap(zona, self.imagen, QRectF(self.imagen.rect()))
            p.restore()
        else:
            p.setPen(QPen(QColor(255, 255, 255, 90), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(zona, 8 * e, 8 * e)
        x = zona.right() + 22 * e
        ancho = r.right() - x - 18 * e
        p.setFont(_fuente(21 * e))
        p.setPen(QColor("white"))
        p.drawText(QRectF(x, zona.y(), ancho, 30 * e), Qt.AlignLeft | Qt.AlignVCenter, self.nombre)
        from PySide6.QtGui import QFontMetricsF
        f = _fuente(14 * e, False)
        p.setFont(f)
        fm = QFontMetricsF(f)
        p.setPen(QColor("#cfd6e4"))
        y = zona.y() + 42 * e
        for l in self.lineas:
            caja = QRectF(x, y, ancho, 60 * e)
            alto = fm.boundingRect(caja, int(Qt.AlignLeft | Qt.TextWordWrap), l).height()
            p.drawText(caja, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, l)
            y += alto + 8 * e
        p.end()


class Cartel(QWidget):
    """Rótulo «PERSONALIZACIONES»: no es un botón."""

    def __init__(self, menu):
        super().__init__(menu)
        self.menu = menu
        self.texto = ""

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        e = self.menu.escala
        g = max(3.0, 5 * e)
        r = QRectF(self.rect()).adjusted(g / 2, g / 2, -g / 2, -g / 2)
        p.setPen(QPen(QColor("#3b7be0"), g))
        p.setBrush(QColor(10, 20, 40, 110))
        p.drawRoundedRect(r, 8 * e, 8 * e)
        _texto(p, r, self.texto, QColor("white"), 22 * e)
        p.end()


class PaginaMenu(QWidget):
    # posiciones en el lienzo de referencia (x, y, ancho, alto)
    OVALOS = [(30, 30, 330, 180), (140, 125, 330, 180), (250, 220, 330, 180)]
    ONLINE = (560, 22, 200, 200)
    CARTAS_DER = [(1018, 22, 225, 225 * CARTA), (1018, 22 + 225 * CARTA + 18, 225, 225 * CARTA)]
    PANEL = (600, 250, 390, 285)
    CARTEL = (30, 560, 853, 50)
    CARTAS_ABAJO_ALTO = 140

    def __init__(self, ventana):
        super().__init__()
        self.v = ventana
        self.escala = 1.0
        self.texturas = Texturas(ventana.base / "recursos" / "adoquin.png")
        self.ovalos = [BotonOvalo(self, "verde", QColor("white"), 0),
                       BotonOvalo(self, "blanco", QColor("#111111"), 1),
                       BotonOvalo(self, "rojo", QColor("white"), 2)]
        for b, fn in zip(self.ovalos, (ventana.iniciar_tutorial, ventana.iniciar_local, ventana.iniciar_ia)):
            b.clicked.connect(fn)
        self.online = BotonCirculo(self, "amarillo", QColor("#111111"), 3)
        self.online.setEnabled(False)
        self.mazos = BotonCarta(self, 1.15)
        self.mazos.clicked.connect(ventana.ir_a_mazos)
        self.contenido = BotonCarta(self, 1.15)
        self.contenido.clicked.connect(ventana.ir_a_contenido)
        self.panel = PanelMazo(self)
        self.cartel = Cartel(self)
        self.traducciones = BotonCarta(self, 0.72)
        self.traducciones.clicked.connect(ventana.ir_a_traducciones)
        self.fundas = BotonCarta(self, 0.72)
        self.fundas.clicked.connect(ventana.elegir_fundas)
        self.tapetes = BotonCarta(self, 0.72)
        self.tapetes.setEnabled(False)
        self.btn_registro = QPushButton(self)
        self.btn_registro.clicked.connect(self._ver_registro)
        self.btn_perfil = QPushButton(self)
        self.btn_perfil.clicked.connect(ventana.cambiar_perfil)
        for b in (self.btn_registro, self.btn_perfil):
            b.setStyleSheet("font-weight:bold;")
        from PySide6.QtWidgets import QLabel
        self.hola = QLabel(self)
        self.hola.setAlignment(Qt.AlignCenter)
        self.hola.setWordWrap(True)
        self.hola.setStyleSheet("color:#a9b1c2;background:transparent;")
        # atributos que usaba el menú anterior (pruebas y otras pantallas)
        self.botones = {"tutorial": self.ovalos[0], "local": self.ovalos[1], "ia": self.ovalos[2],
                        "online": self.online, "mazos": self.mazos, "contenido": self.contenido,
                        "traducciones": self.traducciones, "fundas": self.fundas, "tapetes": self.tapetes}

    # ---------------------------------------------------------------- colocación

    def _r(self, x, y, w, h) -> QRect:
        e = self.escala
        return QRect(int(self.dx + x * e), int(self.dy + y * e), int(w * e), int(h * e))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.escala = min(self.width() / REF_W, self.height() / REF_H)
        self.dx = (self.width() - REF_W * self.escala) / 2
        self.dy = (self.height() - REF_H * self.escala) / 2
        for b, (x, y, w, h) in zip(self.ovalos, self.OVALOS):
            b.base = self._r(x, y, w, h)
            b.setGeometry(b.base)
        self.online.base = self._r(*self.ONLINE)
        self.online.setGeometry(self.online.base)
        self.mazos.setGeometry(self._r(*self.CARTAS_DER[0]))
        self.contenido.setGeometry(self._r(*self.CARTAS_DER[1]))
        self.panel.setGeometry(self._r(*self.PANEL))
        cx, cy, cw, ch = self.CARTEL
        self.cartel.setGeometry(self._r(cx, cy, cw, ch))
        alto = self.CARTAS_ABAJO_ALTO
        ancho = alto / CARTA
        for i, b in enumerate((self.traducciones, self.fundas, self.tapetes)):
            centro = cx + cw * (2 * i + 1) / 6
            b.setGeometry(self._r(centro - ancho / 2, cy + ch + 14, ancho, alto))
        self.btn_registro.setGeometry(self._r(330, 778, 230, 34))
        self.btn_perfil.setGeometry(self._r(580, 778, 230, 34))
        self.hola.setGeometry(self._r(1000, 684, 262, 128))
        f = self.hola.font()
        f.setPixelSize(max(8, int(12 * self.escala)))
        self.hola.setFont(f)
        self.resaltar_ovalo(None)

    def resaltar_ovalo(self, activo):
        """El óvalo con el ratón encima crece un 15 % y pasa delante; los demás se oscurecen."""
        for b in self.ovalos:
            b.oscuro = activo is not None and b is not activo
            if b is activo:
                g = b.base
                dw, dh = int(g.width() * 0.075), int(g.height() * 0.075)
                b.setGeometry(g.adjusted(-dw, -dh, dw, dh))
            else:
                b.setGeometry(b.base)
            b.update()
        for b in self.ovalos:          # orden normal: tutorial debajo, IA encima
            b.raise_()
        if activo is not None:
            activo.raise_()

    # ---------------------------------------------------------------- textos y datos

    def refrescar(self):
        tx = self.v.tx
        p = self.v.perfiles.perfiles[self.v.perfil]
        self.ovalos[0].textos(tx("menu_b_tutorial"), tx("modo_tutorial_desc"))
        self.ovalos[1].textos(tx("menu_b_local"), tx("modo_local_desc"))
        self.ovalos[2].textos(tx("menu_b_ia"), tx("modo_ia_desc"))
        self.online.textos(tx("menu_b_online"), tx("proximamente"))
        self.mazos.textos(tx("modo_mazos"), tx("modo_mazos_desc"))
        self.contenido.textos(tx("modo_contenido"), tx("modo_contenido_desc"))
        self.traducciones.textos(tx("modo_traducciones"), tx("modo_traducciones_desc"))
        self.fundas.textos(tx("modo_fundas"), tx("modo_fundas_desc", funda=self.v.funda_perfil()))
        self.tapetes.textos(tx("menu_b_tapetes"), tx("proximamente"))
        self.cartel.texto = tx("menu_personalizaciones")
        self.btn_registro.setText(tx("ver_registro"))
        self.btn_perfil.setText(tx("cambiar_perfil"))
        hola = tx("menu_hola", nombre=p["nombre"]) + "\n" + tx(
            "estadisticas", ini=p.get("partidas_iniciadas", 0), fin=p.get("partidas_terminadas", 0),
            tut=p.get("tutoriales_completados", 0))
        if p.get("ia_victorias", 0) or p.get("ia_derrotas", 0):
            hola += "\n" + tx("estadisticas_ia", g=p.get("ia_victorias", 0), p=p.get("ia_derrotas", 0))
        self.hola.setText(hola)
        self._panel_mazo()
        for w in self.findChildren(QWidget):
            w.update()

    def _panel_mazo(self):
        tx, v = self.v.tx, self.v
        self.panel.titulo = tx("menu_mazo_usado")
        self.panel.vacio = tx("menu_mazo_vacio")
        fav = v.perfiles.mazo_favorito(v.perfil)
        if fav is None:
            self.panel.nombre = ""
            return
        nombre, e = fav
        comp = max(e["companeros"], key=e["companeros"].get) if e.get("companeros") else None
        if comp is None:
            comp = next((m.companero for _, m, _ in v.mazos_disponibles() if m.nombre == nombre), None)
        self.panel.nombre = nombre
        self.panel.imagen = None
        defn = v.catalogo.por_id.get(comp) if comp else None
        if defn is not None:
            try:
                self.panel.imagen = v.mesa._frente(defn)
            except Exception:
                self.panel.imagen = None
        ganadas, perdidas = e.get("victorias", 0), e.get("derrotas", 0)
        self.panel.lineas = [
            tx("menu_mazo_partidas", n=e.get("partidas", 0)),
            tx("menu_mazo_ia", g=ganadas, p=perdidas),
        ]
        if defn is not None:
            self.panel.lineas.append(tx("menu_mazo_companero", nombre=defn.nombre_en(tx.idioma)))
        if e.get("ultima"):
            self.panel.lineas.append(tx("menu_mazo_ultima", fecha=e["ultima"][:10]))

    def _ver_registro(self):
        from .pantallas import DialogoRegistro
        DialogoRegistro(self.v).exec()
