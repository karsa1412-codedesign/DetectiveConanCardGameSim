"""Revisar y corregir las traducciones a mano.

Las correcciones se guardan en datos/traducciones/<idioma>.json (apartado «manual»), mandan
sobre DeepL y sobre el glosario, y no se pierden al volver a traducir. Como se guardan por
texto japonés, corregir un texto lo corrige en todas las cartas que lo comparten
(reimpresiones y versiones paralelas).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core.cartas import CartaDef
from datos.traduccion import DEEPL_IDIOMAS, TraduccionError, Traductor
from . import tema

NOMBRES_IDIOMA = {"es": "Castellano", "ca": "Català", "en": "English", "fr": "Français", "it": "Italiano",
                  "pt": "Português", "de": "Deutsch"}
MAX_FILAS = 400


class PaginaTraducciones(QWidget):
    def __init__(self, ventana):
        super().__init__()
        self.v = ventana
        self.tr: Traductor | None = None
        self.carta: dict | None = None
        self.edits_rasgos: list[tuple[str, QLineEdit]] = []
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(24, 16, 24, 12)
        cab = QHBoxLayout()
        self.titulo = QLabel()
        self.titulo.setStyleSheet(tema.TITULO)
        cab.addWidget(self.titulo)
        cab.addStretch()
        self.btn_volver = QPushButton()
        self.btn_volver.clicked.connect(self._volver)
        cab.addWidget(self.btn_volver)
        raiz.addLayout(cab)
        self.ayuda = QLabel()
        self.ayuda.setWordWrap(True)
        self.ayuda.setStyleSheet(tema.SUBTITULO)
        raiz.addWidget(self.ayuda)
        filtros = QHBoxLayout()
        self.idioma = QComboBox()
        for codigo in DEEPL_IDIOMAS:
            self.idioma.addItem(NOMBRES_IDIOMA.get(codigo, codigo), codigo)
        self.idioma.currentIndexChanged.connect(self._cambiar_idioma)
        self.buscar = QLineEdit()
        self.buscar.textChanged.connect(self.filtrar)
        self.estado = QComboBox()
        self.estado.currentIndexChanged.connect(self.filtrar)
        self.paquete = QComboBox()
        self.paquete.currentIndexChanged.connect(self.filtrar)
        filtros.addWidget(self.idioma)
        filtros.addWidget(self.buscar, 1)
        filtros.addWidget(self.estado)
        filtros.addWidget(self.paquete)
        raiz.addLayout(filtros)
        split = QSplitter()
        raiz.addWidget(split, 1)
        # lista
        izq = QWidget()
        li = QVBoxLayout(izq)
        li.setContentsMargins(0, 0, 0, 0)
        self.tabla = QTableWidget(0, 4)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabla.setSelectionMode(QTableWidget.SingleSelection)
        self.tabla.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabla.currentCellChanged.connect(lambda r, *_: self._elegir_fila(r))
        li.addWidget(self.tabla, 1)
        self.lbl_cuenta = QLabel()
        self.lbl_cuenta.setStyleSheet(tema.SUBTITULO)
        li.addWidget(self.lbl_cuenta)
        split.addWidget(izq)
        # editor
        der = QFrame()
        ld = QHBoxLayout(der)
        self.previa = QLabel()
        self.previa.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.previa.setFixedWidth(270)
        ld.addWidget(self.previa)
        ed = QVBoxLayout()
        self.lbl_id = QLabel()
        self.lbl_id.setStyleSheet("font-size:15px;font-weight:bold;")
        ed.addWidget(self.lbl_id)
        self.form = QFormLayout()
        self.nombre_ja = QLabel()
        self.nombre_ja.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.nombre = QLineEdit()
        self.lbl_nombre_ja, self.lbl_nombre = QLabel(), QLabel()
        self.form.addRow(self.lbl_nombre_ja, self.nombre_ja)
        self.form.addRow(self.lbl_nombre, self.nombre)
        ed.addLayout(self.form)
        self.caja_rasgos = QFormLayout()
        ed.addLayout(self.caja_rasgos)
        self.lbl_texto_ja = QLabel()
        self.lbl_texto_ja.setStyleSheet("font-weight:bold;")
        ed.addWidget(self.lbl_texto_ja)
        self.texto_ja = QPlainTextEdit()
        self.texto_ja.setReadOnly(True)
        self.texto_ja.setMaximumHeight(120)
        ed.addWidget(self.texto_ja)
        self.lbl_texto = QLabel()
        self.lbl_texto.setStyleSheet("font-weight:bold;")
        ed.addWidget(self.lbl_texto)
        self.texto = QPlainTextEdit()
        ed.addWidget(self.texto, 1)
        self.lbl_compartido = QLabel()
        self.lbl_compartido.setWordWrap(True)
        self.lbl_compartido.setStyleSheet(tema.SUBTITULO)
        ed.addWidget(self.lbl_compartido)
        botones = QHBoxLayout()
        self.btn_restablecer = QPushButton()
        self.btn_restablecer.clicked.connect(self.restablecer)
        self.btn_guardar = QPushButton()
        self.btn_guardar.setObjectName("primario")
        self.btn_guardar.clicked.connect(self.guardar)
        self.btn_siguiente = QPushButton()
        self.btn_siguiente.clicked.connect(lambda: self._mover(1))
        botones.addWidget(self.btn_restablecer)
        botones.addStretch()
        botones.addWidget(self.btn_siguiente)
        botones.addWidget(self.btn_guardar)
        ed.addLayout(botones)
        ld.addLayout(ed, 1)
        split.addWidget(der)
        split.setSizes([520, 860])

    # ------------------------------------------------------------ datos
    @property
    def cartas(self) -> list[dict]:
        return self.v.catalogo_local.cartas

    @property
    def codigo(self) -> str:
        return self.idioma.currentData() or "es"

    def _cargar_traductor(self):
        try:
            self.tr = self.v.traductor(self.codigo, None)
        except TraduccionError as e:
            self.tr = None
            QMessageBox.warning(self, self.v.tx("titulo"), str(e))

    def refrescar(self):
        tx = self.v.tx
        self.titulo.setText(tx("tr_titulo"))
        self.btn_volver.setText(tx("volver_menu_corto"))
        self.ayuda.setText(tx("tr_ayuda"))
        self.buscar.setPlaceholderText(tx("tr_buscar"))
        self.btn_guardar.setText(tx("tr_guardar"))
        self.btn_restablecer.setText(tx("tr_restablecer"))
        self.btn_siguiente.setText(tx("tr_siguiente"))
        self.lbl_texto_ja.setText(tx("tr_texto_original"))
        self.lbl_texto.setText(tx("tr_texto_traducido"))
        self.lbl_nombre_ja.setText(tx("tr_nombre_original"))
        self.lbl_nombre.setText(tx("tr_nombre_traducido"))
        self.tabla.setHorizontalHeaderLabels([tx("tr_col_id"), tx("tr_col_original"), tx("tr_col_traduccion"), ""])
        # idioma por defecto: el de la interfaz, si es traducible
        self.idioma.blockSignals(True)
        i = self.idioma.findData(tx.idioma if tx.idioma in DEEPL_IDIOMAS else "es")
        if self.tr is None and i >= 0:
            self.idioma.setCurrentIndex(i)
        self.idioma.blockSignals(False)
        for cb, opciones in ((self.estado, [("todas", tx("tr_f_todas")), ("manual", tx("tr_f_manual")),
                                            ("sin", tx("tr_f_sin"))]),
                             (self.paquete, [(None, tx("mz_todas_colecciones"))] +
                              [(p, p) for p in sorted({c.get("paquete", "") for c in self.cartas if c.get("paquete")})])):
            actual = cb.currentData()
            cb.blockSignals(True)
            cb.clear()
            for dato, texto in opciones:
                cb.addItem(texto, dato)
            j = cb.findData(actual)
            cb.setCurrentIndex(j if j >= 0 else 0)
            cb.blockSignals(False)
        self._cargar_traductor()
        self.filtrar()

    def _cambiar_idioma(self):
        if not self._descartar_cambios():
            return
        self._cargar_traductor()
        self.filtrar()

    def _estado(self, c: dict) -> str:
        tr = self.tr
        ja_t = c["texto"].get("ja", "")
        manual = tr.es_manual("nombres", c["nombre"]["ja"]) or (ja_t and tr.es_manual("textos", ja_t)) or \
            any(tr.es_manual("rasgos", r) for r in c.get("rasgos_ja", []))
        if manual:
            return "manual"
        if (ja_t and not tr.traduccion_actual("textos", ja_t)) or not tr.traduccion_actual("nombres", c["nombre"]["ja"]):
            return "sin"
        return "ok"

    def filtrar(self):
        tx = self.v.tx
        self.tabla.setRowCount(0)
        if self.tr is None:
            return
        if not self.cartas:
            self.lbl_cuenta.setText(tx("trad_sin_cartas"))
            self._mostrar(None)
            return
        texto = self.buscar.text().strip().lower()
        estado, paquete = self.estado.currentData(), self.paquete.currentData()
        filas = []
        for c in self.cartas:
            if paquete and c.get("paquete") != paquete:
                continue
            est = self._estado(c)
            if estado == "manual" and est != "manual" or estado == "sin" and est != "sin":
                continue
            if texto:
                pajar = " ".join([c["id"], *c["nombre"].values(), *c["texto"].values()]).lower()
                if texto not in pajar:
                    continue
            filas.append((c, est))
        self.tabla.setRowCount(min(len(filas), MAX_FILAS))
        marca = {"manual": "✎", "sin": "—", "ok": ""}
        for i, (c, est) in enumerate(filas[:MAX_FILAS]):
            it = QTableWidgetItem(c["id"])
            it.setData(Qt.UserRole, c["id"])
            self.tabla.setItem(i, 0, it)
            self.tabla.setItem(i, 1, QTableWidgetItem(c["nombre"].get("ja", "")))
            self.tabla.setItem(i, 2, QTableWidgetItem(c["nombre"].get(self.codigo, "")))
            m = QTableWidgetItem(marca[est])
            m.setToolTip(tx("tr_f_manual") if est == "manual" else (tx("tr_f_sin") if est == "sin" else ""))
            self.tabla.setItem(i, 3, m)
        self.tabla.resizeColumnToContents(0)
        self.tabla.resizeColumnToContents(3)
        self.lbl_cuenta.setText(tx("tr_cuenta", n=len(filas)) +
                                (" " + tx("mz_afina", m=MAX_FILAS) if len(filas) > MAX_FILAS else ""))
        if filas:
            self.tabla.setCurrentCell(0, 0)
        else:
            self._mostrar(None)

    # ------------------------------------------------------------ editor
    def _elegir_fila(self, fila: int):
        it = self.tabla.item(fila, 0) if fila >= 0 else None
        if it is None:
            return
        cid = it.data(Qt.UserRole)
        if self.carta and self.carta["id"] == cid:
            return
        if not self._descartar_cambios():
            return
        self._mostrar(next((c for c in self.cartas if c["id"] == cid), None))

    def _mostrar(self, c: dict | None):
        tx = self.v.tx
        self.carta = c
        while self.caja_rasgos.rowCount():
            self.caja_rasgos.removeRow(0)
        self.edits_rasgos = []
        activo = c is not None and self.tr is not None
        for w in (self.nombre, self.texto, self.btn_guardar, self.btn_restablecer, self.btn_siguiente):
            w.setEnabled(activo)
        if not activo:
            self.lbl_id.setText("")
            self.nombre_ja.setText("")
            self.nombre.clear()
            self.texto_ja.clear()
            self.texto.clear()
            self.previa.clear()
            self.lbl_compartido.setText("")
            return
        tr = self.tr
        self.lbl_id.setText(f"{c['id']} · {c.get('paquete', '')} · {tx('tipo_' + c['tipo'])}")
        self.nombre_ja.setText(c["nombre"].get("ja", ""))
        self.nombre.setText(tr.traduccion_actual("nombres", c["nombre"]["ja"]))
        for r in c.get("rasgos_ja", []):
            e = QLineEdit(tr.traduccion_actual("rasgos", r))
            self.caja_rasgos.addRow(f"{tx('mz_rasgos')}: {r}", e)
            self.edits_rasgos.append((r, e))
        ja_t = c["texto"].get("ja", "")
        self.texto_ja.setPlainText(ja_t)
        self.texto.setPlainText(tr.traduccion_actual("textos", ja_t) if ja_t else "")
        self.texto.setEnabled(bool(ja_t))
        n = sum(1 for x in self.cartas if x["texto"].get("ja", "") == ja_t) if ja_t else 0
        self.lbl_compartido.setText(tx("tr_compartido", n=n) if n > 1 else "")
        self._previa()

    def _previa(self):
        if not self.carta:
            return
        d = CartaDef.desde_dict(self.carta)
        pix = self.v.imagenes.mostrar(d, self.codigo)
        if pix is not None and not pix.isNull():
            self.previa.setPixmap(pix.scaledToWidth(260 if pix.width() <= pix.height() else 270,
                                                    Qt.SmoothTransformation))
        else:
            self.previa.setText(self.v.tx("tr_sin_imagen"))

    def _cambios(self) -> list[tuple[str, str, str]]:
        """[(tipo, japonés, valor nuevo)] de lo que difiere de lo guardado."""
        if not self.carta or self.tr is None:
            return []
        tr, c = self.tr, self.carta
        out = []
        if self.nombre.text().strip() != tr.traduccion_actual("nombres", c["nombre"]["ja"]):
            out.append(("nombres", c["nombre"]["ja"], self.nombre.text()))
        for r, e in self.edits_rasgos:
            if e.text().strip() != tr.traduccion_actual("rasgos", r):
                out.append(("rasgos", r, e.text()))
        ja_t = c["texto"].get("ja", "")
        if ja_t and self.texto.toPlainText().strip() != tr.traduccion_actual("textos", ja_t).strip():
            out.append(("textos", ja_t, self.texto.toPlainText()))
        return out

    def _descartar_cambios(self) -> bool:
        if not self._cambios():
            return True
        tx = self.v.tx
        r = QMessageBox.question(self, tx("titulo"), tx("tr_guardar_antes"),
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            self.guardar()
            return True
        return r == QMessageBox.Discard

    def _aplicar_y_guardar(self):
        cat = self.v.catalogo_local
        self.tr.aplicar(cat.cartas)
        cat.guardar()
        cid = self.carta["id"] if self.carta else None
        self.v.recargar_catalogo()
        self.carta = next((c for c in self.cartas if c["id"] == cid), None) if cid else None

    def guardar(self):
        cambios = self._cambios()
        if not cambios:
            return
        for tipo, ja, valor in cambios:
            self.tr.corregir(tipo, ja, valor)
        self._aplicar_y_guardar()
        fila = self.tabla.currentRow()
        self._actualizar_fila(fila)
        self._mostrar(self.carta)

    def restablecer(self):
        if not self.carta:
            return
        tx = self.v.tx
        if QMessageBox.question(self, tx("titulo"), tx("tr_confirmar_restablecer")) != QMessageBox.Yes:
            return
        c = self.carta
        self.tr.restablecer("nombres", c["nombre"]["ja"])
        for r in c.get("rasgos_ja", []):
            self.tr.restablecer("rasgos", r)
        if c["texto"].get("ja"):
            self.tr.restablecer("textos", c["texto"]["ja"])
        self._aplicar_y_guardar()
        self._actualizar_fila(self.tabla.currentRow())
        self._mostrar(self.carta)

    def _actualizar_fila(self, fila: int):
        if fila < 0 or not self.carta:
            return
        est = self._estado(self.carta)
        self.tabla.item(fila, 2).setText(self.carta["nombre"].get(self.codigo, ""))
        self.tabla.item(fila, 3).setText({"manual": "✎", "sin": "—", "ok": ""}[est])

    def _mover(self, paso: int):
        fila = self.tabla.currentRow() + paso
        if 0 <= fila < self.tabla.rowCount():
            self.tabla.setCurrentCell(fila, 0)

    def _volver(self):
        if self._descartar_cambios():
            self.carta = None
            self.v.ir_a_menu()
