"""Creador de mazos: buscar cartas, montar el mazo, validarlo, guardarlo e importarlo/exportarlo."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from core.cartas import CASO, COMPANERO, EVENTO, PERSONAJE, CartaDef, Mazo
from . import tema

MAX_RESULTADOS = 240
COLORES_HEX = {"azul": "#2f5fa8", "rojo": "#b23b3b", "verde": "#2f8a4e", "amarillo": "#c49a1a",
               "blanco": "#8c8c8c", "negro": "#3a3a3a"}


def nombre_archivo(nombre: str) -> str:
    limpio = re.sub(r'[\\/:*?"<>|]+', "_", nombre).strip() or "mazo"
    return limpio[:60] + ".json"


def mazo_a_texto(m: Mazo) -> str:
    lineas = [f"# {m.nombre}", f"Compañero: {m.companero}", f"Caso: {m.caso}"]
    lineas += [f"{n} {cid}" for cid, n in sorted(m.cartas.items())]
    return "\n".join(lineas) + "\n"


def texto_a_mazo(texto: str, cat) -> tuple[Mazo, list[str]]:
    """Admite «3 D10011», «3x D10011», «D10011 x3» y líneas «Compañero:»/«Caso:»."""
    nombre, comp, caso, cartas, avisos = "Mazo importado", "", "", {}, []
    for linea in texto.splitlines():
        l = linea.strip()
        if not l:
            continue
        if l.startswith("#"):
            nombre = l.lstrip("# ").strip() or nombre
            continue
        m = re.match(r"(?i)(compa[ñn]er[oa]|company|partner|caso|cas|case)\s*[:=]\s*(\S+)", l)
        if m:
            cid = m.group(2).upper()
            if m.group(1).lower().startswith(("c", "p")) and not m.group(1).lower().startswith("cas"):
                comp = cid
            else:
                caso = cid
            continue
        m = re.match(r"(\d+)\s*[xX×]?\s+(\S+)$", l) or re.match(r"(\S+)\s+[xX×]\s*(\d+)$", l)
        if not m:
            avisos.append(f"No entiendo la línea: {l}")
            continue
        a, b = m.groups()
        n, cid = (int(a), b) if a.isdigit() else (int(b), a)
        cid = cid.upper()
        if cid not in cat:
            avisos.append(f"Carta desconocida: {cid}")
            continue
        d = cat[cid]
        if d.tipo == COMPANERO:
            comp = cid
        elif d.tipo == CASO:
            caso = cid
        else:
            cartas[cid] = cartas.get(cid, 0) + n
    return Mazo(nombre, comp, caso, cartas), avisos


class PaginaMazos(QWidget):
    def __init__(self, ventana):
        super().__init__()
        self.v = ventana
        self.mazo = Mazo("", "", "", {})
        self.ruta: Path | None = None
        self.cambiado = False
        self._iconos: dict[str, QIcon] = {}
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
        split = QSplitter()
        raiz.addWidget(split, 1)
        split.addWidget(self._panel_busqueda())
        split.addWidget(self._panel_detalle())
        split.addWidget(self._panel_mazo())
        split.setSizes([620, 300, 460])

    # ------------------------------------------------------------ paneles

    def _panel_busqueda(self):
        w = QWidget()
        l = QVBoxLayout(w)
        self.buscar = QLineEdit()
        self.buscar.textChanged.connect(self.filtrar)
        l.addWidget(self.buscar)
        fila = QHBoxLayout()
        self.f_color = QComboBox()
        self.f_tipo = QComboBox()
        self.f_nivel = QComboBox()
        self.f_paquete = QComboBox()
        for cb in (self.f_color, self.f_tipo, self.f_nivel, self.f_paquete):
            cb.currentIndexChanged.connect(self.filtrar)
            fila.addWidget(cb)
        l.addLayout(fila)
        self.lista = QListWidget()
        self.lista.setViewMode(QListWidget.IconMode)
        self.lista.setIconSize(QSize(86, 120))
        self.lista.setGridSize(QSize(112, 178))
        self.lista.setResizeMode(QListWidget.Adjust)
        self.lista.setMovement(QListWidget.Static)
        self.lista.setWordWrap(True)
        self.lista.setUniformItemSizes(True)
        self.lista.currentItemChanged.connect(lambda it, _: self.mostrar(it.data(Qt.UserRole) if it else None))
        self.lista.itemDoubleClicked.connect(lambda it: self.anadir(it.data(Qt.UserRole)))
        self.det_img_ampliar = True
        l.addWidget(self.lista, 1)
        self.lbl_resultados = QLabel()
        self.lbl_resultados.setStyleSheet(tema.SUBTITULO)
        l.addWidget(self.lbl_resultados)
        return w

    def _panel_detalle(self):
        w = QFrame()
        l = QVBoxLayout(w)
        self.det_img = QLabel()
        self.det_img.setAlignment(Qt.AlignCenter)
        self.det_img.setMinimumHeight(300)
        l.addWidget(self.det_img)
        self.det_txt = QLabel()
        self.det_txt.setWordWrap(True)
        self.det_txt.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.det_txt.setTextInteractionFlags(Qt.TextSelectableByMouse)
        l.addWidget(self.det_txt, 1)
        self.btn_anadir = QPushButton()
        self.btn_anadir.setObjectName("primario")
        self.btn_anadir.clicked.connect(lambda: self.anadir(self._actual()))
        l.addWidget(self.btn_anadir)
        return w

    def _panel_mazo(self):
        w = QWidget()
        l = QVBoxLayout(w)
        fila = QHBoxLayout()
        self.nombre = QLineEdit()
        self.nombre.textEdited.connect(lambda t: self._marcar())
        fila.addWidget(self.nombre, 1)
        l.addLayout(fila)
        self.lbl_comp = QPushButton()
        self.lbl_comp.clicked.connect(lambda: self.mostrar(self.v.catalogo.por_id.get(self.mazo.companero)))
        self.lbl_caso = QPushButton()
        self.lbl_caso.clicked.connect(lambda: self.mostrar(self.v.catalogo.por_id.get(self.mazo.caso)))
        for b in (self.lbl_comp, self.lbl_caso):
            b.setStyleSheet("text-align:left;")
            l.addWidget(b)
        self.tabla = QTableWidget(0, 4)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla.cellClicked.connect(lambda r, c: self.mostrar(self.v.catalogo.por_id.get(
            self.tabla.item(r, 1).data(Qt.UserRole))))
        l.addWidget(self.tabla, 1)
        self.lbl_total = QLabel()
        self.lbl_total.setStyleSheet("font-size:15px;font-weight:bold;")
        l.addWidget(self.lbl_total)
        self.lbl_curva = QLabel()
        self.lbl_curva.setStyleSheet(tema.SUBTITULO + "font-family:monospace;")
        l.addWidget(self.lbl_curva)
        self.lbl_errores = QLabel()
        self.lbl_errores.setWordWrap(True)
        l.addWidget(self.lbl_errores)
        botones = QHBoxLayout()
        self.b_nuevo, self.b_abrir, self.b_guardar, self.b_importar, self.b_exportar, self.b_borrar = (
            QPushButton() for _ in range(6))
        for b, fn in ((self.b_nuevo, self.nuevo), (self.b_abrir, self.abrir), (self.b_guardar, self.guardar),
                      (self.b_importar, self.importar), (self.b_exportar, self.exportar),
                      (self.b_borrar, self.borrar)):
            b.clicked.connect(fn)
            botones.addWidget(b)
        self.b_guardar.setObjectName("primario")
        l.addLayout(botones)
        return w

    # ------------------------------------------------------------ datos

    @property
    def idioma(self):
        return self.v.tx.idioma

    def carpeta_mazos(self) -> Path:
        return self.v.rutas.usuario / "mazos"

    def refrescar(self):
        tx = self.v.tx
        self.titulo.setText(tx("mz_titulo"))
        self.btn_volver.setText(tx("volver_menu_corto"))
        self.buscar.setPlaceholderText(tx("mz_buscar"))
        self.btn_anadir.setText(tx("mz_anadir"))
        self.nombre.setPlaceholderText(tx("mz_nombre"))
        for b, k in ((self.b_nuevo, "mz_nuevo"), (self.b_abrir, "mz_abrir"), (self.b_guardar, "mz_guardar"),
                     (self.b_importar, "mz_importar"), (self.b_exportar, "mz_exportar"), (self.b_borrar, "mz_borrar")):
            b.setText(tx(k))
        cat = self.v.catalogo.todas()
        reales = [c for c in cat if not c.id.startswith("DEMO-")] or cat
        self._rellenar(self.f_color, tx("mz_todos_colores"), sorted({col for c in reales for col in c.colores}),
                       lambda x: tx("color_" + x))
        self._rellenar(self.f_tipo, tx("mz_todos_tipos"), [PERSONAJE, EVENTO, COMPANERO, CASO], lambda x: tx("tipo_" + x))
        self._rellenar(self.f_nivel, tx("mz_todos_niveles"), sorted({c.nivel for c in reales if c.tipo in (PERSONAJE, EVENTO)}),
                       lambda x: tx("nivel_n", n=x))
        self._rellenar(self.f_paquete, tx("mz_todas_colecciones"), sorted({c.paquete or "DEMO" for c in cat}), str)
        self.filtrar()
        self._pintar_mazo()

    def _rellenar(self, cb: QComboBox, todos: str, valores: list, etiqueta):
        actual = cb.currentData()
        cb.blockSignals(True)
        cb.clear()
        cb.addItem(todos, None)
        for v in valores:
            cb.addItem(etiqueta(v), v)
        i = cb.findData(actual)
        cb.setCurrentIndex(i if i >= 0 else 0)
        cb.blockSignals(False)

    def _icono(self, d: CartaDef) -> QIcon:
        if d.id not in self._iconos:
            pix = self.v.imagenes.mostrar(d, self.idioma)
            if pix is None or pix.isNull():
                pix = QPixmap(86, 120)
                pix.fill(QColor(COLORES_HEX.get(d.colores[0] if d.colores else "", "#555")))
                p = QPainter(pix)
                p.setPen(QColor("white"))
                p.drawText(pix.rect().adjusted(4, 4, -4, -4), Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap,
                           f"{d.nivel if d.tipo in (PERSONAJE, EVENTO) else d.tipo[:4].upper()}\n{d.nombre_en(self.idioma)}")
                p.end()
            else:
                pix = pix.scaled(86, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._iconos[d.id] = QIcon(pix)
        return self._iconos[d.id]

    def filtrar(self):
        texto = self.buscar.text().strip().lower()
        col, tipo, niv, paq = (cb.currentData() for cb in (self.f_color, self.f_tipo, self.f_nivel, self.f_paquete))
        res = []
        for d in self.v.catalogo.todas():
            if col and col not in d.colores:
                continue
            if tipo and d.tipo != tipo:
                continue
            if niv is not None and (d.nivel != niv or d.tipo not in (PERSONAJE, EVENTO)):
                continue
            if paq and (d.paquete or "DEMO") != paq:
                continue
            if texto:
                pajar = " ".join([d.id, d.id_regla, *d.nombre.values(), *d.texto.values(),
                                  *d.rasgos_en(self.idioma), *d.rasgos_ja]).lower()
                if texto not in pajar:
                    continue
            res.append(d)
        res.sort(key=lambda d: (d.paquete or "ZZ", d.id))
        self.lista.clear()
        for d in res[:MAX_RESULTADOS]:
            it = QListWidgetItem(self._icono(d), f"{d.nombre_en(self.idioma)}\n{d.id}")
            it.setData(Qt.UserRole, d)
            it.setToolTip(d.nombre_en(self.idioma))
            self.lista.addItem(it)
        tx = self.v.tx
        self.lbl_resultados.setText(tx("mz_resultados", n=len(res)) +
                                    (" " + tx("mz_afina", m=MAX_RESULTADOS) if len(res) > MAX_RESULTADOS else ""))

    def _actual(self) -> CartaDef | None:
        it = self.lista.currentItem()
        return it.data(Qt.UserRole) if it else None

    def mostrar(self, d: CartaDef | None):
        tx = self.v.tx
        if d is None:
            self.det_img.clear()
            self.det_txt.setText(tx("mz_elige_carta"))
            return
        pix = self.v.imagenes.mostrar(d, self.idioma)
        if pix is not None and not pix.isNull():
            self.det_img.setPixmap(pix.scaled(300, 420, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.det_img.setPixmap(self._icono(d).pixmap(86, 120))
        partes = [f"<b style='font-size:15px'>{d.nombre_en(self.idioma)}</b>",
                  f"<span style='color:{tema.TEXTO_SUAVE}'>{d.id} · ID {d.id_regla} · {d.rareza} · {d.paquete}</span>",
                  f"{tx('tipo_' + d.tipo)} · {', '.join(tx('color_' + c) for c in d.colores)}"]
        if d.tipo in (PERSONAJE, EVENTO):
            partes.append(tx("nivel_n", n=d.nivel) + (f" · AP {d.ap} · LP {d.lp}" if d.tipo == PERSONAJE else ""))
        if d.tipo == COMPANERO:
            partes.append(f"LP {d.lp}")
        if d.tipo == CASO:
            partes.append(tx("mz_nivel_caso", a=d.nivel_caso[0], b=d.nivel_caso[1]))
        if d.rasgos_en(self.idioma):
            partes.append(tx("mz_rasgos") + ": " + ", ".join(d.rasgos_en(self.idioma)))
        texto = d.texto_en(self.idioma)
        if texto:
            partes.append("<br>" + texto.replace("\n", "<br>"))
        if self.idioma not in d.texto and self.idioma != "ja" and d.texto.get("ja") and "es" not in d.texto:
            partes.append(f"<i style='color:{tema.TEXTO_SUAVE}'>{tx('mz_sin_traducir')}</i>")
        self.det_txt.setText("<br>".join(partes))

    # ------------------------------------------------------------ editar el mazo

    def _marcar(self):
        self.cambiado = True
        self.mazo.nombre = self.nombre.text().strip()
        self._pintar_mazo()

    def _copias_regla(self, regla: str) -> int:
        cat = self.v.catalogo.por_id
        return sum(n for cid, n in self.mazo.cartas.items() if cid in cat and cat[cid].id_regla == regla)

    def anadir(self, d: CartaDef | None):
        if d is None:
            return
        tx = self.v.tx
        if d.tipo == COMPANERO:
            self.mazo.companero = d.id
        elif d.tipo == CASO:
            self.mazo.caso = d.id
        else:
            if self.mazo.total() >= 40:
                QMessageBox.information(self, tx("titulo"), tx("mz_lleno"))
                return
            if self._copias_regla(d.id_regla) >= d.limite:
                QMessageBox.information(self, tx("titulo"), tx("mz_limite", n=d.limite))
                return
            self.mazo.cartas[d.id] = self.mazo.cartas.get(d.id, 0) + 1
        self.cambiado = True
        self._pintar_mazo()

    def quitar(self, cid: str):
        n = self.mazo.cartas.get(cid, 0) - 1
        if n <= 0:
            self.mazo.cartas.pop(cid, None)
        else:
            self.mazo.cartas[cid] = n
        self.cambiado = True
        self._pintar_mazo()

    def _pintar_mazo(self):
        tx = self.v.tx
        cat = self.v.catalogo.por_id
        m = self.mazo
        if self.nombre.text() != m.nombre:
            self.nombre.setText(m.nombre)

        def etiqueta(cid, clave):
            d = cat.get(cid)
            return tx(clave) + ": " + (f"{d.nombre_en(self.idioma)} ({cid})" if d else (cid or tx("mz_sin_elegir")))
        self.lbl_comp.setText(etiqueta(m.companero, "companero"))
        self.lbl_caso.setText(etiqueta(m.caso, "caso"))
        filas = sorted(m.cartas.items(), key=lambda kv: (cat[kv[0]].nivel if kv[0] in cat else 99, kv[0]))
        self.tabla.clearContents()
        self.tabla.setRowCount(0)
        self.tabla.setRowCount(len(filas))
        self.tabla.setHorizontalHeaderLabels([tx("col_nivel"), tx("col_carta"), tx("col_copias"), ""])
        for i, (cid, n) in enumerate(filas):
            d = cat.get(cid)
            self.tabla.setItem(i, 0, QTableWidgetItem(str(d.nivel) if d else "?"))
            it = QTableWidgetItem(f"{d.nombre_en(self.idioma)}  ·  {cid}" if d else cid)
            it.setData(Qt.UserRole, cid)
            if d and m.caso in cat and not set(d.colores) <= set(cat[m.caso].colores):
                it.setForeground(QColor(tema.ROJO))
                it.setToolTip(tx("mz_color_no"))
            self.tabla.setItem(i, 1, it)
            self.tabla.setItem(i, 2, QTableWidgetItem(f"×{n}"))
            caja = QWidget()
            bl = QHBoxLayout(caja)
            bl.setContentsMargins(0, 0, 0, 0)
            menos, mas = QToolButton(text="−"), QToolButton(text="+")
            menos.clicked.connect(lambda _=False, c=cid: self.quitar(c))
            mas.clicked.connect(lambda _=False, c=cid: self.anadir(cat.get(c)))
            bl.addWidget(menos)
            bl.addWidget(mas)
            self.tabla.setCellWidget(i, 3, caja)
        self.tabla.resizeColumnToContents(0)
        self.tabla.resizeColumnToContents(2)
        self.tabla.resizeColumnToContents(3)
        total = m.total()
        self.lbl_total.setText(tx("mz_total", n=total) + ("  " + tx("mz_sin_guardar") if self.cambiado else ""))
        self.lbl_total.setStyleSheet(f"font-size:15px;font-weight:bold;color:{tema.ORO if total == 40 else tema.TEXTO};")
        curva = {}
        for cid, n in m.cartas.items():
            if cid in cat:
                curva[cat[cid].nivel] = curva.get(cat[cid].nivel, 0) + n
        self.lbl_curva.setText(tx("mz_curva") + "  " + "   ".join(f"N{k}×{v}" for k, v in sorted(curva.items())))
        errores = m.validar(self.v.catalogo)
        if m.caso in cat:
            fuera = sum(n for cid, n in m.cartas.items() if cid in cat and not set(cat[cid].colores) <= set(cat[m.caso].colores))
            if fuera:
                errores.append(tx("mz_aviso_color", n=fuera))
        if errores:
            self.lbl_errores.setText("<br>".join(f"• {e}" for e in errores))
            self.lbl_errores.setStyleSheet(f"color:{tema.ROJO};")
        else:
            self.lbl_errores.setText("✓ " + tx("mz_valido"))
            self.lbl_errores.setStyleSheet(f"color:{tema.ORO};")

    # ------------------------------------------------------------ archivos

    def _seguir_sin_guardar(self) -> bool:
        if not self.cambiado or self.mazo.total() == 0 and not self.mazo.companero:
            return True
        return QMessageBox.question(self, self.v.tx("titulo"), self.v.tx("mz_descartar")) == QMessageBox.Yes

    def _volver(self):
        if self._seguir_sin_guardar():
            self.cambiado = False
            self.v.ir_a_menu()

    def cargar(self, m: Mazo, ruta: Path | None):
        self.mazo, self.ruta, self.cambiado = m, ruta, False
        self._pintar_mazo()

    def nuevo(self):
        if self._seguir_sin_guardar():
            self.cargar(Mazo("", "", "", {}), None)

    def abrir(self):
        if not self._seguir_sin_guardar():
            return
        dlg = DialogoElegirMazo(self.v, solo_validos=False)
        if dlg.exec() == QDialog.Accepted and dlg.elegido:
            ruta, m = dlg.elegido
            propio = ruta.parent.resolve() == self.carpeta_mazos().resolve()
            self.cargar(m, ruta if propio else None)   # los oficiales se guardan como copia

    def guardar(self):
        tx = self.v.tx
        if not self.mazo.nombre:
            nombre, ok = QInputDialog.getText(self, tx("titulo"), tx("mz_nombre"))
            if not ok or not nombre.strip():
                return
            self.mazo.nombre = nombre.strip()
        ruta = self.ruta or self.carpeta_mazos() / nombre_archivo(self.mazo.nombre)
        if self.ruta is None and ruta.exists():
            if QMessageBox.question(self, tx("titulo"), tx("mz_sobrescribir", n=self.mazo.nombre)) != QMessageBox.Yes:
                return
        self.mazo.guardar(ruta)
        self.ruta, self.cambiado = ruta, False
        self._pintar_mazo()

    def importar(self):
        tx = self.v.tx
        dlg = QDialog(self)
        dlg.setWindowTitle(tx("mz_importar"))
        dlg.resize(460, 420)
        l = QVBoxLayout(dlg)
        info = QLabel(tx("mz_importar_ayuda"))
        info.setWordWrap(True)
        l.addWidget(info)
        ed = QPlainTextEdit()
        l.addWidget(ed, 1)
        fila = QHBoxLayout()
        b_arch = QPushButton(tx("mz_desde_archivo"))
        fila.addWidget(b_arch)
        fila.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        fila.addWidget(bb)
        l.addLayout(fila)
        b_arch.clicked.connect(lambda: self._leer_archivo(ed))
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.Accepted or not self._seguir_sin_guardar():
            return
        m, avisos = texto_a_mazo(ed.toPlainText(), self.v.catalogo.por_id)
        self.cargar(m, None)
        self.cambiado = True
        self._pintar_mazo()
        if avisos:
            QMessageBox.information(self, tx("titulo"), "\n".join(avisos[:20]))

    def _leer_archivo(self, ed: QPlainTextEdit):
        ruta, _ = QFileDialog.getOpenFileName(self, self.v.tx("mz_importar"), "", "Mazos (*.txt *.json)")
        if not ruta:
            return
        if ruta.endswith(".json"):
            ed.setPlainText(mazo_a_texto(Mazo.cargar(ruta)))
        else:
            ed.setPlainText(Path(ruta).read_text(encoding="utf-8-sig"))

    def exportar(self):
        tx = self.v.tx
        texto = mazo_a_texto(self.mazo)
        dlg = QDialog(self)
        dlg.setWindowTitle(tx("mz_exportar"))
        dlg.resize(420, 420)
        l = QVBoxLayout(dlg)
        ed = QPlainTextEdit(texto)
        ed.setReadOnly(True)
        l.addWidget(ed, 1)
        fila = QHBoxLayout()
        b_copiar = QPushButton(tx("mz_copiar"))
        b_copiar.clicked.connect(lambda: (ed.selectAll(), ed.copy()))
        b_arch = QPushButton(tx("mz_a_archivo"))
        b_arch.clicked.connect(lambda: self._escribir_archivo(texto))
        cerrar = QPushButton(tx("cerrar"))
        cerrar.clicked.connect(dlg.accept)
        for b in (b_copiar, b_arch):
            fila.addWidget(b)
        fila.addStretch()
        fila.addWidget(cerrar)
        l.addLayout(fila)
        dlg.exec()

    def _escribir_archivo(self, texto: str):
        ruta, _ = QFileDialog.getSaveFileName(self, self.v.tx("mz_exportar"),
                                              nombre_archivo(self.mazo.nombre or "mazo").replace(".json", ".txt"),
                                              "Texto (*.txt)")
        if ruta:
            Path(ruta).write_text(texto, encoding="utf-8")

    def borrar(self):
        tx = self.v.tx
        if not self.ruta:
            self.nuevo()
            return
        if QMessageBox.question(self, tx("titulo"), tx("mz_confirmar_borrar", n=self.mazo.nombre)) == QMessageBox.Yes:
            self.ruta.unlink(missing_ok=True)
            self.cargar(Mazo("", "", "", {}), None)


class DialogoElegirMazo(QDialog):
    """Lista los mazos oficiales (datos/mazos) y los del usuario (mazos/)."""

    def __init__(self, ventana, solo_validos=True, titulo=None):
        super().__init__(ventana)
        self.v, self.elegido = ventana, None
        tx = ventana.tx
        self.setWindowTitle(titulo or tx("mz_abrir"))
        self.resize(560, 460)
        l = QVBoxLayout(self)
        self.lista = QListWidget()
        l.addWidget(self.lista, 1)
        for ruta, m, errores in ventana.mazos_disponibles():
            oficial = ruta.parent.name == "mazos" and ruta.parent.parent.name == "datos"
            etiqueta = f"{m.nombre}   {'· ' + tx('mz_oficial') if oficial else ''}"
            if errores:
                etiqueta += f"\n   {errores[0]}"
            it = QListWidgetItem(etiqueta)
            it.setData(Qt.UserRole, (ruta, m))
            if errores and solo_validos:
                it.setFlags(Qt.NoItemFlags)
            self.lista.addItem(it)
        self.lista.itemDoubleClicked.connect(lambda _: self._ok())
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        l.addWidget(bb)

    def _ok(self):
        it = self.lista.currentItem()
        if it and it.flags() & Qt.ItemIsEnabled:
            self.elegido = it.data(Qt.UserRole)
            self.accept()
