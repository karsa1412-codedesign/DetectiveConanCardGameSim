"""Ventana principal: perfiles, menú de modos y tablero (partida local y tutorial)."""
from __future__ import annotations

import configparser
import os
from pathlib import Path

import time

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QPixmap, QTransform
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QFrame, QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QStackedWidget,
                               QToolButton, QVBoxLayout, QWidget, QCheckBox)

from core import acciones as A
from core.cartas import Catalogo, Mazo
from core.estado import ACTIVO, ATURDIDO, DORMIDO
from core.reglas import Motor, ReglaError, nueva_partida
from core.perfiles import GestorPerfiles
from core.tutorial import Guion, GuionError
from core.ia import IA, copiar
from datos.descarga import CatalogoLocal
from . import tema
from .contenido import PaginaContenido
from .fundas import Fundas
from .mesa import Mesa
from .traducciones import PaginaTraducciones
from .intro import Intro
from .actualizaciones import Actualizaciones
from .mazos import PaginaMazos
from .pantallas import PaginaPerfiles
from .menu_principal import PaginaMenu
from .textos import Textos, describir, describir_efecto, linea_hab

RESALTE = "border:3px solid #ff7a00;"

COLORES = {"azul": "#2f5fa8", "rojo": "#b23b3b", "verde": "#2f8a4e", "amarillo": "#c49a1a",
           "blanco": "#8c8c8c", "negro": "#3a3a3a", "morado": "#6d3fa0", "rosa": "#c0507e"}
ANCHO, ALTO = 100, 140
OPS_CARTA = ("a_mano", "a_descarte", "al_fondo_mazo", "a_file", "activar", "dormir", "aturdir",
             "ap+1000", "ap-1000")


def acciones_de_carta(a: A.Accion) -> set:
    """UIDs de las cartas a las que se refiere una acción (para el menú al pulsar una carta)."""
    out = set()
    for campo in ("uid", "atacante", "objetivo", "retirar"):
        v = getattr(a, campo, None)
        if isinstance(v, int):
            out.add(v)
    for v in getattr(a, "uids", ()) or ():
        out.add(v)
    return out


class Config:
    def __init__(self, ruta: Path):
        self.ruta = ruta
        self.cp = configparser.ConfigParser()
        self.cp.read(ruta, encoding="utf-8")
        if "general" not in self.cp:
            self.cp["general"] = {}
        self.g = self.cp["general"]

    def guardar(self):
        with open(self.ruta, "w", encoding="utf-8") as f:
            self.cp.write(f)

    def clave_deepl(self, idioma: str, exacta: bool = False) -> str:
        """Clave del idioma; si no hay y exacta es False, la general."""
        sec = self.cp["deepl"] if "deepl" in self.cp else {}
        propia = sec.get(idioma, "")
        return propia if (propia or exacta) else sec.get("general", "")

    def poner_clave_deepl(self, idioma: str, clave: str):
        if "deepl" not in self.cp:
            self.cp["deepl"] = {}
        if clave:
            self.cp["deepl"][idioma] = clave
        elif idioma in self.cp["deepl"]:
            del self.cp["deepl"][idioma]


class Imagenes:
    """Busca la imagen de cada carta por nombre de archivo dentro de la carpeta elegida.
    mostrar() devuelve la imagen con el texto traducido superpuesto (solo en memoria)."""

    def __init__(self):
        self.indice: dict[str, Path] = {}
        self.cache: dict[str, QPixmap] = {}
        self.cache_trad: dict[tuple, QPixmap] = {}
        self.traducir = True

    def mostrar(self, defn, idioma: str) -> QPixmap | None:
        base = self.de(defn)
        if base is None or base.isNull() or not self.traducir or idioma == "ja":
            return base
        clave = (defn.id, idioma, defn.texto.get(idioma, ""), defn.nombre.get(idioma, ""))
        if clave not in self.cache_trad:
            from .superposicion import componer
            self.cache_trad[clave] = componer(base, defn, idioma) or base
        return self.cache_trad[clave]

    def cargar(self, carpeta: str):
        self.indice.clear()
        self.cache.clear()
        self.cache_trad.clear()
        if carpeta and Path(carpeta).is_dir():
            for p in Path(carpeta).rglob("*"):
                if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    self.indice.setdefault(p.stem.upper(), p)

    def ruta(self, defn):
        return self.indice.get((Path(defn.imagen).stem if defn.imagen else defn.id).upper())

    def de(self, defn) -> QPixmap | None:
        clave = (Path(defn.imagen).stem if defn.imagen else defn.id).upper()
        if clave not in self.indice:
            return None
        if clave not in self.cache:
            self.cache[clave] = QPixmap(str(self.indice[clave]))
        return self.cache[clave]


class CartaWidget(QFrame):
    def __init__(self, ventana: "Ventana", carta=None, oculta=False, extra=""):
        super().__init__()
        self.v, self.carta = ventana, carta
        if carta is not None and not oculta:
            ventana._cartas.append(self)
        tumbada = carta is not None and carta.estado in (DORMIDO, ATURDIDO) and not oculta
        w, h = (ALTO, ANCHO) if tumbada else (ANCHO, ALTO)
        self.setFixedSize(w, h)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(1)
        if oculta or carta is None:
            self.setStyleSheet("QFrame{background:#5a4632;border-radius:6px;border:2px solid #2b2016;}"
                               "QLabel{color:#e8dcc8;}")
            lab = QLabel("DC")
            lab.setAlignment(Qt.AlignCenter)
            lay.addWidget(lab)
            return
        d = carta.defn
        img = ventana.imagenes.mostrar(d, ventana.tx.idioma)
        if img is not None and not img.isNull():
            pix = img.scaled(ANCHO - 8, ALTO - 8, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if tumbada:
                pix = pix.transformed(QTransform().rotate(90 if carta.estado == DORMIDO else 180))
            lab = QLabel()
            lab.setPixmap(pix)
            lab.setAlignment(Qt.AlignCenter)
            lay.addWidget(lab)
        else:
            color = COLORES.get(d.colores[0] if d.colores else "", "#555")
            borde = "#f0c040" if carta.estado == ACTIVO else "#222"
            self.setStyleSheet(f"QFrame{{background:{color};border-radius:6px;border:2px solid {borde};}}"
                               "QLabel{color:white;border:none;background:transparent;}")
            cab = QLabel(f"{d.nivel}" if d.tipo in ("personaje", "evento") else d.tipo[:4].upper())
            cab.setStyleSheet("font-weight:bold;")
            lay.addWidget(cab)
            nom = QLabel(d.nombre_en(ventana.tx.idioma))
            nom.setWordWrap(True)
            nom.setStyleSheet("font-size:10px;font-weight:bold;")
            lay.addWidget(nom, 1)
            if d.tipo == "personaje":
                pie = QLabel(f"AP {carta.ap}  LP {carta.lp}")
                pie.setStyleSheet("font-size:9px;")
                lay.addWidget(pie)
            if carta.estado != ACTIVO:
                est = QLabel(ventana.tx(carta.estado))
                est.setStyleSheet("font-size:9px;color:#ffd0d0;")
                lay.addWidget(est)
        if extra:
            ex = QLabel(extra)
            ex.setStyleSheet("font-size:9px;color:#ffe9a0;")
            lay.addWidget(ex)
        tip = f"{d.nombre_en(ventana.tx.idioma)}\n{d.id} · {', '.join(d.colores)} · nivel {d.nivel}"
        if d.tipo == "personaje":
            tip += f"\nAP {carta.ap} · LP {carta.lp}"
        if d.palabras_clave:
            tip += "\n" + ", ".join(k if v is True else f"{k} {v}" for k, v in d.palabras_clave.items())
        if d.irrupcion_ap:
            tip += f"\nIrrupción AP+{d.irrupcion_ap}"
        if d.disfraz:
            tip += "\nDisfraz"
        if d.texto_en(ventana.tx.idioma):
            tip += "\n" + d.texto_en(ventana.tx.idioma)
        self._tip = tip
        self._img = img if img is not None and not img.isNull() else None
        if self._img is None:
            self.setToolTip(tip)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, ev):
        if self.carta is not None and getattr(self, "_img", None) is not None:
            self.v.vista_previa.mostrar(self._img, self.mapToGlobal(self.rect().topRight()))
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.v.vista_previa.hide()
        super().leaveEvent(ev)

    def resaltar(self):
        self.setObjectName("carta")
        self.setStyleSheet(self.styleSheet() + "QFrame#carta{%s}" % RESALTE)

    def mouseDoubleClickEvent(self, ev):
        if self.carta is not None:
            self.v.ver_en_grande(self.carta.defn)

    def mousePressEvent(self, ev):
        self.v.vista_previa.hide()
        if self.carta is not None:
            self.v.menu_carta(self.carta, self.mapToGlobal(ev.position().toPoint()))


