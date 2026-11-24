"""Pantallas fuera del tablero: elegir perfil, menú de modos de juego y registro de accesos."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from core.perfiles import GestorPerfiles, PerfilError

ESTILO_BOTON_GRANDE = "QPushButton{padding:12px;text-align:left;min-height:52px;}"


class BotonModo(QPushButton):
    """Botón grande con título en negrita y una descripción debajo."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(ESTILO_BOTON_GRANDE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        self.titulo = QLabel()
        self.titulo.setStyleSheet("font-size:16px;font-weight:bold;background:transparent;")
        self.desc = QLabel()
        self.desc.setWordWrap(True)
        self.desc.setStyleSheet("color:#a9b1c2;background:transparent;")
        for w in (self.titulo, self.desc):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            lay.addWidget(w)

    def textos(self, titulo: str, desc: str):
        self.titulo.setText(titulo)
        self.desc.setText(desc)
        self.setMinimumHeight(self.layout().sizeHint().height())

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if not hasattr(self, "titulo"):
            return
        gris = "" if self.isEnabled() else "color:#6c7487;"
        self.titulo.setStyleSheet("font-size:16px;font-weight:bold;background:transparent;" + gris)


class PaginaPerfiles(QWidget):
    elegido = Signal(str)

    def __init__(self, ventana):
        super().__init__()
        self.v = ventana
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 40, 0, 20)
        caja = QFrame()
        caja.setFixedWidth(460)
        lc = QVBoxLayout(caja)
        self.titulo = QLabel()
        self.titulo.setStyleSheet("font-size:26px;font-weight:bold;color:#d9a845;")
        lc.addWidget(self.titulo)
        self.vacio = QLabel()
        self.vacio.setWordWrap(True)
        lc.addWidget(self.vacio)
        self.lista = QListWidget()
        self.lista.setStyleSheet("QListWidget{font-size:15px;} QListWidget::item{padding:8px;}")
        self.lista.itemDoubleClicked.connect(lambda _: self._entrar())
        self.lista.setMaximumHeight(320)
        lc.addWidget(self.lista)
        self.btn_entrar = QPushButton()
        self.btn_entrar.clicked.connect(self._entrar)
        lc.addWidget(self.btn_entrar)
        lc.addSpacing(18)
        fila = QHBoxLayout()
        self.nombre = QLineEdit()
        self.nombre.setMaxLength(24)
        self.nombre.returnPressed.connect(self._crear)
        fila.addWidget(self.nombre, 1)
        self.btn_crear = QPushButton()
        self.btn_crear.clicked.connect(self._crear)
        fila.addWidget(self.btn_crear)
        lc.addLayout(fila)
        self.aviso = QLabel()
        self.aviso.setWordWrap(True)
        self.aviso.setStyleSheet("color:#888;font-size:10px;")
        lc.addSpacing(12)
        lc.addWidget(self.aviso)
        lc.addStretch()
        lay.addWidget(caja, 1, Qt.AlignHCenter)

    def refrescar(self):
        tx, gp = self.v.tx, self.v.perfiles
        self.titulo.setText(tx("perfiles_titulo"))
        self.btn_entrar.setText(tx("perfil_entrar"))
        self.btn_crear.setText(tx("perfil_nuevo"))
        self.nombre.setPlaceholderText(tx("perfil_nombre"))
        self.aviso.setText(tx("aviso"))
        self.lista.clear()
        perfiles = gp.listar()
        self.vacio.setText(tx("perfil_vacio") if not perfiles else "")
        self.vacio.setVisible(not perfiles)
        for p in perfiles:
            info = tx("perfil_info", accesos=p.get("accesos", 0), ultimo=(p.get("ultimo_acceso") or "")[:16] or tx("nunca"))
            if p.get("tutorial_completado"):
                info += " · " + tx("tutorial_hecho")
            it = QListWidgetItem(f"{p['nombre']}\n{info}")
            it.setData(Qt.UserRole, p["nombre"])
            self.lista.addItem(it)
        if perfiles:
            self.lista.setCurrentRow(0)
        self.btn_entrar.setEnabled(bool(perfiles))

    def _entrar(self):
        it = self.lista.currentItem()
        if it:
            self.elegido.emit(it.data(Qt.UserRole))

    def _crear(self):
        try:
            p = self.v.perfiles.crear(self.nombre.text())
        except PerfilError as e:
            QMessageBox.information(self, self.v.tx("titulo"), str(e))
            return
        self.nombre.clear()
        self.elegido.emit(p["nombre"])


