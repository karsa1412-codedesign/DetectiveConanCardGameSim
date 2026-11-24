"""Mesa de juego gráfica: tapete con zonas, cartas animadas y arrastrar y soltar.

Cada carta visible es un objeto que persiste entre refrescos (por uid), así que cuando el
motor cambia el estado, la carta se desliza a su nueva posición y gira al dormirse (90°) o
aturdirse (180°). Las jugadas se pueden hacer arrastrando:

  mano → tu Escena ............ Jugar carta (sobre un Personaje propio si la escena está llena: Cambio)
  Personaje → Personaje rival . Acción contra él         Personaje → Caso rival ... Acción al Caso
  Personaje / Compañero → tus Pruebas ... Deducir        Compañero → tu FILE ...... Asistir
  Compañero → tu Caso ......... Resolver el caso         FILE → tu mano ........... Siguiente pista
  Irrupción o Disfraz (en Contacto) → la Escena ... usar  Personaje → lado rival ... Guardar

Un clic abre el menú de la carta con todas sus opciones, como antes.
"""
from __future__ import annotations

from PySide6.QtCore import (QEasingCurve, QLineF, QPointF, QPropertyAnimation, QRectF, Qt,
                            QParallelAnimationGroup)
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import (QGraphicsDropShadowEffect, QGraphicsLineItem, QGraphicsObject, QGraphicsScene,
                               QGraphicsSimpleTextItem, QGraphicsView)

from core import acciones as A
from core.estado import ATURDIDO, DORMIDO

CW, CH = 92, 129                      # tamaño de carta en la mesa
ANCHO_MESA, ALTO_MESA = 1500, 960
DURACION = 320                        # ms de cada animación
ORO = QColor("#d9a845")
NARANJA = QColor("#ff8a1e")
COLORES = {"azul": "#2f5fa8", "rojo": "#b23b3b", "verde": "#2f8a4e", "amarillo": "#c49a1a",
           "blanco": "#8c8c8c", "negro": "#3a3a3a"}

# centros de zona para el jugador de abajo; el de arriba es su reflejo vertical
POS = {"caso": (115, 565), "companero": (275, 565), "extra": (275, 720),
       "mazo": (1215, 565), "descarte": (1355, 565), "file": (1215, 722), "pruebas": (1355, 722)}
ESCENA_Y, MANO_Y = 565, 872
ESCENA_X0, ESCENA_PASO = 428, 138


def _y(lado: int, y: float) -> float:
    return y if lado == 0 else ALTO_MESA - y


def cara_generica(defn, idioma: str) -> QPixmap:
    """Cara de carta dibujada (para cartas sin imagen descargada)."""
    w, h = 360, 504
    apaisada = defn.tipo == "caso"
    if apaisada:
        w, h = h, w
    pix = QPixmap(w, h)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    camino = QPainterPath()
    camino.addRoundedRect(QRectF(0, 0, w, h), 20, 20)
    p.setClipPath(camino)
    base = QColor(COLORES.get(defn.colores[0] if defn.colores else "", "#555"))
    g = QLinearGradient(0, 0, 0, h)
    g.setColorAt(0, base.lighter(125))
    g.setColorAt(1, base.darker(130))
    p.fillRect(pix.rect(), QBrush(g))
    p.fillRect(QRectF(16, 70, w - 32, h * 0.52), QColor(255, 255, 255, 40))
    f = QFont()
    f.setBold(True)
    f.setPixelSize(44)
    p.setFont(f)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("white"))
    p.drawEllipse(QPointF(46, 42), 30, 30)
    p.setPen(base.darker(120))
    marca = str(defn.nivel) if defn.tipo in ("personaje", "evento") else defn.tipo[:1].upper()
    p.drawText(QRectF(16, 12, 60, 60), Qt.AlignCenter, marca)
    p.setPen(QColor("white"))
    f.setPixelSize(30)
    p.setFont(f)
    p.drawText(QRectF(88, 14, w - 100, 56), Qt.AlignVCenter | Qt.TextWordWrap, defn.nombre_en(idioma))
    f.setBold(False)
    f.setPixelSize(19)
    p.setFont(f)
    texto = defn.texto_en(idioma)
    p.drawText(QRectF(24, h * 0.62, w - 48, h * 0.27), Qt.TextWordWrap, texto[:220])
    if defn.tipo == "personaje":
        f.setBold(True)
        f.setPixelSize(40)
        p.setFont(f)
        p.drawText(QRectF(0, h - 64, w - 24, 56), Qt.AlignRight | Qt.AlignVCenter, f"{defn.ap}  ·  {defn.lp}")
    p.end()
    return pix