class VistaPrevia(QLabel):
    """Carta en grande junto al cursor al pasar el ratón."""

    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setStyleSheet("background:#0d1119;border:2px solid #d9a845;border-radius:8px;padding:4px;")

    def mostrar(self, pix: QPixmap, pos):
        ancho = 420 if pix.width() > pix.height() else 330
        self.setPixmap(pix.scaledToWidth(ancho, Qt.SmoothTransformation))
        self.adjustSize()
        pantalla = QApplication.primaryScreen().availableGeometry()
        x, y = pos.x() + 8, pos.y()
        if x + self.width() > pantalla.right():
            x = pos.x() - self.width() - 120
        y = max(pantalla.top(), min(y, pantalla.bottom() - self.height()))
        self.move(x, y)
        self.show()


class DialogoCarta(QDialog):
    """Carta a tamaño grande (doble clic o «Ver en grande»)."""

    def __init__(self, ventana, defn):
        super().__init__(ventana)
        self.setWindowTitle(defn.nombre_en(ventana.tx.idioma))
        l = QVBoxLayout(self)
        img = ventana.imagenes.mostrar(defn, ventana.tx.idioma)
        lab = QLabel()
        if img is not None and not img.isNull():
            alto = min(760, QApplication.primaryScreen().availableGeometry().height() - 120)
            lab.setPixmap(img.scaledToHeight(alto if img.height() >= img.width() else int(alto * 0.72),
                                             Qt.SmoothTransformation))
        else:
            lab.setText(defn.texto_en(ventana.tx.idioma) or defn.nombre_en(ventana.tx.idioma))
            lab.setWordWrap(True)
        l.addWidget(lab)
        # qué habilidades aplica la app sola y cuáles hay que aplicar a mano
        from core import habilidades as H
        filas = []
        for h in H.habilidades(defn):
            if h.clase in (H.NUCLEO, H.DISFRAZ):
                continue
            estado = ventana.tx("hab_auto") if h.automatica else ventana.tx("hab_manual")
            color = "#2ecc71" if h.automatica else "#e0a020"
            filas.append(f"<span style='color:{color}'>●</span> {linea_hab(defn, h.indice, ventana.tx.idioma)}"
                         f" <i style='color:#999'>({estado})</i>")
        if filas:
            info = QLabel("<br>".join(filas))
            info.setWordWrap(True)
            info.setMaximumWidth(560)
            l.addWidget(info)


class DialogoFundas(QDialog):
    """Elegir la funda del perfil. Las imágenes que se pongan en fundas/ aparecen aquí."""

    def __init__(self, ventana):
        super().__init__(ventana)
        from PySide6.QtWidgets import QListWidget, QListWidgetItem
        from PySide6.QtGui import QIcon, QDesktopServices
        from PySide6.QtCore import QUrl
        self.v = ventana
        tx = ventana.tx
        self.setWindowTitle(tx("fundas_titulo"))
        self.resize(760, 560)
        l = QVBoxLayout(self)
        ayuda = QLabel(tx("fundas_ayuda"))
        ayuda.setWordWrap(True)
        ayuda.setStyleSheet("color:#a9b1c2;")
        l.addWidget(ayuda)
        self.lista = QListWidget()
        self.lista.setViewMode(QListWidget.IconMode)
        self.lista.setIconSize(QSize(120, 168))
        self.lista.setGridSize(QSize(150, 214))
        self.lista.setMovement(QListWidget.Static)
        self.lista.setResizeMode(QListWidget.Adjust)
        actual = ventana.funda_perfil()
        ventana.fundas.recargar()
        for nombre in ventana.fundas.disponibles():
            etiqueta = nombre if ventana.fundas.es_propia(nombre) else f"{nombre}\n({tx('fundas_tuya')})"
            it = QListWidgetItem(QIcon(ventana.fundas.pixmap(nombre)), etiqueta)
            it.setData(Qt.UserRole, nombre)
            self.lista.addItem(it)
            if nombre == actual:
                self.lista.setCurrentItem(it)
        self.lista.itemDoubleClicked.connect(lambda _: self._ok())
        l.addWidget(self.lista, 1)
        fila = QHBoxLayout()
        abrir = QPushButton(tx("fundas_abrir"))

        def abrir_carpeta():
            ventana.fundas.carpeta.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(ventana.fundas.carpeta)))
        abrir.clicked.connect(abrir_carpeta)
        fila.addWidget(abrir)
        fila.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        fila.addWidget(bb)
        l.addLayout(fila)

    def _ok(self):
        it = self.lista.currentItem()
        if it:
            self.v.perfiles.actualizar(self.v.perfil, funda=it.data(Qt.UserRole))
        self.accept()


class DialogoMazos(QDialog):
    """Elegir el mazo de cada jugador (solo mazos válidos) y, si el mazo trae varios, el Compañero."""

    def __init__(self, ventana: "Ventana", ia: bool = False):
        super().__init__(ventana)
        self.v = ventana
        self.ia = ia
        tx = ventana.tx
        self.setWindowTitle(tx("elige_mazos"))
        self.validos = [(r, m) for r, m, err in ventana.mazos_disponibles() if not err]
        self.hay_mazos = bool(self.validos)
        form = QFormLayout(self)
        self.combos, self.comps, self.fundas_cb = [], [], []
        reales = [i for i, (r, m) in enumerate(self.validos) if not m.companero.startswith("DEMO-")]
        for n in (1, 2):
            cb = QComboBox()
            for r, m in self.validos:
                cb.addItem(m.nombre, len(self.combos))
            preferidos = reales or list(range(len(self.validos)))
            if preferidos:
                cb.setCurrentIndex(preferidos[min(n - 1, len(preferidos) - 1)])
            comp = QComboBox()
            cb.currentIndexChanged.connect(lambda _=0, c=cb, k=comp: self._comps(c, k))
            funda = QComboBox()
            for nombre in ventana.fundas.disponibles():
                funda.addItem(ventana.fundas.pixmap(nombre).scaledToHeight(36, Qt.SmoothTransformation), nombre, nombre)
            preferida = ventana.funda_perfil() if n == 1 else ("Granate" if ventana.funda_perfil() != "Granate" else "Noche")
            funda.setCurrentIndex(max(0, funda.findData(preferida)))
            funda.setIconSize(QSize(26, 36))
            form.addRow(tx("mazo_jugador", n=n) if not ia else tx("ia_tu_mazo" if n == 1 else "ia_su_mazo"), cb)
            form.addRow(tx("elegir_companero"), comp)
            form.addRow(tx("funda"), funda)
            self.combos.append(cb)
            self.comps.append(comp)
            self.fundas_cb.append(funda)
            self._comps(cb, comp)
        if ia:
            g = ventana.cfg.g
            self.nivel = QComboBox()
            for k in ("facil", "normal", "dificil"):
                self.nivel.addItem(tx("ia_nivel_" + k), k)
            self.nivel.setCurrentIndex(max(0, self.nivel.findData(g.get("ia_nivel", "normal"))))
            self.estilo = QComboBox()
            for k in ("equilibrado", "agresivo", "prudente"):
                self.estilo.addItem(tx("ia_estilo_" + k), k)
            self.estilo.setCurrentIndex(max(0, self.estilo.findData(g.get("ia_estilo", "equilibrado"))))
            self.primero = QComboBox()
            for k in ("azar", "yo", "ia"):
                self.primero.addItem(tx("ia_empieza_" + k), k)
            self.primero.setCurrentIndex(max(0, self.primero.findData(g.get("ia_primero", "azar"))))
            form.addRow(tx("ia_nivel"), self.nivel)
            form.addRow(tx("ia_estilo"), self.estilo)
            form.addRow(tx("ia_empieza"), self.primero)
            ayuda = QLabel(tx("ia_ayuda"))
            ayuda.setWordWrap(True)
            ayuda.setStyleSheet("color:#a9b1c2;font-size:11px;")
            form.addRow(ayuda)
            for n, cb in enumerate(self.combos):
                guardado = g.get(f"ia_mazo{n}")
                i = cb.findText(guardado) if guardado else -1
                if i >= 0:
                    cb.setCurrentIndex(i)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def opciones_ia(self) -> dict:
        op = {"nivel": self.nivel.currentData(), "estilo": self.estilo.currentData(),
              "primero": self.primero.currentData()}
        for k, v in op.items():
            self.v.cfg.g["ia_" + k] = v
        for n, cb in enumerate(self.combos):
            self.v.cfg.g[f"ia_mazo{n}"] = cb.currentText()
        self.v.cfg.guardar()
        return op

    def _comps(self, cb, comp):
        comp.clear()
        if cb.currentIndex() < 0:
            return
        m = self.validos[cb.currentIndex()][1]
        for cid in [m.companero, *m.companeros_alternativos]:
            d = self.v.catalogo.por_id.get(cid)
            comp.addItem(d.nombre_en(self.v.tx.idioma) if d else cid, cid)
        comp.setEnabled(comp.count() > 1)

    def fundas_elegidas(self) -> list:
        return [cb.currentData() for cb in self.fundas_cb]

    def mazos(self):
        out = []
        for cb, comp in zip(self.combos, self.comps):
            m = self.validos[cb.currentIndex()][1]
            m = Mazo(m.nombre, comp.currentData() or m.companero, m.caso, dict(m.cartas))
            out.append(m)
        return out