class PaginaMenu(QWidget):
    def __init__(self, ventana):
        super().__init__()
        self.v = ventana
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 40, 0, 20)
        caja = QFrame()
        caja.setFixedWidth(600)
        lc = QVBoxLayout(caja)
        self.hola = QLabel()
        self.hola.setStyleSheet("font-size:26px;font-weight:bold;color:#d9a845;")
        lc.addWidget(self.hola)
        self.stats = QLabel()
        self.stats.setStyleSheet("color:#a9b1c2;")
        lc.addWidget(self.stats)
        lc.addSpacing(16)
        self.modos = QLabel()
        self.modos.setStyleSheet("font-size:14px;font-weight:bold;")
        lc.addWidget(self.modos)
        self.botones = {}
        for clave, fn in (("tutorial", ventana.iniciar_tutorial), ("local", ventana.iniciar_local),
                          ("ia", None), ("online", None)):
            if clave == "ia":
                self.lbl_herr = QLabel()
                self.lbl_herr.setStyleSheet("font-size:14px;font-weight:bold;margin-top:10px;")
                lc.addWidget(self.lbl_herr)
                for clave2, fn2 in (("mazos", ventana.ir_a_mazos), ("contenido", ventana.ir_a_contenido),
                                    ("traducciones", ventana.ir_a_traducciones), ("fundas", ventana.elegir_fundas)):
                    b2 = BotonModo()
                    b2.clicked.connect(fn2)
                    lc.addWidget(b2)
                    self.botones[clave2] = b2
                self.lbl_prox = QLabel()
                self.lbl_prox.setStyleSheet("font-size:14px;font-weight:bold;margin-top:10px;")
                lc.addWidget(self.lbl_prox)
            b = BotonModo()
            if fn:
                b.clicked.connect(fn)
            else:
                b.setEnabled(False)
            lc.addWidget(b)
            self.botones[clave] = b
        lc.addSpacing(16)
        fila = QHBoxLayout()
        self.btn_registro = QPushButton()
        self.btn_registro.clicked.connect(self._ver_registro)
        self.btn_perfil = QPushButton()
        self.btn_perfil.clicked.connect(ventana.cambiar_perfil)
        fila.addWidget(self.btn_registro)
        fila.addWidget(self.btn_perfil)
        lc.addLayout(fila)
        lc.addStretch()
        lay.addWidget(caja, 1, Qt.AlignHCenter)

    def refrescar(self):
        tx = self.v.tx
        p = self.v.perfiles.perfiles[self.v.perfil]
        self.hola.setText(tx("menu_hola", nombre=p["nombre"]))
        self.stats.setText(tx("estadisticas", ini=p.get("partidas_iniciadas", 0),
                              fin=p.get("partidas_terminadas", 0), tut=p.get("tutoriales_completados", 0)))
        self.modos.setText(tx("menu_modos"))
        self.botones["tutorial"].textos(tx("modo_tutorial"), tx("modo_tutorial_desc"))
        self.botones["local"].textos(tx("modo_local"), tx("modo_local_desc"))
        self.botones["mazos"].textos(tx("modo_mazos"), tx("modo_mazos_desc"))
        self.botones["contenido"].textos(tx("modo_contenido"), tx("modo_contenido_desc"))
        self.botones["traducciones"].textos(tx("modo_traducciones"), tx("modo_traducciones_desc"))
        self.botones["fundas"].textos(tx("modo_fundas"), tx("modo_fundas_desc", funda=self.v.funda_perfil()))
        self.lbl_herr.setText(tx("menu_herramientas"))
        self.lbl_prox.setText(tx("proximamente"))
        self.botones["ia"].textos(tx("modo_ia"), tx("proximamente"))
        self.botones["online"].textos(tx("modo_online"), tx("proximamente"))
        self.btn_registro.setText(tx("ver_registro"))
        self.btn_perfil.setText(tx("cambiar_perfil"))

    def _ver_registro(self):
        DialogoRegistro(self.v).exec()


class DialogoRegistro(QDialog):
    def __init__(self, ventana):
        super().__init__(ventana)
        tx = ventana.tx
        self.setWindowTitle(tx("registro_titulo", nombre=ventana.perfil))
        self.resize(640, 460)
        lay = QVBoxLayout(self)
        filas = list(reversed(ventana.perfiles.leer_registro(ventana.perfil)))
        t = QTableWidget(len(filas), 3)
        t.setHorizontalHeaderLabels([tx("col_fecha"), tx("col_evento"), tx("col_detalle")])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        for i, r in enumerate(filas):
            t.setItem(i, 0, QTableWidgetItem(r["fecha"]))
            t.setItem(i, 1, QTableWidgetItem(tx("ev_" + r["evento"])))
            t.setItem(i, 2, QTableWidgetItem(r.get("detalle", "")))
        t.resizeColumnsToContents()
        lay.addWidget(t)
        b = QPushButton(tx("cerrar"))
        b.clicked.connect(self.accept)
        lay.addWidget(b, alignment=Qt.AlignRight)