class CartaItem(QGraphicsObject):
    def __init__(self, mesa: "Mesa", uid: int):
        super().__init__()
        self.mesa, self.uid = mesa, uid
        self.frente: QPixmap | None = None
        self.dorso: QPixmap | None = None
        self.boca_arriba = True
        self.apaisada = False
        self.resaltado = False
        self.objetivo = False         # resaltado de destino válido durante un arrastre
        self.arrastrable = False
        self.en_mano = False
        self._inicio = None
        self._arrastrando = False
        self._origen = QPointF()
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        sombra = QGraphicsDropShadowEffect()
        sombra.setBlurRadius(16)
        sombra.setOffset(3, 4)
        sombra.setColor(QColor(0, 0, 0, 150))
        self.setGraphicsEffect(sombra)

    def boundingRect(self) -> QRectF:
        w, h = (CH, CW) if self.apaisada else (CW, CH)
        return QRectF(-w / 2 - 4, -h / 2 - 4, w + 8, h + 8)

    def paint(self, p: QPainter, opt, widget=None):
        w, h = (CH, CW) if self.apaisada else (CW, CH)
        r = QRectF(-w / 2, -h / 2, w, h)
        pix = self.frente if self.boca_arriba else self.dorso
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        camino = QPainterPath()
        camino.addRoundedRect(r, 6, 6)
        if pix is not None and not pix.isNull():
            p.save()
            p.setClipPath(camino)
            if not self.boca_arriba and self.apaisada:   # dorso en una carta apaisada
                p.translate(0, 0)
                p.rotate(90)
                p.drawPixmap(QRectF(-h / 2, -w / 2, h, w), pix, QRectF(pix.rect()))
            else:
                p.drawPixmap(r, pix, QRectF(pix.rect()))
            p.restore()
        else:
            p.fillPath(camino, QColor("#444"))
        if self.resaltado or self.objetivo:
            p.setPen(QPen(NARANJA if self.resaltado else ORO, 4))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 8, 8)

    # --------------------------------------------------------- ratón
    def hoverEnterEvent(self, ev):
        if self.en_mano and not self._arrastrando:
            self.setZValue(500)
            self.setScale(1.18)
        if self.boca_arriba:
            self.mesa.previa(self, ev.screenPos())
        super().hoverEnterEvent(ev)

    def hoverLeaveEvent(self, ev):
        if self.en_mano and not self._arrastrando:
            self.setScale(1.0)
            self.setZValue(self.data(0) or 10)
        self.mesa.ocultar_previa()
        super().hoverLeaveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._inicio = ev.scenePos()
            self._origen = self.pos()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._inicio is None:
            return
        if not self._arrastrando and self.arrastrable and (ev.scenePos() - self._inicio).manhattanLength() > 8:
            self._arrastrando = True
            self.mesa.ocultar_previa()
            self.setZValue(900)
            self.setScale(1.08)
            self.mesa.empezar_arrastre(self)
        if self._arrastrando:
            self.setPos(self._origen + (ev.scenePos() - self._inicio))

    def mouseReleaseEvent(self, ev):
        if self._inicio is None:
            return
        if self._arrastrando:
            self._arrastrando = False
            self.setScale(1.0)
            self.mesa.soltar(self, ev.scenePos())
        elif ev.button() == Qt.LeftButton:
            self.mesa.clic(self, ev.screenPos())
        self._inicio = None

    def mouseDoubleClickEvent(self, ev):
        self.mesa.doble_clic(self)


