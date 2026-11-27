"""Pantallas fuera del tablero: elegir perfil y registro de accesos (el menú está en menu_principal.py)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from core.perfiles import GestorPerfiles, PerfilError

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
        logo = QPixmap(str(ventana.base / "recursos" / "logo.png"))
        if not logo.isNull():
            lbl_logo = QLabel()
            lbl_logo.setPixmap(logo.scaled(132, 132, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lbl_logo.setAlignment(Qt.AlignCenter)
            lbl_logo.setStyleSheet("background:transparent;")
            lc.addWidget(lbl_logo)
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