class DialogoElegir(QDialog):
    """Elegir cartas que no están a la vista en la mesa (mazo, zona de retiradas, Pruebas...)."""

    def __init__(self, ventana, cartas, validas: set, minimo: int, maximo: int, elegidas: list, texto: str):
        super().__init__(ventana)
        self.v = ventana
        self.setWindowTitle(ventana.tx("elegir_titulo"))
        self.minimo, self.maximo = minimo, maximo
        lay = QVBoxLayout(self)
        lbl = QLabel(texto)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        rejilla = QWidget()
        fila = QHBoxLayout(rejilla)
        self.botones = {}
        for c in cartas:
            b = QToolButton()
            b.setCheckable(True)
            b.setEnabled(c.uid in validas)
            b.setChecked(c.uid in elegidas)
            pix = ventana.mesa._frente(c.defn)
            b.setIcon(pix)
            b.setIconSize(QSize(150, 210))
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setText(c.defn.nombre_en(ventana.tx.idioma))
            b.setStyleSheet("QToolButton:checked{border:4px solid #2ecc71;border-radius:8px;}"
                            "QToolButton:disabled{color:#666;}")
            b.toggled.connect(self._cambio)
            fila.addWidget(b)
            self.botones[c.uid] = b
        sc = QScrollArea()
        sc.setWidget(rejilla)
        sc.setWidgetResizable(True)
        sc.setMinimumSize(720, 300)
        lay.addWidget(sc)
        self.lbl = QLabel()
        lay.addWidget(self.lbl)
        self.caja = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.caja.accepted.connect(self.accept)
        self.caja.rejected.connect(self.reject)
        lay.addWidget(self.caja)
        self._cambio()

    def elegidas(self) -> list:
        return [u for u, b in self.botones.items() if b.isChecked()]

    def _cambio(self, *_):
        n = len(self.elegidas())
        self.lbl.setText(self.v.tx("ef_elegidas", n=f"{n} / {self.maximo}"))
        self.caja.button(QDialogButtonBox.Ok).setEnabled(self.minimo <= n <= self.maximo)


class Pensador(QThread):
    """La IA piensa en segundo plano, sobre una copia de la partida, sin bloquear la ventana."""
    listo = Signal(object, int)

    def __init__(self, ia: IA, motor: Motor, gen: int):
        super().__init__()
        self.ia, self.motor, self.gen = ia, motor, gen

    def run(self):
        try:
            accion = self.ia.pensar(self.motor).accion
        except Exception:      # no debería pasar: si falla, juega con reglas sencillas
            from core.ia import por_reglas
            accion = por_reglas(self.motor, self.ia.yo, self.ia.rng)
        self.listo.emit(accion, self.gen)


class PilaConFondo(QStackedWidget):
    """Contenedor de las pantallas con la pared de ladrillo azulada de fondo."""

    def __init__(self, imagen: Path):
        super().__init__()
        self.fondo = QPixmap(str(imagen)) if imagen.exists() else None
        self._escalado = None

    def paintEvent(self, ev):
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        if self.fondo is None or self.fondo.isNull():
            p.fillRect(self.rect(), QColor("#151b27"))
            return
        if self._escalado is None or self._escalado.size() != self.size():
            esc = self.fondo.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x, y = (esc.width() - self.width()) // 2, (esc.height() - self.height()) // 2
            self._escalado = esc.copy(x, y, self.width(), self.height())
        p.drawPixmap(0, 0, self._escalado)