class Pila(QGraphicsObject):
    """Mazo, FILE o Pruebas: un montón de dorsos con su número."""

    def __init__(self, mesa: "Mesa", clave: tuple):
        super().__init__()
        self.mesa, self.clave = mesa, clave
        self.n = 0
        self.dorso: QPixmap | None = None
        self.apaisada = False
        self.resaltado = False
        self.objetivo = False
        self.arrastrable = False
        self._inicio = None
        self._arrastrando = False
        self.setAcceptHoverEvents(True)

    def boundingRect(self):
        w, h = (CH, CW) if self.apaisada else (CW, CH)
        return QRectF(-w / 2 - 8, -h / 2 - 8, w + 16, h + 16)

    def paint(self, p: QPainter, opt, widget=None):
        w, h = (CH, CW) if self.apaisada else (CW, CH)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        capas = min(5, self.n)
        for i in range(capas):
            off = (capas - 1 - i) * 1.6
            r = QRectF(-w / 2 + off, -h / 2 - off, w, h)
            camino = QPainterPath()
            camino.addRoundedRect(r, 6, 6)
            if self.dorso is not None:
                p.save()
                p.setClipPath(camino)
                if self.apaisada:
                    p.translate(r.center())
                    p.rotate(90)
                    p.drawPixmap(QRectF(-h / 2, -w / 2, h, w), self.dorso, QRectF(self.dorso.rect()))
                else:
                    p.drawPixmap(r, self.dorso, QRectF(self.dorso.rect()))
                p.restore()
            p.setPen(QPen(QColor(0, 0, 0, 110), 1))
            p.drawPath(camino)
        if self.resaltado or self.objetivo:
            p.setPen(QPen(NARANJA if self.resaltado else ORO, 4))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(-w / 2 - 3, -h / 2 - 3, w + 6, h + 6), 8, 8)
        # número
        f = QFont()
        f.setBold(True)
        f.setPixelSize(22)
        p.setFont(f)
        circulo = QRectF(w / 2 - 22, h / 2 - 22, 34, 34)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 14, 22, 220))
        p.drawEllipse(circulo)
        p.setPen(ORO)
        p.drawText(circulo, Qt.AlignCenter, str(self.n))

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.arrastrable:
            self._inicio = ev.scenePos()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._inicio is not None and not self._arrastrando and \
                (ev.scenePos() - self._inicio).manhattanLength() > 8:
            self._arrastrando = True
            self.mesa.empezar_arrastre(self)

    def mouseReleaseEvent(self, ev):
        if self._arrastrando:
            self.mesa.soltar(self, ev.scenePos())
        self._inicio = None
        self._arrastrando = False


