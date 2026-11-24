"""Pantalla «Cartas y descargas»: colecciones oficiales, imágenes locales y traducción con DeepL."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMessageBox, QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from datos import descarga
from datos.traduccion import DEEPL_IDIOMAS, ClienteDeepL, TraduccionError, Traductor
from . import tema

MAZOS_EJEMPLO = ("CT-D10", "CT-D11")
NOMBRES_IDIOMA = {"es": "Castellano", "ca": "Català", "en": "English", "fr": "Français", "it": "Italiano",
                  "pt": "Português", "de": "Deutsch"}


class Tarea(QThread):
    """Ejecuta una función larga fuera de la interfaz y avisa del progreso."""
    progreso = Signal(str, float)
    terminado = Signal(object)
    fallo = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.parar = False

    def run(self):
        try:
            r = self.fn(lambda t, f: self.progreso.emit(t, f), lambda: self.parar)
            self.terminado.emit(r)
        except Exception as e:  # se muestra al usuario
            self.fallo.emit(str(e))


class PaginaContenido(QWidget):
    def __init__(self, ventana):
        super().__init__()
        self.v = ventana
        self.tarea: Tarea | None = None
        self.paquetes_web: list[tuple[str, str]] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 24, 40, 20)
        cab = QHBoxLayout()
        self.titulo = QLabel()
        self.titulo.setStyleSheet(tema.TITULO)
        cab.addWidget(self.titulo)
        cab.addStretch()
        self.btn_volver = QPushButton()
        self.btn_volver.clicked.connect(ventana.ir_a_menu)
        cab.addWidget(self.btn_volver)
        lay.addLayout(cab)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self._tab_colecciones()
        self._tab_traduccion()
        # barra de progreso común
        fila = QHBoxLayout()
        self.barra = QProgressBar()
        self.barra.setRange(0, 1000)
        self.estado = QLabel()
        self.estado.setStyleSheet(tema.SUBTITULO)
        self.btn_parar = QPushButton()
        self.btn_parar.clicked.connect(self._parar)
        fila.addWidget(self.estado, 1)
        fila.addWidget(self.barra, 1)
        fila.addWidget(self.btn_parar)
        lay.addLayout(fila)
        self._ocupado(False)

    # ------------------------------------------------------------ pestañas

    def _tab_colecciones(self):
        w = QWidget()
        l = QVBoxLayout(w)
        self.lbl_intro = QLabel()
        self.lbl_intro.setWordWrap(True)
        self.lbl_intro.setStyleSheet(tema.SUBTITULO)
        l.addWidget(self.lbl_intro)
        fila = QHBoxLayout()
        self.btn_ejemplo = QPushButton()
        self.btn_ejemplo.setObjectName("primario")
        self.btn_ejemplo.clicked.connect(lambda: self.descargar(list(MAZOS_EJEMPLO)))
        self.btn_lista = QPushButton()
        self.btn_lista.clicked.connect(self.actualizar_lista)
        fila.addWidget(self.btn_ejemplo)
        fila.addWidget(self.btn_lista)
        fila.addStretch()
        l.addLayout(fila)
        self.tabla = QTableWidget(0, 4)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.setSelectionMode(QTableWidget.NoSelection)
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        l.addWidget(self.tabla, 1)
        fila2 = QHBoxLayout()
        self.chk_imagenes = QCheckBox()
        self.chk_imagenes.setChecked(True)
        self.lbl_carpeta = QLabel()
        self.lbl_carpeta.setStyleSheet(tema.SUBTITULO)
        self.btn_carpeta = QPushButton()
        self.btn_carpeta.clicked.connect(self._elegir_carpeta)
        self.btn_descargar = QPushButton()
        self.btn_descargar.setObjectName("primario")
        self.btn_descargar.clicked.connect(lambda: self.descargar(self._marcados()))
        fila2.addWidget(self.chk_imagenes)
        fila2.addWidget(self.lbl_carpeta, 1)
        fila2.addWidget(self.btn_carpeta)
        fila2.addWidget(self.btn_descargar)
        l.addLayout(fila2)
        self.tabs.addTab(w, "")

    def _tab_traduccion(self):
        w = QWidget()
        l = QVBoxLayout(w)
        self.lbl_trad = QLabel()
        self.lbl_trad.setWordWrap(True)
        self.lbl_trad.setStyleSheet(tema.SUBTITULO)
        l.addWidget(self.lbl_trad)
        self.rejilla = QGridLayout()
        l.addLayout(self.rejilla)
        self.filas_idioma = {}
        idiomas = ["general"] + [i for i in DEEPL_IDIOMAS]
        for r, idi in enumerate(idiomas):
            nombre = QLabel()
            clave = QLineEdit()
            clave.setEchoMode(QLineEdit.Password)
            clave.setText(self.v.cfg.clave_deepl(idi, exacta=True))
            probar = QPushButton()
            probar.clicked.connect(lambda _=False, i=idi: self.probar(i))
            info = QLabel()
            info.setStyleSheet(tema.SUBTITULO)
            traducir = QPushButton()
            traducir.setObjectName("primario")
            traducir.clicked.connect(lambda _=False, i=idi: self.traducir(i))
            traducir.setVisible(idi != "general")
            for c, wdg in enumerate((nombre, clave, probar, traducir, info)):
                self.rejilla.addWidget(wdg, r, c)
            self.filas_idioma[idi] = (nombre, clave, probar, traducir, info)
        self.rejilla.setColumnStretch(1, 2)
        self.rejilla.setColumnStretch(4, 3)
        fila = QHBoxLayout()
        self.btn_guardar_claves = QPushButton()
        self.btn_guardar_claves.clicked.connect(self.guardar_claves)
        self.chk_ver = QCheckBox()
        self.chk_ver.toggled.connect(lambda v: [f[1].setEchoMode(QLineEdit.Normal if v else QLineEdit.Password)
                                                for f in self.filas_idioma.values()])
        fila.addWidget(self.chk_ver)
        self.btn_revisar = QPushButton()
        self.btn_revisar.clicked.connect(self.v.ir_a_traducciones)
        fila.addWidget(self.btn_revisar)
        fila.addStretch()
        fila.addWidget(self.btn_guardar_claves)
        l.addLayout(fila)
        l.addStretch()
        self.tabs.addTab(w, "")

    # ------------------------------------------------------------ refresco

    def refrescar(self):
        tx = self.v.tx
        self.titulo.setText(tx("cont_titulo"))
        self.btn_volver.setText(tx("volver_menu_corto"))
        self.tabs.setTabText(0, tx("cont_colecciones"))
        self.tabs.setTabText(1, tx("cont_traduccion"))
        self.lbl_intro.setText(tx("cont_intro"))
        self.btn_ejemplo.setText(tx("cont_ejemplo"))
        self.btn_lista.setText(tx("cont_actualizar"))
        self.chk_imagenes.setText(tx("cont_con_imagenes"))
        self.lbl_carpeta.setText(tx("cont_carpeta", carpeta=self.v.carpeta_imagenes()))
        self.btn_carpeta.setText(tx("cambiar"))
        self.btn_descargar.setText(tx("cont_descargar"))
        self.btn_parar.setText(tx("detener"))
        self.lbl_trad.setText(tx("trad_intro"))
        self.btn_guardar_claves.setText(tx("trad_guardar"))
        self.chk_ver.setText(tx("trad_ver_claves"))
        self.btn_revisar.setText(tx("trad_revisar"))
        cartas = self.v.catalogo_local.cartas
        for idi, (nombre, clave, probar, traducir, info) in self.filas_idioma.items():
            nombre.setText(tx("trad_clave_general") if idi == "general" else NOMBRES_IDIOMA.get(idi, idi))
            clave.setPlaceholderText(tx("trad_usa_general") if idi != "general" else tx("trad_clave_ph"))
            probar.setText(tx("trad_probar"))
            traducir.setText(tx("trad_traducir"))
            if idi != "general" and cartas:
                try:
                    pend = self.v.traductor(idi, None).pendiente(cartas)
                    info.setText(tx("trad_pendiente", n=f"{pend:,}".replace(",", ".")) if pend else tx("trad_completo"))
                except Exception:
                    info.setText("")
            elif idi != "general":
                info.setText(tx("trad_sin_cartas"))
        self._llenar_tabla()

    def _llenar_tabla(self):
        tx = self.v.tx
        locales = self.v.catalogo_local.paquetes()
        lista = self.paquetes_web or [(c, d["nombre"]) for c, d in locales.items()]
        if not lista:
            lista = [(c, c) for c in MAZOS_EJEMPLO]
        self.tabla.setHorizontalHeaderLabels(["", tx("col_coleccion"), tx("col_cartas"), tx("col_descargado")])
        self.tabla.setRowCount(len(lista))
        for i, (cod, nombre) in enumerate(lista):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Unchecked)
            chk.setData(Qt.UserRole, (cod, nombre))
            self.tabla.setItem(i, 0, chk)
            self.tabla.setItem(i, 1, QTableWidgetItem(nombre if nombre.startswith(cod) else f"{cod} {nombre}"))
            loc = locales.get(cod)
            self.tabla.setItem(i, 2, QTableWidgetItem(str(loc["cartas"]) if loc else "—"))
            self.tabla.setItem(i, 3, QTableWidgetItem(loc["descargado"] if loc else tx("no")))
        self.tabla.resizeColumnToContents(0)

    def _marcados(self) -> list:
        out = []
        for i in range(self.tabla.rowCount()):
            it = self.tabla.item(i, 0)
            if it.checkState() == Qt.Checked:
                out.append(it.data(Qt.UserRole)[0])
        return out

    # ------------------------------------------------------------ tareas

    def _ocupado(self, si: bool):
        for b in (self.btn_ejemplo, self.btn_lista, self.btn_descargar, self.btn_carpeta, self.btn_guardar_claves):
            b.setEnabled(not si)
        for f in self.filas_idioma.values():
            f[2].setEnabled(not si)
            f[3].setEnabled(not si)
        self.btn_parar.setVisible(si)
        self.barra.setVisible(si)

    def _lanzar(self, fn, al_terminar):
        self.tarea = Tarea(fn)
        self.tarea.progreso.connect(lambda t, f: (self.estado.setText(t), self.barra.setValue(int(f * 1000))))
        self.tarea.terminado.connect(lambda r: (self._ocupado(False), al_terminar(r)))
        self.tarea.fallo.connect(lambda e: (self._ocupado(False), self.estado.setText(""),
                                            QMessageBox.warning(self, self.v.tx("titulo"), e)))
        self._ocupado(True)
        self.barra.setValue(0)
        self.tarea.start()

    def _parar(self):
        if self.tarea:
            self.tarea.parar = True

    def actualizar_lista(self):
        def fn(prog, parar):
            prog(self.v.tx("cont_consultando"), 0.5)
            return descarga.listar_paquetes()

        def fin(r):
            self.paquetes_web = r
            self.estado.setText(self.v.tx("cont_n_colecciones", n=len(r)))
            self._llenar_tabla()
        self._lanzar(fn, fin)

    def descargar(self, codigos: list[str]):
        if not codigos:
            QMessageBox.information(self, self.v.tx("titulo"), self.v.tx("cont_marca_alguna"))
            return
        con_img = self.chk_imagenes.isChecked()
        carpeta = Path(self.v.carpeta_imagenes())
        nombres = dict(self.paquetes_web)
        cat = self.v.catalogo_local

        def fn(prog, parar):
            nuevas_total = []
            for i, cod in enumerate(codigos):
                if parar():
                    break
                prog(f"{cod}…", i / len(codigos))
                cartas = [descarga.convertir(c) for c in descarga.descargar_paquete(cod)]
                cat.integrar(cod, nombres.get(cod, cod), cartas)
                cat.guardar()
                nuevas_total += cartas
            if con_img and not parar():
                descarga.descargar_imagenes(nuevas_total, carpeta, prog, parar)
            return len(nuevas_total)

        def fin(n):
            self.estado.setText(self.v.tx("cont_hecho", n=n))
            self.v.recargar_catalogo()
            self.refrescar()
        self._lanzar(fn, fin)

    def _elegir_carpeta(self):
        c = QFileDialog.getExistingDirectory(self, self.v.tx("carpeta_imagenes"), self.v.carpeta_imagenes())
        if c:
            self.v.cfg.g["carpeta_imagenes"] = c
            self.v.cfg.guardar()
            self.v.imagenes.cargar(c)
            self.refrescar()

    # ------------------------------------------------------------ DeepL

    def guardar_claves(self):
        for idi, fila in self.filas_idioma.items():
            self.v.cfg.poner_clave_deepl(idi, fila[1].text().strip())
        self.v.cfg.guardar()
        self.estado.setText(self.v.tx("trad_guardadas"))

    def _clave(self, idi: str) -> str:
        propia = self.filas_idioma[idi][1].text().strip()
        return propia or self.filas_idioma["general"][1].text().strip()

    def probar(self, idi: str):
        clave = self._clave(idi)
        destino = DEEPL_IDIOMAS.get(idi)

        def fn(prog, parar):
            cli = ClienteDeepL(clave)
            usado, limite = cli.uso()
            soporta = None
            if destino:
                soportados = cli.idiomas_destino()
                soporta = destino.upper() in soportados or destino.split("-")[0] in {s.split("-")[0] for s in soportados}
            return usado, limite, soporta

        def fin(r):
            usado, limite, soporta = r
            texto = self.v.tx("trad_uso", usado=f"{usado:,}".replace(",", "."), limite=f"{limite:,}".replace(",", "."))
            if soporta is False:
                texto += " · " + self.v.tx("trad_no_soporta")
            self.filas_idioma[idi][4].setText(texto)
        self._lanzar(fn, fin)

    def traducir(self, idi: str):
        clave = self._clave(idi)
        if not clave:
            QMessageBox.information(self, self.v.tx("titulo"), self.v.tx("trad_falta_clave"))
            return
        cat = self.v.catalogo_local
        if not cat.cartas:
            QMessageBox.information(self, self.v.tx("titulo"), self.v.tx("trad_sin_cartas"))
            return
        try:
            pend = self.v.traductor(idi, None).pendiente(cat.cartas)
        except TraduccionError as e:
            QMessageBox.warning(self, self.v.tx("titulo"), str(e))
            return
        if pend == 0:
            self.v.traductor(idi, None).aplicar(cat.cartas)
            cat.guardar()
            self.v.recargar_catalogo()
            self.refrescar()
            return
        if QMessageBox.question(self, self.v.tx("titulo"),
                                self.v.tx("trad_confirmar", n=f"{pend:,}".replace(",", "."),
                                          idioma=NOMBRES_IDIOMA.get(idi, idi))) != QMessageBox.Yes:
            return

        def fn(prog, parar):
            tr = self.v.traductor(idi, ClienteDeepL(clave))
            completo = tr.traducir_catalogo(cat.cartas, prog, parar)
            cat.guardar()
            return completo, tr.enviados

        def fin(r):
            completo, enviados = r
            self.estado.setText(self.v.tx("trad_hecho" if completo else "trad_parcial",
                                          n=f"{enviados:,}".replace(",", ".")))
            self.v.recargar_catalogo()
            self.refrescar()
        self._lanzar(fn, fin)