class Ventana(QMainWindow):
    def __init__(self, base: Path):
        super().__init__()
        from core.rutas import Rutas
        self.rutas = base if isinstance(base, Rutas) else Rutas(Path(base), Path(base))
        self.rutas.preparar()
        self.base = self.rutas.programa
        usuario = self.rutas.usuario
        self.cfg = Config(usuario / "config.ini")
        self.tx = Textos(self.base / "idiomas", self.cfg.g.get("idioma", "es"))
        self.perfiles = GestorPerfiles(usuario / "perfiles")
        self.perfil: str | None = None
        self.imagenes = Imagenes()
        self.imagenes.traducir = self.cfg.g.get("cartas_traducidas", "si") == "si"
        self.imagenes.cargar(self.carpeta_imagenes())
        self.vista_previa = VistaPrevia()
        self.fundas = Fundas(usuario / "fundas")
        self.catalogo_local = CatalogoLocal(usuario / "datos" / "cartas.json")
        self.catalogo = None
        self.recargar_catalogo()
        self.motor: Motor | None = None
        self.eleccion: list = []          # cartas marcadas para el efecto en curso
        self.eleccion_de = None
        self.eleccion_abierta = False
        self.guion: Guion | None = None
        self.modo = None            # "local" | "tutorial" | "ia"
        self.ia: IA | None = None
        self.ia_gen = 0             # cambia al empezar o dejar una partida: descarta lo que pensaba
        self.pensador: Pensador | None = None
        self._hilos: set = set()
        self.ia_ultima = ""
        self.fin_registrado = False
        self.ultimo_decisor = None
        self._zonas: dict[str, list] = {}
        self._cartas: list = []
        self.resize(1400, 880)
        self.pila = PilaConFondo(self.base / "recursos" / "fondo.jpg")
        self.setCentralWidget(self.pila)
        self.pag_perfiles = PaginaPerfiles(self)
        self.pag_perfiles.elegido.connect(self.entrar_perfil)
        self.pag_menu = PaginaMenu(self)
        self.pag_contenido = PaginaContenido(self)
        self.pag_mazos = PaginaMazos(self)
        self.pag_traducciones = PaginaTraducciones(self)
        self.tablero = QWidget()
        self.tapa = QWidget()
        for w in (self.pag_perfiles, self.pag_menu, self.pag_contenido, self.pag_mazos, self.pag_traducciones,
                  self.tablero, self.tapa):
            w.setObjectName("pagina")
            self.pila.addWidget(w)
        self._montar_tapa()
        self._montar_tablero()
        self.act = Actualizaciones(self)
        self._menus()
        self.ir_a_perfiles()
        from PySide6.QtCore import QTimer
        self.intro = None
        if self.cfg.g.get("intro", "si") == "si" and not os.environ.get("SIMULADOR_SIN_INTRO"):
            intro = Intro(self, self.base / "recursos" / "intro")
            if intro.valida:
                self.intro = intro
                intro.terminada.connect(self._tras_intro)
        if self.intro is None:
            QTimer.singleShot(0, self._tras_intro)

    def showEvent(self, ev):
        super().showEvent(ev)
        if self.intro is not None and not self.intro.iniciada:
            QTimer.singleShot(0, self.intro.empezar)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self.intro is not None and self.intro.isVisible():
            self.intro.setGeometry(self.rect())

    def _tras_intro(self):
        self.intro = None
        self.act.ofrecer_importar_si_nuevo()
        self.act.al_arrancar()

    def _toggle_intro(self, valor: bool):
        self.cfg.g["intro"] = "si" if valor else "no"
        self.cfg.guardar()

    # ---------------------------------------------------------------- navegación y perfiles

    def ir_a_perfiles(self):
        self.pag_perfiles.refrescar()
        self.pila.setCurrentWidget(self.pag_perfiles)
        self._menus()

    def ir_a_menu(self):
        self.motor = self.guion = self.modo = None
        self.ia_gen += 1
        self.mesa.vaciar()
        self.registro.clear()
        self.pag_menu.refrescar()
        self.pila.setCurrentWidget(self.pag_menu)
        self._menus()

    def ver_en_grande(self, defn):
        self.vista_previa.hide()
        DialogoCarta(self, defn).exec()

    def _toggle_traducidas(self, valor: bool):
        self.cfg.g["cartas_traducidas"] = "si" if valor else "no"
        self.cfg.guardar()
        self.imagenes.traducir = valor
        self.imagenes.cache_trad.clear()
        if hasattr(self, "pag_mazos"):
            self.pag_mazos._iconos.clear()
        actual = self.pila.currentWidget()
        if actual is self.pag_mazos:
            self.pag_mazos.refrescar()
        elif self.motor is not None:
            self.refrescar()

    def elegir_fundas(self):
        DialogoFundas(self).exec()
        self.pag_menu.refrescar()

    def funda_perfil(self) -> str:
        if self.perfil and self.perfil in self.perfiles.perfiles:
            return self.perfiles.perfiles[self.perfil].get("funda", "Noche")
        return "Noche"

    def traductor(self, idioma: str, cliente):
        from datos.traduccion import Traductor
        return Traductor(self.rutas.datos_usuario, idioma, cliente, self.rutas.datos_programa)

    def carpeta_imagenes(self) -> str:
        return self.cfg.g.get("carpeta_imagenes", "") or str(self.rutas.usuario / "imagenes")

    def recargar_catalogo(self):
        self.catalogo_local = CatalogoLocal(self.rutas.datos_usuario / "cartas.json")
        self.catalogo = Catalogo.cargar(self.base / "datos" / "cartas_demo.json", self.rutas.datos_usuario / "cartas.json")
        self.imagenes.cargar(self.carpeta_imagenes())
        if hasattr(self, "fundas"):
            self.fundas.recargar()
        if hasattr(self, "pag_mazos"):
            self.pag_mazos._iconos.clear()

    def mazos_disponibles(self) -> list:
        """[(ruta, Mazo, errores)] de los mazos oficiales y los del usuario."""
        import json as _json
        out = []
        for carpeta in (self.base / "datos" / "mazos", self.rutas.usuario / "mazos"):
            for ruta in sorted(carpeta.glob("*.json")) if carpeta.exists() else []:
                try:
                    m = Mazo.cargar(ruta)
                except Exception as e:
                    continue
                errores = m.validar(self.catalogo)
                paquete = _json.loads(ruta.read_text(encoding="utf-8")).get("paquete")
                if errores and paquete and any("desconocida" in e or "no existe" in e for e in errores):
                    errores = [self.tx("local_falta_coleccion", p=paquete)]
                out.append((ruta, m, errores))
        return out

    def ir_a_contenido(self):
        self.pag_contenido.refrescar()
        self.pila.setCurrentWidget(self.pag_contenido)
        self._menus()

    def ir_a_traducciones(self):
        self.pag_traducciones.refrescar()
        self.pila.setCurrentWidget(self.pag_traducciones)
        self._menus()

    def ir_a_mazos(self):
        self.pag_mazos.refrescar()
        self.pila.setCurrentWidget(self.pag_mazos)
        self._menus()

    def entrar_perfil(self, nombre: str):
        self.perfil = nombre
        self.perfiles.entrar(nombre)
        self.ir_a_menu()
        if self.perfiles.es_nuevo(nombre):
            self.perfiles.actualizar(nombre, tutorial_recomendado=True)
            self.perfiles.registrar(nombre, "tutorial_recomendado")
            caja = QMessageBox(self)
            caja.setWindowTitle(self.tx("recomendar_titulo", nombre=nombre))
            caja.setText(self.tx("recomendar_texto"))
            si = caja.addButton(self.tx("recomendar_si"), QMessageBox.AcceptRole)
            caja.addButton(self.tx("recomendar_no"), QMessageBox.RejectRole)
            caja.exec()
            if caja.clickedButton() is si:
                self.iniciar_tutorial()
            else:
                self.perfiles.registrar(nombre, "tutorial_saltado")

    def cambiar_perfil(self):
        if self.perfil:
            self.perfiles.registrar(self.perfil, "cierre_sesion")
        self.perfil = None
        self.ir_a_perfiles()

    def volver_al_menu(self):
        if self.modo and self.motor and self.motor.p.ganador is None:
            if QMessageBox.question(self, self.tx("titulo"), self.tx("abandonar_confirmar")) != QMessageBox.Yes:
                return
            evento = "tutorial_abandonado" if self.modo == "tutorial" else "partida_abandonada"
            detalle = f"paso {self.guion.indice + 1}" if self.modo == "tutorial" else f"turno {self.motor.p.turno}"
            self.perfiles.registrar(self.perfil, evento, detalle)
        self.ir_a_menu()

    def closeEvent(self, ev):
        self.ia_gen += 1
        for h in list(self._hilos):
            h.wait(10000)
        if self.perfil:
            if self.modo and self.motor and self.motor.p.ganador is None:
                self.perfiles.registrar(self.perfil, "tutorial_abandonado" if self.modo == "tutorial"
                                        else "partida_abandonada", "al cerrar")
            self.perfiles.registrar(self.perfil, "cierre_sesion")
        super().closeEvent(ev)

    # ---------------------------------------------------------------- menús

    def _menus(self):
        self.menuBar().clear()
        tx = self.tx
        self.setWindowTitle(tx("titulo"))
        m = self.menuBar().addMenu(tx("menu_partida"))
        en_tablero = self.pila.currentWidget() in (self.tablero, self.tapa)
        if en_tablero:
            m.addAction(tx("volver_menu"), self.volver_al_menu)
            if self.modo in ("local", "ia"):
                m.addAction(tx("rendirse"), self.rendirse)
        m.addAction(tx("carpeta_imagenes"), self.elegir_imagenes)
        self.chk_ocultar = QAction(tx("ocultar_manos"), self, checkable=True)
        self.chk_ocultar.setChecked(self.cfg.g.get("ocultar_manos", "si") == "si")
        self.chk_ocultar.toggled.connect(self._toggle_ocultar)
        m.addAction(self.chk_ocultar)
        self.chk_traducidas = QAction(tx("cartas_traducidas"), self, checkable=True)
        self.chk_traducidas.setChecked(self.imagenes.traducir)
        self.chk_traducidas.toggled.connect(self._toggle_traducidas)
        m.addAction(self.chk_traducidas)
        chk_intro = QAction(tx("ver_intro"), self, checkable=True)
        chk_intro.setChecked(self.cfg.g.get("intro", "si") == "si")
        chk_intro.toggled.connect(self._toggle_intro)
        m.addAction(chk_intro)
        m.addSeparator()
        m.addAction(tx("salir"), self.close)
        if hasattr(self, "act"):
            ma = self.menuBar().addMenu(tx("menu_ayuda"))
            ma.addAction(tx("act_buscar"), lambda: self.act.buscar(silencioso=False))
            ma.addAction(tx("imp_menu"), self.act.importar)
            ma.addSeparator()
            ma.addAction(tx("acerca"), self.act.acerca_de)
        mi = self.menuBar().addMenu(tx("idioma"))
        for idi in self.tx.idiomas():
            mi.addAction(idi.upper(), lambda i=idi: self.cambiar_idioma(i))

    # ---------------------------------------------------------------- montaje del tablero

    def _montar_tapa(self):
        lay = QVBoxLayout(self.tapa)
        self.lbl_tapa = QLabel()
        self.lbl_tapa.setAlignment(Qt.AlignCenter)
        self.lbl_tapa.setStyleSheet("font-size:28px;font-weight:bold;")
        self.btn_tapa = QPushButton()
        self.btn_tapa.setFixedWidth(220)
        self.btn_tapa.clicked.connect(lambda: self.pila.setCurrentWidget(self.tablero))
        lay.addStretch()
        lay.addWidget(self.lbl_tapa)
        lay.addWidget(self.btn_tapa, alignment=Qt.AlignCenter)
        lay.addStretch()

    def _montar_tablero(self):
        raiz = QHBoxLayout(self.tablero)
        split = QSplitter()
        raiz.addWidget(split)
        izq = QWidget()
        li = QVBoxLayout(izq)
        li.setContentsMargins(0, 0, 0, 0)
        self.lbl_estado = QLabel()
        self.lbl_estado.setStyleSheet("font-size:15px;font-weight:bold;padding:4px;")
        li.addWidget(self.lbl_estado)
        self.mesa = Mesa(self)
        li.addWidget(self.mesa, 1)
        self.lbl_aviso = QLabel()
        self.lbl_aviso.setStyleSheet("color:#888;font-size:10px;")
        li.addWidget(self.lbl_aviso)
        split.addWidget(izq)
        der = QWidget()
        ld = QVBoxLayout(der)
        # panel del tutorial
        self.panel_tut = QFrame()
        self.panel_tut.setStyleSheet("QFrame#tut{background:#fff6e0;border:2px solid #e0a020;border-radius:10px;}"
                                     "QLabel{color:#2b2418;}")
        self.panel_tut.setObjectName("tut")
        lt = QVBoxLayout(self.panel_tut)
        cab = QHBoxLayout()
        self.lbl_narrador = QLabel()
        self.lbl_narrador.setStyleSheet("font-size:15px;font-weight:bold;")
        self.lbl_progreso = QLabel()
        self.lbl_progreso.setStyleSheet("color:#7a6a4a;")
        cab.addWidget(self.lbl_narrador)
        cab.addStretch()
        cab.addWidget(self.lbl_progreso)
        lt.addLayout(cab)
        self.lbl_tut = QLabel()
        self.lbl_tut.setWordWrap(True)
        self.lbl_tut.setStyleSheet("font-size:14px;")
        self.lbl_tut.setMinimumHeight(110)
        self.lbl_tut.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lt.addWidget(self.lbl_tut)
        self.lbl_tut_pista = QLabel()
        self.lbl_tut_pista.setStyleSheet("color:#b05a00;font-style:italic;")
        lt.addWidget(self.lbl_tut_pista)
        bt = QHBoxLayout()
        self.btn_tut_salir = QPushButton()
        self.btn_tut_salir.clicked.connect(self.volver_al_menu)
        self.btn_tut_seguir = QPushButton()
        self.btn_tut_seguir.setStyleSheet("font-weight:bold;padding:6px 16px;")
        self.btn_tut_seguir.clicked.connect(self.tutorial_continuar)
        bt.addWidget(self.btn_tut_salir)
        bt.addStretch()
        bt.addWidget(self.btn_tut_seguir)
        lt.addLayout(bt)
        ld.addWidget(self.panel_tut)
        self.lbl_acciones = QLabel()
        self.lbl_acciones.setStyleSheet("font-weight:bold;")
        ld.addWidget(self.lbl_acciones)
        self.zona_botones = QVBoxLayout()
        cont = QWidget()
        cont.setLayout(self.zona_botones)
        self.sc_acciones = QScrollArea()
        self.sc_acciones.setWidgetResizable(True)
        self.sc_acciones.setWidget(cont)
        ld.addWidget(self.sc_acciones, 2)
        self.lbl_registro = QLabel()
        self.lbl_registro.setStyleSheet("font-weight:bold;")
        ld.addWidget(self.lbl_registro)
        self.registro = QPlainTextEdit(readOnly=True)
        ld.addWidget(self.registro, 2)
        der.setMinimumWidth(380)
        der.setMaximumWidth(440)
        split.addWidget(der)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)

    # ---------------------------------------------------------------- modos de juego

    def iniciar_local(self):
        dlg = DialogoMazos(self)
        if not dlg.hay_mazos:
            QMessageBox.information(self, self.tx("titulo"), self.tx("local_sin_mazos"))
            return
        if dlg.exec() != QDialog.Accepted:
            return
        m0, m1 = dlg.mazos()
        self.mesa.fundas = dict(enumerate(dlg.fundas_elegidas()))
        try:
            self.motor = nueva_partida(self.catalogo, m0, m1)
        except ReglaError as e:
            QMessageBox.warning(self, self.tx("titulo"), str(e))
            return
        self.mesa.vaciar()
        self.modo, self.guion = "local", None
        self.fin_registrado = False
        self.ultimo_decisor = None
        self.perfiles.registrar(self.perfil, "partida_inicio", f"{m0.nombre} contra {m1.nombre}")
        self.perfiles.sumar(self.perfil, "partidas_iniciadas")
        self.perfiles.uso_mazo(self.perfil, m0.nombre, m0.companero)
        self.mazo_en_juego = m0.nombre
        self.pila.setCurrentWidget(self.tablero)
        self._menus()
        self.refrescar()

    def iniciar_ia(self):
        dlg = DialogoMazos(self, ia=True)
        if not dlg.hay_mazos:
            QMessageBox.information(self, self.tx("titulo"), self.tx("local_sin_mazos"))
            return
        if dlg.exec() != QDialog.Accepted:
            return
        m0, m1 = dlg.mazos()
        op = dlg.opciones_ia()
        primero = {"yo": 0, "ia": 1}.get(op["primero"])
        self.mesa.fundas = dict(enumerate(dlg.fundas_elegidas()))
        try:
            self.motor = nueva_partida(self.catalogo, m0, m1, primero=primero)
        except ReglaError as e:
            QMessageBox.warning(self, self.tx("titulo"), str(e))
            return
        self.ia_gen += 1
        self.ia = IA(1, op["nivel"], op["estilo"], tiempo=1.5)
        self.ia_ultima = ""
        self.mesa.vaciar()
        self.modo, self.guion = "ia", None
        self.fin_registrado = False
        self.ultimo_decisor = None
        self.perfiles.registrar(self.perfil, "partida_ia_inicio",
                                f"{m0.nombre} contra {m1.nombre} (IA {op['nivel']}, {op['estilo']})")
        self.perfiles.sumar(self.perfil, "partidas_iniciadas")
        self.perfiles.uso_mazo(self.perfil, m0.nombre, m0.companero)
        self.mazo_en_juego = m0.nombre
        self.pila.setCurrentWidget(self.tablero)
        self._menus()
        self.refrescar()

    def _turno_ia(self):
        """Si le toca a la IA, la pone a pensar (una sola vez por decisión)."""
        m = self.motor
        if self.modo != "ia" or m is None or self.ia is None or not self.ia.le_toca(m):
            return
        self.ia_inicio = time.monotonic()
        if self.pensador is not None and self.pensador.gen == self.ia_gen:
            return    # ya está pensando esta decisión (o acaba de terminar y la jugará en breve)
        hilo = Pensador(self.ia, copiar(m), self.ia_gen)
        hilo.listo.connect(self._ia_decidio)
        hilo.finished.connect(lambda h=hilo: self._hilos.discard(h))
        self._hilos.add(hilo)      # referencia viva hasta que termine (si no, Qt lo destruiría)
        self.pensador = hilo
        hilo.start()

    def _ia_decidio(self, accion, gen):
        if gen != self.ia_gen or self.modo != "ia" or self.motor is None:
            self.pensador = None
            return
        # pausa mínima para que se vea lo que hace, como si fuera una persona
        espera = max(0, 0.75 - (time.monotonic() - self.ia_inicio))
        QTimer.singleShot(int(espera * 1000), lambda: self._ia_jugar(accion, gen))

    def _ia_jugar(self, accion, gen):
        if gen != self.ia_gen or self.modo != "ia" or self.motor is None or not self.ia.le_toca(self.motor):
            self.pensador = None
            return
        texto = describir(self.tx, self.motor, accion)
        try:
            self.motor.aplicar(accion)
        except ReglaError:
            from core.ia import por_reglas
            accion = por_reglas(self.motor, 1, self.ia.rng)
            texto = describir(self.tx, self.motor, accion)
            self.motor.aplicar(accion)
        self.ia_ultima = texto
        self.pensador = None
        self.refrescar()

    def iniciar_tutorial(self):
        try:
            from core.tutorial import disponible
            real = self.base / "datos" / "tutorial" / "tutorial_real.json"
            if real.exists() and disponible(real, self.base / "datos", self.catalogo):
                # con CT-D10 y CT-D11 descargados, el tutorial usa las cartas reales
                self.guion = Guion(real, self.base / "datos", self.catalogo)
            else:
                self.guion = Guion(self.base / "datos" / "tutorial" / "tutorial.json", self.base / "datos")
        except Exception as e:  # datos del tutorial dañados o ausentes
            QMessageBox.warning(self, self.tx("titulo"), str(e))
            return
        self.mesa.vaciar()
        self.registro.clear()
        self.ultimo_decisor = None
        self.motor = self.guion.motor
        self.modo = "tutorial"
        propia = self.funda_perfil()
        self.mesa.fundas = {0: propia, 1: "Granate" if propia != "Granate" else "Noche"}
        self.fin_registrado = False
        self.perfiles.registrar(self.perfil, "tutorial_inicio")
        self.pila.setCurrentWidget(self.tablero)
        self._menus()
        self.refrescar()

    def tutorial_continuar(self):
        g = self.guion
        ultimo = g.indice == len(g.pasos) - 1
        try:
            g.continuar()
        except GuionError as e:
            QMessageBox.warning(self, self.tx("titulo"), str(e))
            return
        if ultimo or g.terminado:
            self.perfiles.registrar(self.perfil, "tutorial_completado")
            self.perfiles.actualizar(self.perfil, tutorial_completado=True)
            self.perfiles.sumar(self.perfil, "tutoriales_completados")
            self.ir_a_menu()
            return
        self.refrescar()

    def ejecutar(self, accion: A.Accion):
        if self.modo == "tutorial":
            if not self.guion.es_esperada(accion):
                QMessageBox.information(self, self.tx("titulo"),
                                        self.tx("tut_no_toca", narrador=self.guion.narrador))
                return
            self.guion.jugar_usuario(accion)
        else:
            try:
                self.motor.aplicar(accion)
            except ReglaError as e:
                QMessageBox.information(self, self.tx("titulo"), str(e))
        self.refrescar()

    # ---------------------------------------------------------------- dibujo

    def refrescar(self):
        m, tx = self.motor, self.tx
        if m is None:
            return
        p = m.p
        tut = self.modo == "tutorial"
        decide = p.quien_decide()
        ia = self.modo == "ia"
        ocultar = self.chk_ocultar.isChecked() and not tut and not ia
        if ocultar and p.ganador is None and self.ultimo_decisor is not None and decide != self.ultimo_decisor:
            self.lbl_tapa.setText(tx("pasar_dispositivo", n=decide + 1))
            self.btn_tapa.setText(tx("listo"))
            self.pila.setCurrentWidget(self.tapa)
        self.ultimo_decisor = decide
        if self.modo in ("local", "ia") and p.ganador is not None and not self.fin_registrado:
            self.fin_registrado = True
            if ia:
                self.perfiles.registrar(self.perfil, "partida_ia_fin",
                                        f"{'gana' if p.ganador == 0 else 'pierde'} contra la IA "
                                        f"({self.ia.nivel}) en el turno {p.turno} · {p.motivo}")
                self.perfiles.sumar(self.perfil, "ia_victorias" if p.ganador == 0 else "ia_derrotas")
                self.perfiles.resultado_mazo(self.perfil, getattr(self, "mazo_en_juego", ""), p.ganador == 0)
            else:
                self.perfiles.registrar(self.perfil, "partida_fin",
                                        f"gana el jugador {p.ganador + 1} en el turno {p.turno} · {p.motivo}")
            self.perfiles.sumar(self.perfil, "partidas_terminadas")
        ver = {}
        for idx in (0, 1):
            if tut or ia:
                ver[idx] = idx == 0 or p.ganador is not None
            else:
                ver[idx] = (not ocultar) or idx == decide or p.ganador is not None
        self.mesa.actualizar(m, ver)
        self.mesa.actualizar_arrastrables()
        if p.ganador is not None and ia:
            self.lbl_estado.setText(tx("ia_ganas" if p.ganador == 0 else "ia_gana", motivo=p.motivo))
        elif ia and p.turno > 0:
            quien = tx("ia_turno_tuyo" if p.activo == 0 else "ia_turno_suyo", t=p.turno)
            self.lbl_estado.setText(quien + ("   ·   " + tx("ia_piensa") if decide == 1 else ""))
        elif p.ganador is not None:
            self.lbl_estado.setText(tx("ganador", n=p.ganador + 1, motivo=p.motivo))
        elif p.turno == 0:
            self.lbl_estado.setText(tx("decide", n=decide + 1))
        else:
            self.lbl_estado.setText(tx("turno", t=p.turno, n=p.activo + 1) + "   ·   " + tx("decide", n=decide + 1))
        self.lbl_aviso.setText(tx("aviso"))
        self.lbl_acciones.setText(tx("acciones"))
        self.lbl_registro.setText(tx("registro"))
        self._dibujar_acciones()
        self._dibujar_tutorial()
        self._dibujar_eleccion()
        self.registro.setPlainText("\n".join(p.log))
        self.registro.verticalScrollBar().setValue(self.registro.verticalScrollBar().maximum())
        self._turno_ia()

    def _dibujar_acciones(self):
        m, tx = self.motor, self.tx
        while self.zona_botones.count():
            w = self.zona_botones.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        tut = self.modo == "tutorial"
        esperadas = self.guion.esperadas() if tut else None
        legales = m.legales()
        ia = self.modo == "ia"
        if (tut or ia) and m.p.quien_decide() != 0:
            legales = []   # las decisiones del rival las aplica el guion o la IA
        if ia and m.p.ganador is None:
            caja = QLabel((tx("ia_ultima", accion=self.ia_ultima) + "\n") if self.ia_ultima else "")
            caja.setWordWrap(True)
            caja.setStyleSheet("color:#ffcf6e;font-size:12px;")
            if m.p.quien_decide() == 1:
                caja.setText(caja.text() + tx("ia_piensa"))
            if caja.text():
                self.zona_botones.addWidget(caja)
        pend = m.p.pendiente
        if pend is not None and pend.tipo == "efecto" and m.p.ganador is None and not (ia and pend.jugador != 0):
            self._panel_efecto(pend, esperadas)
            legales = []
        for a in legales:
            b = QPushButton(describir(tx, m, a))
            b.setMinimumHeight(30)
            b.setStyleSheet("text-align:left;padding:5px;")
            if tut:
                ok = a in esperadas
                b.setEnabled(ok)
                if ok:
                    b.setStyleSheet("text-align:left;padding:5px;font-weight:bold;" + RESALTE)
            b.clicked.connect(lambda _=False, acc=a: self.ejecutar(acc))
            self.zona_botones.addWidget(b)
        if m.p.ganador is not None:
            volver = QPushButton(tx("volver_menu"))
            volver.setObjectName("primario")
            volver.setMinimumHeight(34)
            volver.clicked.connect(self.ir_a_menu)
            self.zona_botones.addWidget(volver)
        if m.p.ganador is None and not tut:
            rendir = QPushButton(tx("rendirse"))
            rendir.setMinimumHeight(30)
            rendir.setStyleSheet("QPushButton{color:#ffb3a6;border-color:#c0533f;text-align:left;padding:5px;}")
            rendir.clicked.connect(self.rendirse)
            self.zona_botones.addWidget(rendir)
        if m.p.ganador is None and not tut and not (ia and m.p.quien_decide() != 0):
            decide = m.p.quien_decide()
            herr = QToolButton(text=tx("manual"))
            herr.setPopupMode(QToolButton.InstantPopup)
            menu = QMenu(herr)
            for op in ("robar", "barajar", "prueba+1", "prueba-1"):
                menu.addAction(tx("m_" + op), lambda o=op: self.ejecutar(A.Manual(decide, o)))
            herr.setMenu(menu)
            self.zona_botones.addWidget(herr)
        self.zona_botones.addStretch()

    # ---------------------------------------------------------------- efectos de habilidades

    def _panel_efecto(self, pend, esperadas):
        """Lo que pide el efecto en curso: elegir cartas (foco en la mesa), sí/no, opción o «Hecho»."""
        m, tx = self.motor, self.tx
        d = pend.datos
        tut = self.modo == "tutorial"
        caja = QFrame()
        caja.setObjectName("efecto")
        caja.setStyleSheet("QFrame#efecto{border:2px solid #4fd1ff;border-radius:10px;padding:4px;}")
        lay = QVBoxLayout(caja)
        fuente = m.p.carta(d["fuente"])
        titulo = QLabel(tx("ef_titulo", carta=fuente.defn.nombre_en(tx.idioma)))
        titulo.setStyleSheet("font-weight:bold;font-size:14px;color:#4fd1ff;")
        lay.addWidget(titulo)
        texto = linea_hab(fuente.defn, d["indice"], tx.idioma) if d.get("indice") is not None \
            else fuente.defn.texto_en(tx.idioma)
        lbl = QLabel(texto)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-style:italic;")
        lay.addWidget(lbl)
        if tut and pend.jugador != 0:
            lay.addWidget(QLabel(tx("ef_rival_decide", n=pend.jugador + 1)))
            self.zona_botones.addWidget(caja)
            return
        instr = QLabel(describir_efecto(tx, d))
        instr.setWordWrap(True)
        instr.setStyleSheet("font-size:13px;")
        lay.addWidget(instr)
        if d["modo"] == "manual":
            extra = QLabel(d.get("texto", ""))
            extra.setWordWrap(True)
            extra.setStyleSheet("color:#aaa;font-size:11px;")
            lay.addWidget(extra)

        def boton(texto, accion, principal=False):
            b = QPushButton(texto)
            b.setMinimumHeight(30)
            if principal:
                b.setObjectName("primario")
            if tut and accion not in (esperadas or []):
                b.setEnabled(False)
            elif tut:
                b.setStyleSheet("font-weight:bold;" + RESALTE)
            b.clicked.connect(lambda _=False, acc=accion: self.ejecutar(acc))
            lay.addWidget(b)
            return b

        q = pend.jugador
        if d["modo"] == "manual":
            boton(tx("ef_hecho"), A.Elegir(q, (), 1), True)
        elif d["modo"] == "si_no":
            boton(tx("ef_si"), A.Elegir(q, (), 1), True)
            boton(tx("ef_no"), A.Elegir(q, (), 0))
        elif d["modo"] == "opcion":
            for i, o in enumerate(d["opciones"]):
                txt = o if not any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in o) \
                    else f"{i + 1}. {o}"
                boton(txt, A.Elegir(q, (), i), i == 0).setStyleSheet("text-align:left;padding:5px;")
        else:
            self._preparar_eleccion(pend)
            fuera = [u for u in d["opciones"] if not self._en_mesa(u)]
            lay.addWidget(QLabel(tx("ef_pulsa_ver") if len(fuera) == len(d["opciones"]) else tx("ef_pulsa")))
            self.lbl_elegidas = QLabel()
            lay.addWidget(self.lbl_elegidas)
            if fuera:
                ver = QPushButton(tx("ef_ver_cartas"))
                ver.clicked.connect(self._dialogo_eleccion)
                lay.addWidget(ver)
            self.btn_confirmar = QPushButton(tx("ef_confirmar"))
            self.btn_confirmar.setObjectName("primario")
            self.btn_confirmar.setMinimumHeight(32)
            self.btn_confirmar.clicked.connect(self._confirmar_eleccion)
            lay.addWidget(self.btn_confirmar)
            self._actualizar_eleccion()
            if fuera and not self.eleccion_abierta:
                self.eleccion_abierta = True
                QTimer.singleShot(150, self._dialogo_eleccion)
        self.zona_botones.addWidget(caja)

    def _en_mesa(self, uid: int) -> bool:
        it = self.mesa.items_carta.get(uid)
        if it is None or not it.boca_arriba:
            return False
        c = self.motor.p.carta(uid)
        j = self.motor.j(c.dueno)
        return c in j.escena or c in j.mano or c is j.caso or c in j.zona_companero

    def _preparar_eleccion(self, pend):
        if getattr(self, "eleccion_de", None) is not pend:
            self.eleccion_de = pend
            self.eleccion = []
            self.eleccion_abierta = False

    def _actualizar_eleccion(self):
        pend = getattr(self, "eleccion_de", None)
        if pend is None or self.motor.p.pendiente is not pend:
            return
        d = pend.datos
        n = len(self.eleccion)
        self.lbl_elegidas.setText(self.tx("ef_elegidas", n=f"{n} / {d['max']}"))
        ok = d["min"] <= n <= d["max"]
        if self.modo == "tutorial":
            ok = ok and self._eleccion_tutorial() is not None
        self.btn_confirmar.setEnabled(ok)
        self.btn_confirmar.setStyleSheet(RESALTE if ok and self.modo == "tutorial" else "")

    def _dibujar_eleccion(self):
        """Foco en la mesa: cartas elegibles (borde azul) y elegidas (verde)."""
        m = self.motor
        pend = m.p.pendiente if m else None
        if pend is None or pend.tipo != "efecto" or pend.datos["modo"] != "elegir" or \
                (self.modo in ("tutorial", "ia") and pend.jugador != 0) or m.p.ganador is not None:
            self.mesa.marcar_eleccion(set(), set())
            return
        self.mesa.marcar_eleccion({u for u in pend.datos["opciones"] if self._en_mesa(u)}, set(self.eleccion))

    def alternar_eleccion(self, uid: int):
        pend = getattr(self, "eleccion_de", None)
        if pend is None or self.motor.p.pendiente is not pend:
            return
        if uid in self.eleccion:
            self.eleccion.remove(uid)
        else:
            if len(self.eleccion) >= pend.datos["max"]:
                if pend.datos["max"] == 1:
                    self.eleccion = []
                else:
                    return
            self.eleccion.append(uid)
        self._actualizar_eleccion()
        self._dibujar_eleccion()

    def _eleccion_tutorial(self):
        """La jugada del guion que coincide con las cartas marcadas (sin importar el orden)."""
        return next((x for x in self.guion.esperadas()
                     if isinstance(x, A.Elegir) and set(x.uids) == set(self.eleccion)), None)

    def _confirmar_eleccion(self):
        pend = getattr(self, "eleccion_de", None)
        if pend is None:
            return
        accion = A.Elegir(pend.jugador, tuple(self.eleccion))
        if self.modo == "tutorial":
            accion = self._eleccion_tutorial() or accion
        self.ejecutar(accion)

    def _dialogo_eleccion(self):
        pend = getattr(self, "eleccion_de", None)
        if pend is None or self.motor.p.pendiente is not pend:
            return
        d = pend.datos
        cartas = [self.motor.p.carta(u) for u in d.get("vistas") or d["opciones"]]
        dlg = DialogoElegir(self, cartas, set(d["opciones"]), d["min"], d["max"], list(self.eleccion),
                            describir_efecto(self.tx, d))
        if dlg.exec() == QDialog.Accepted:
            self.eleccion = dlg.elegidas()
            self._actualizar_eleccion()
            self._dibujar_eleccion()
            if d["min"] <= len(self.eleccion) <= d["max"] and self.modo != "tutorial":
                self._confirmar_eleccion()

    def rendirse(self):
        """Pregunta qué jugador se rinde (en partida local los dos juegan en el mismo equipo)."""
        if self.motor is None or self.motor.p.ganador is not None:
            return
        tx = self.tx
        if self.modo == "ia":
            if QMessageBox.question(self, tx("rendirse"), tx("ia_rendirse")) == QMessageBox.Yes:
                self.ia_gen += 1
                self.motor.aplicar(A.Rendirse(0))
                self.refrescar()
            return
        caja = QMessageBox(self)
        caja.setWindowTitle(tx("rendirse"))
        caja.setText(tx("rendirse_pregunta"))
        botones = {}
        decide = self.motor.p.quien_decide()
        for j in (decide, 1 - decide):
            botones[caja.addButton(tx("rendirse_jugador", n=j + 1), QMessageBox.AcceptRole)] = j
        caja.addButton(tx("cancelar"), QMessageBox.RejectRole)
        caja.exec()
        j = botones.get(caja.clickedButton())
        if j is not None:
            self.ejecutar(A.Rendirse(j))

    def acciones_permitidas(self) -> list:
        """Jugadas que el jugador puede hacer ahora (en el tutorial, solo la que toca)."""
        if self.motor is None:
            return []
        if self.modo == "tutorial":
            return self.guion.esperadas()
        if self.modo == "ia" and self.motor.p.quien_decide() != 0:
            return []
        return self.motor.legales()

    def _dibujar_tutorial(self):
        tut = self.modo == "tutorial"
        self.panel_tut.setVisible(tut)
        self.sc_acciones.setStyleSheet("")
        if not tut:
            self.mesa.resaltar([], set())
            return
        g, tx = self.guion, self.tx
        n, total = g.progreso()
        self.lbl_narrador.setText(g.narrador)
        self.lbl_progreso.setText(tx("tut_paso", n=min(n, total), total=total))
        self.lbl_tut.setText(g.texto(tx.idioma))
        tipo = g.tipo()
        self.btn_tut_salir.setText(tx("tut_salir"))
        ultimo = g.indice == len(g.pasos) - 1
        self.btn_tut_seguir.setText(tx("tut_fin") if ultimo else tx("tut_continuar"))
        self.btn_tut_seguir.setVisible(tipo in ("continuar", "rival"))
        self.lbl_tut_pista.setText(tx("tut_hazlo", narrador=g.narrador) if tipo == "usuario" else "")
        claves = list(g.resaltar())
        uids = set()
        if tipo == "usuario":
            # se resaltan exactamente las cartas que intervienen en la jugada esperada
            for a in g.esperadas():
                uids |= acciones_de_carta(a) | self.mesa._uids_arrastre(a)
                if isinstance(a, A.SiguientePista):
                    claves.append("file:0")
            claves = [c for c in claves if not c.startswith("carta:")]
        else:
            for c in claves:
                if c.startswith("carta:"):
                    uids |= {u for u, it in self.mesa.items_carta.items()
                             if self.motor.p.carta(u).defn.id == c[6:] and self.motor.p.carta(u).dueno == 0}
        if "acciones" in claves:
            self.sc_acciones.setStyleSheet("QScrollArea{%s}" % RESALTE)
        self.mesa.resaltar(claves, uids)

    def _zona(self, clave: str, w):
        self._zonas.setdefault(clave, []).append(w)
        return w

    def _dibujar_bloque(self, idx: int, mostrar_mano: bool):
        m, tx = self.motor, self.tx
        j = m.j(idx)
        caja = self.bloques[idx]
        viejo = caja.layout()
        if viejo is not None:
            QWidget().setLayout(viejo)   # descarta el layout anterior y sus widgets
        resaltado = idx == m.p.quien_decide() and m.p.ganador is None
        caja.setTitle(tx("jugador", n=idx + 1) + ("  ◀" if resaltado else ""))
        caja.setStyleSheet("QGroupBox{font-weight:bold;border:2px solid %s;border-radius:8px;margin-top:14px;padding-top:10px;}"
                           "QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 4px;}"
                           % (tema.ORO if resaltado else tema.BORDE))
        lay = QVBoxLayout(caja)
        fila = QHBoxLayout()
        fase = tx("fase_resolucion") if j.caso_resuelto else tx("fase_caso")
        fila.addWidget(self._zona(f"caso:{idx}", CartaWidget(self, j.caso,
                                  extra=f"{fase} · {len(j.pruebas)}/{m.nivel_caso(j)}")))
        fila.addWidget(self._zona(f"companero:{idx}", CartaWidget(
            self, j.companero, extra=tx("en_file") if j.companero_en_file else "")))
        for mr in j.zona_companero:
            fila.addWidget(CartaWidget(self, mr))
        info = QLabel(f"{tx('mazo')}: {len(j.mazo)}\n{tx('file')}: {j.cartas_file}\n"
                      f"{tx('pruebas')}: {len(j.pruebas)}")
        info.setStyleSheet("font-size:13px;padding:4px;")
        fila.addWidget(self._zona(f"info:{idx}", info))
        btn_desc = QToolButton(text=f"{tx('descarte')}: {len(j.descarte)}")
        btn_desc.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(btn_desc)
        for c in reversed(j.descarte):
            sub = menu.addMenu(c.defn.nombre_en(tx.idioma))
            if self.modo != "tutorial":
                self._ops_manuales(sub, c)
        btn_desc.setMenu(menu)
        fila.addWidget(self._zona(f"descarte:{idx}", btn_desc))
        fila.addSpacing(12)
        escena = QFrame()
        le = QHBoxLayout(escena)
        le.setContentsMargins(6, 4, 6, 4)
        le.addWidget(QLabel(tx("escena") + ":"))
        for c in j.escena:
            le.addWidget(self._zona(f"carta:{c.defn.id}", CartaWidget(self, c)) if idx == 0
                         else CartaWidget(self, c))
        le.addStretch()
        fila.addWidget(self._zona(f"escena:{idx}", escena), 1)
        lay.addLayout(fila)
        filam = QHBoxLayout()
        filam.addWidget(QLabel(tx("mano") + ":"))
        if mostrar_mano:
            for c in j.mano:
                w = CartaWidget(self, c)
                filam.addWidget(self._zona(f"carta:{c.defn.id}", w) if idx == 0 else w)
        else:
            filam.addWidget(CartaWidget(self, None, oculta=True))
            filam.addWidget(QLabel(tx("mano_oculta", n=len(j.mano))))
        filam.addStretch()
        cont = QWidget()
        cont.setLayout(filam)
        sc = QScrollArea()
        sc.setWidget(cont)
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setMinimumHeight(ALTO + 24)
        lay.addWidget(self._zona(f"mano:{idx}", sc))

    # ---------------------------------------------------------------- menús de carta

    def _ops_manuales(self, menu: QMenu, carta):
        decide = self.motor.p.quien_decide()
        for op in OPS_CARTA:
            menu.addAction(self.tx("m_" + op), lambda o=op, u=carta.uid: self.ejecutar(A.Manual(decide, o, u)))

    def menu_carta(self, carta, pos):
        m = self.motor
        if m is None:
            return
        menu = QMenu(self)
        tut = self.modo == "tutorial"
        for a in self.acciones_permitidas() if self.modo == "ia" else m.legales():
            if carta.uid in acciones_de_carta(a):
                act = menu.addAction(describir(self.tx, m, a), lambda acc=a: self.ejecutar(acc))
                if tut and not self.guion.es_esperada(a):
                    act.setEnabled(False)
        if m.p.ganador is None and not tut and not (self.modo == "ia" and m.p.quien_decide() != 0):
            if not menu.isEmpty():
                menu.addSeparator()
            self._ops_manuales(menu.addMenu(self.tx("manual")), carta)
        if not menu.isEmpty():
            menu.addSeparator()
        menu.addAction(self.tx("ver_grande"), lambda d=carta.defn: self.ver_en_grande(d))
        if not menu.isEmpty():
            menu.exec(pos)

    # ---------------------------------------------------------------- ajustes

    def elegir_imagenes(self):
        carpeta = QFileDialog.getExistingDirectory(self, self.tx("carpeta_imagenes"),
                                                   self.cfg.g.get("carpeta_imagenes", ""))
        if carpeta:
            self.cfg.g["carpeta_imagenes"] = carpeta
            self.cfg.guardar()
            self.imagenes.cargar(carpeta)
            self.refrescar()

    def cambiar_idioma(self, idioma: str):
        self.tx.cambiar(idioma)
        self.cfg.g["idioma"] = idioma
        self.cfg.guardar()
        self._menus()
        actual = self.pila.currentWidget()
        if actual is self.pag_perfiles:
            self.pag_perfiles.refrescar()
        elif actual is self.pag_menu:
            self.pag_menu.refrescar()
        else:
            self.refrescar()

    def _toggle_ocultar(self, valor: bool):
        self.cfg.g["ocultar_manos"] = "si" if valor else "no"
        self.cfg.guardar()
        self.refrescar()