class Mesa(QGraphicsView):
    def __init__(self, ventana):
        super().__init__()
        self.v = ventana
        self.escena = QGraphicsScene(0, 0, ANCHO_MESA, ALTO_MESA)
        self.setScene(self.escena)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.items_carta: dict[int, CartaItem] = {}
        self.pilas: dict[tuple, Pila] = {}
        self.zonas: dict[tuple, QRectF] = {}
        self.textos: dict[tuple, QGraphicsSimpleTextItem] = {}
        self.zonas_resaltadas: set = set()
        self.zonas_objetivo: set = set()
        self.fundas = {0: None, 1: None}
        self.motor = None
        self.animaciones = QParallelAnimationGroup()
        self.linea_contacto = QGraphicsLineItem()
        self.linea_contacto.setPen(QPen(NARANJA, 4, Qt.DashLine))
        self.linea_contacto.setZValue(800)
        self.escena.addItem(self.linea_contacto)
        self._montar_zonas()

    # --------------------------------------------------------- tapete
    def drawBackground(self, p: QPainter, rect):
        g = QRadialGradient(ANCHO_MESA / 2, ALTO_MESA / 2, ANCHO_MESA * 0.7)
        g.setColorAt(0, QColor("#1f3a4a"))
        g.setColorAt(1, QColor("#0e1a24"))
        p.fillRect(rect, QBrush(g))
        p.setPen(QPen(QColor(217, 168, 69, 70), 2, Qt.DashLine))
        p.drawLine(QPointF(40, ALTO_MESA / 2), QPointF(ANCHO_MESA - 40, ALTO_MESA / 2))
        for clave, r in self.zonas.items():
            nombre, lado = clave
            resaltada = clave in self.zonas_resaltadas
            objetivo = clave in self.zonas_objetivo
            color = NARANJA if resaltada else (ORO if objetivo else QColor(217, 168, 69, 60))
            p.setPen(QPen(color, 3 if (resaltada or objetivo) else 1.5))
            relleno = QColor(255, 255, 255, 18 if not objetivo else 40)
            p.setBrush(relleno)
            p.drawRoundedRect(r, 10, 10)

    def _montar_zonas(self):
        for lado in (0, 1):
            for nombre, (x, y) in POS.items():
                yy = _y(lado, y)
                w, h = (CH + 22, CW + 30) if nombre in ("caso", "file") else (CW + 22, CH + 22)
                if nombre == "extra":
                    w, h = CW + 22, CH * 0.55
                self.zonas[(nombre, lado)] = QRectF(x - w / 2, yy - h / 2, w, h)
            ey = _y(lado, ESCENA_Y)
            self.zonas[("escena", lado)] = QRectF(ESCENA_X0 - CH / 2 - 8, ey - CH / 2 - 12,
                                                  ESCENA_PASO * 4 + CH + 16, CH + 24)
            my = _y(lado, MANO_Y)
            self.zonas[("mano", lado)] = QRectF(380, my - CH / 2 - 8, 760, CH + 16)
            for nombre in ("caso", "companero", "mazo", "descarte", "file", "pruebas", "escena"):
                t = QGraphicsSimpleTextItem()
                t.setBrush(QColor(217, 168, 69, 170))
                f = QFont()
                f.setPixelSize(13)
                f.setBold(True)
                t.setFont(f)
                t.setZValue(1)
                self.escena.addItem(t)
                self.textos[(nombre, lado)] = t
            info = QGraphicsSimpleTextItem()
            info.setBrush(QColor("#ece6d8"))
            f = QFont()
            f.setPixelSize(15)
            f.setBold(True)
            info.setFont(f)
            self.escena.addItem(info)
            self.textos[("jugador", lado)] = info

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.fitInView(self.escena.sceneRect(), Qt.KeepAspectRatio)

    def showEvent(self, ev):
        super().showEvent(ev)
        self.fitInView(self.escena.sceneRect(), Qt.KeepAspectRatio)

    def vaciar(self):
        """Quita todas las cartas y montones: la siguiente partida empieza con la mesa limpia."""
        self.animaciones.stop()
        for it in list(self.items_carta.values()):
            self.escena.removeItem(it)
        self.items_carta.clear()
        for pila in list(self.pilas.values()):
            self.escena.removeItem(pila)
        self.pilas.clear()
        self.zonas_resaltadas, self.zonas_objetivo = set(), set()
        self.linea_contacto.setVisible(False)
        self.motor = None
        self.escena.update()

    # --------------------------------------------------------- utilidades
    def _lado(self, jugador: int) -> int:
        return 0 if jugador == 0 else 1

    def _frente(self, defn) -> QPixmap:
        pix = self.v.imagenes.mostrar(defn, self.v.tx.idioma)
        if pix is None or pix.isNull():
            clave = ("cara", defn.id, self.v.tx.idioma)
            cache = self.v.imagenes.cache_trad
            if clave not in cache:
                cache[clave] = cara_generica(defn, self.v.tx.idioma)
            pix = cache[clave]
        return pix

    def _dorso(self, jugador: int) -> QPixmap:
        return self.v.fundas.pixmap(self.fundas.get(jugador))

    def _rotulo(self, clave, texto, x, y):
        t = self.textos[clave]
        t.setText(texto)
        b = t.boundingRect()
        t.setPos(x - b.width() / 2, y)

    # --------------------------------------------------------- refresco
    def actualizar(self, motor, ver_mano: dict, animar: bool = True):
        self.motor = motor
        tx = self.v.tx
        p = motor.p
        destinos: dict[int, tuple] = {}   # uid -> (x, y, rotacion, boca_arriba, apaisada, z, en_mano)
        for jugador in (0, 1):
            j = motor.j(jugador)
            lado = self._lado(jugador)
            # Caso y Compañero
            x, y = POS["caso"]
            destinos[j.caso.uid] = (x, _y(lado, y), 0, True, True, 5, False)
            cx, cy = POS["companero"]
            if j.companero_en_file:
                fx, fy = POS["file"]
                destinos[j.companero.uid] = (fx, _y(lado, fy) + (-34 if lado == 0 else 34), 90, True, False, 30, False)
            else:
                destinos[j.companero.uid] = (cx, _y(lado, cy), self._giro(j.companero.estado), True, False, 5, False)
            ex, ey = POS["extra"]
            for i, c in enumerate(j.zona_companero):
                destinos[c.uid] = (ex + i * 18, _y(lado, ey), 0, True, False, 6 + i, False)
            # Escena
            for i, c in enumerate(j.escena):
                destinos[c.uid] = (ESCENA_X0 + i * ESCENA_PASO, _y(lado, ESCENA_Y), self._giro(c.estado), True, False, 10, False)
            # Descarte: la de arriba boca arriba
            dx, dy = POS["descarte"]
            for i, c in enumerate(j.descarte[-3:]):
                destinos[c.uid] = (dx, _y(lado, dy), 0, True, False, 10 + i, False)
            # Mano en abanico
            n = len(j.mano)
            paso = min(CW + 10, 700 / max(1, n))
            x0 = ANCHO_MESA / 2 - paso * (n - 1) / 2
            visible = ver_mano.get(jugador, False)
            for i, c in enumerate(j.mano):
                destinos[c.uid] = (x0 + i * paso, _y(lado, MANO_Y), 0, visible, False, 20 + i, True)
            # pilas
            for nombre, cuantas in (("mazo", len(j.mazo)), ("file", len(j.file)), ("pruebas", len(j.pruebas))):
                self._pila((nombre, lado), jugador, cuantas, nombre == "file")
            # rótulos
            fase = tx("fase_resolucion") if j.caso_resuelto else tx("fase_caso")
            base = 72
            off = (CH / 2 + 8) if lado == 0 else -(CH / 2 + 26)
            self._rotulo(("caso", lado), f"{tx('caso')} · {fase} · {len(j.pruebas)}/{motor.nivel_caso(j)}",
                         POS["caso"][0], _y(lado, POS["caso"][1]) + (CW / 2 + 12 if lado == 0 else -(CW / 2 + 30)))
            self._rotulo(("companero", lado), tx("companero"), POS["companero"][0], _y(lado, POS["companero"][1]) + off)
            self._rotulo(("mazo", lado), tx("mazo"), POS["mazo"][0], _y(lado, POS["mazo"][1]) + off)
            self._rotulo(("descarte", lado), f"{tx('descarte')} ({len(j.descarte)})",
                         POS["descarte"][0], _y(lado, POS["descarte"][1]) + off)
            self._rotulo(("file", lado), f"{tx('file')} ({j.cartas_file})", POS["file"][0],
                         _y(lado, POS["file"][1]) + ((CW / 2 + 12) if lado == 0 else -(CW / 2 + 30)))
            self._rotulo(("pruebas", lado), tx("pruebas"), POS["pruebas"][0], _y(lado, POS["pruebas"][1]) + off)
            self._rotulo(("escena", lado), tx("escena"), ESCENA_X0 - CW / 2 - 4 + 50,
                         _y(lado, ESCENA_Y) + ((CH / 2 + 14) if lado == 0 else -(CH / 2 + 32)))
            decide = p.quien_decide() == jugador and p.ganador is None
            nombre_j = tx("jugador", n=jugador + 1) + ("  ◀" if decide else "")
            self._rotulo(("jugador", lado), nombre_j, 110, ALTO_MESA - 70 if lado == 0 else 40)
            self.textos[("jugador", lado)].setBrush(ORO if decide else QColor("#ece6d8"))
        self._sincronizar(destinos, animar)
        self._contacto()
        self.escena.update()

    def _giro(self, estado: str) -> float:
        return 90 if estado == DORMIDO else (180 if estado == ATURDIDO else 0)

    def _pila(self, clave, jugador, n, apaisada):
        pila = self.pilas.get(clave)
        if pila is None:
            pila = Pila(self, clave)
            pila.setZValue(4)
            self.escena.addItem(pila)
            self.pilas[clave] = pila
        nombre, lado = clave
        x, y = POS[nombre]
        pila.setPos(x, _y(lado, y))
        pila.n = n
        pila.apaisada = apaisada
        pila.dorso = self._dorso(jugador)
        pila.setVisible(n > 0)
        pila.update()

    def _sincronizar(self, destinos: dict, animar: bool):
        self.animaciones.stop()
        self.animaciones = QParallelAnimationGroup()
        for uid in list(self.items_carta):
            if uid not in destinos:
                it = self.items_carta.pop(uid)
                self.escena.removeItem(it)
        for uid, (x, y, rot, cara, apaisada, z, en_mano) in destinos.items():
            c = self.motor.p.carta(uid)
            it = self.items_carta.get(uid)
            nuevo = it is None
            if nuevo:
                it = CartaItem(self, uid)
                self.escena.addItem(it)
                self.items_carta[uid] = it
                lado = self._lado(c.dueno)
                mx, my = POS["mazo"]
                it.setPos(mx, _y(lado, my))     # las cartas nuevas salen del mazo
            it.frente = self._frente(c.defn)
            it.dorso = self._dorso(c.dueno)
            it.boca_arriba = cara
            it.apaisada = apaisada
            it.en_mano = en_mano
            it.setData(0, z)
            it.setZValue(z)
            it.setScale(1.0)
            it.resaltado = it.objetivo = False
            it.prepareGeometryChange()
            it.update()
            destino = QPointF(x, y)
            if animar and (nuevo or it.pos() != destino or it.rotation() != rot):
                a = QPropertyAnimation(it, b"pos")
                a.setDuration(DURACION)
                a.setEndValue(destino)
                a.setEasingCurve(QEasingCurve.OutCubic)
                self.animaciones.addAnimation(a)
                if it.rotation() != rot:
                    g = QPropertyAnimation(it, b"rotation")
                    g.setDuration(DURACION + 120)
                    g.setEndValue(rot)
                    g.setEasingCurve(QEasingCurve.OutBack)
                    self.animaciones.addAnimation(g)
            else:
                it.setPos(destino)
                it.setRotation(rot)
        self.animaciones.start()

    def _contacto(self):
        ct = self.motor.p.contacto if self.motor else None
        if ct and ct.atacante in self.items_carta and ct.defensor in self.items_carta:
            a, d = self.items_carta[ct.atacante], self.items_carta[ct.defensor]
            fin_a = a.pos() if self.animaciones.state() != self.animaciones.State.Running else a.pos()
            self.linea_contacto.setLine(QLineF(fin_a, d.pos()))
            self.linea_contacto.setVisible(True)
        else:
            self.linea_contacto.setVisible(False)

    def terminar_animaciones(self):
        """Lleva todo a su sitio al instante (para capturas y pruebas)."""
        if self.animaciones.state() == self.animaciones.State.Running:
            self.animaciones.setCurrentTime(self.animaciones.totalDuration())
            self.animaciones.stop()
        self._contacto()

    # --------------------------------------------------------- resaltados
    def resaltar(self, claves: list, uids: set):
        self.zonas_resaltadas = set()
        for clave in claves:
            if ":" not in clave:
                continue
            nombre, lado = clave.split(":", 1)
            if nombre == "carta":
                continue
            try:
                lado = self._lado(int(lado))
            except ValueError:
                continue
            if nombre == "info":
                for z in ("mazo", "file", "pruebas"):
                    self.zonas_resaltadas.add((z, lado))
            else:
                self.zonas_resaltadas.add((nombre, lado))
        for uid, it in self.items_carta.items():
            it.resaltado = uid in uids
            it.update()
        for clave, pila in self.pilas.items():
            pila.resaltado = clave in self.zonas_resaltadas
            pila.update()
        self.escena.update()

    # --------------------------------------------------------- interacción
    def previa(self, it: CartaItem, pos):
        if it.frente is not None:
            self.v.vista_previa.mostrar(it.frente, pos.toPoint() if hasattr(pos, "toPoint") else pos)

    def ocultar_previa(self):
        self.v.vista_previa.hide()

    def clic(self, it: CartaItem, pos_pantalla):
        self.ocultar_previa()
        c = self.motor.p.carta(it.uid)
        jug = self.motor.j(c.dueno)
        if not it.boca_arriba and c in jug.mano:
            return
        self.v.menu_carta(c, pos_pantalla.toPoint() if hasattr(pos_pantalla, "toPoint") else pos_pantalla)

    def doble_clic(self, it: CartaItem):
        if it.boca_arriba:
            self.v.ver_en_grande(self.motor.p.carta(it.uid).defn)

    def actualizar_arrastrables(self):
        """Marca qué cartas tienen alguna jugada que se pueda hacer arrastrando."""
        legales = self.v.acciones_permitidas()
        uids = set()
        pista = False
        for a in legales:
            uids |= self._uids_arrastre(a)
            pista = pista or isinstance(a, A.SiguientePista)
        for uid, it in self.items_carta.items():
            it.arrastrable = uid in uids and it.boca_arriba
            it.setCursor(Qt.OpenHandCursor if it.arrastrable else Qt.PointingHandCursor)
        for clave, pila in self.pilas.items():
            pila.arrastrable = pista and clave == ("file", self._lado(self.motor.p.quien_decide()))
            pila.setCursor(Qt.OpenHandCursor if pila.arrastrable else Qt.ArrowCursor)

    def _uids_arrastre(self, a) -> set:
        if isinstance(a, A.JugarCarta) or isinstance(a, A.Deducir) or isinstance(a, A.Guardia):
            return {a.uid} if a.uid is not None else set()
        if isinstance(a, A.Contactar):
            return {a.uid} if a.uid is not None else set()
        if isinstance(a, A.Atacar):
            return {a.atacante}
        if isinstance(a, (A.Asistir, A.ResolverCaso)):
            return {self.motor.j(a.jugador).companero.uid}
        return set()

    def _que_hace(self, origen, pos: QPointF) -> list:
        """Acciones legales que corresponden a soltar origen en pos."""
        m = self.motor
        legales = self.v.acciones_permitidas()
        zona = next((k for k, r in self.zonas.items() if r.contains(pos)), None)
        debajo = None
        for it in self.escena.items(pos):
            if isinstance(it, CartaItem) and it is not origen:
                debajo = it.uid
                break
        out = []
        if isinstance(origen, Pila):
            dueno = 0 if origen.clave[1] == 0 else 1
            if zona == ("mano", origen.clave[1]):
                out = [a for a in legales if isinstance(a, A.SiguientePista)]
            return out
        uid = origen.uid
        c = m.p.carta(uid)
        lado = self._lado(c.dueno)
        rival = 1 - lado
        for a in legales:
            if isinstance(a, A.JugarCarta) and a.uid == uid:
                if a.retirar is not None:
                    if debajo == a.retirar:
                        out.append(a)
                elif zona == ("escena", lado):
                    out.append(a)
            elif isinstance(a, A.Contactar) and a.uid == uid:
                if zona and zona[0] == "escena" or debajo is not None:
                    out.append(a)
            elif isinstance(a, A.Deducir) and a.uid == uid and zona == ("pruebas", lado):
                out.append(a)
            elif isinstance(a, A.Atacar) and a.atacante == uid:
                if a.objetivo is None and zona == ("caso", rival):
                    out.append(a)
                elif a.objetivo is not None and debajo == a.objetivo:
                    out.append(a)
            elif isinstance(a, A.Guardia) and a.uid == uid:
                if (zona and zona[1] == rival) or debajo is not None and m.p.carta(debajo).dueno != c.dueno:
                    out.append(a)
            elif isinstance(a, A.Asistir) and uid == m.j(a.jugador).companero.uid and zona == ("file", lado):
                out.append(a)
            elif isinstance(a, A.ResolverCaso) and uid == m.j(a.jugador).companero.uid and zona == ("caso", lado):
                out.append(a)
        return out

    def empezar_arrastre(self, origen):
        """Ilumina en dorado los sitios donde se puede soltar."""
        self.zonas_objetivo = set()
        for clave, r in self.zonas.items():
            if self._que_hace(origen, r.center()):
                self.zonas_objetivo.add(clave)
        for uid, it in self.items_carta.items():
            if it is not origen and self._que_hace(origen, it.pos()):
                it.objetivo = True
                it.update()
        self.escena.update()

    def soltar(self, origen, pos: QPointF):
        acciones = self._que_hace(origen, pos)
        self.zonas_objetivo = set()
        for it in self.items_carta.values():
            it.objetivo = False
        if acciones:
            self.v.ejecutar(acciones[0])
        else:
            self.v.refrescar()          # vuelve a su sitio con animación
