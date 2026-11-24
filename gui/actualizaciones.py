"""Aviso de actualizaciones, descarga con progreso e importación de datos antiguos."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout)

from core import actualizador
from core import rutas as R
from core.version import REPO, VERSION


class _Hilo(QThread):
    hecho = Signal(object)
    fallo = Signal(str)
    progreso = Signal(float)

    def __init__(self, fn):
        super().__init__()
        self.fn, self.parar = fn, False

    def run(self):
        try:
            self.hecho.emit(self.fn(self))
        except Exception as e:  # se muestra al usuario
            self.fallo.emit(str(e))


class Actualizaciones:
    def __init__(self, ventana):
        self.v = ventana
        self.hilo: _Hilo | None = None

    @property
    def repo(self) -> str:
        cp = self.v.cfg.cp
        return (cp["actualizaciones"].get("repo", "") if "actualizaciones" in cp else "") or REPO

    def _cfg(self, clave, valor=None):
        cp = self.v.cfg.cp
        if "actualizaciones" not in cp:
            cp["actualizaciones"] = {}
        if valor is None:
            return cp["actualizaciones"].get(clave, "")
        cp["actualizaciones"][clave] = valor
        self.v.cfg.guardar()

    # ------------------------------------------------------------ buscar
    def al_arrancar(self):
        """Comprobación silenciosa unos segundos después de abrir la app."""
        if self.repo and actualizador.instalada() and self._cfg("automatico") != "no":
            QTimer.singleShot(3000, lambda: self.buscar(silencioso=True))

    def buscar(self, silencioso=False):
        tx = self.v.tx
        if not self.repo:
            if not silencioso:
                QMessageBox.information(self.v, tx("titulo"), tx("act_sin_repo"))
            return
        if self.hilo and self.hilo.isRunning():
            return
        self.hilo = _Hilo(lambda h: actualizador.buscar(self.repo))
        self.hilo.hecho.connect(lambda n: self._resultado(n, silencioso))
        self.hilo.fallo.connect(lambda e: None if silencioso else
                                QMessageBox.warning(self.v, tx("titulo"), tx("act_error", e=e)))
        self.hilo.start()

    def _resultado(self, n, silencioso):
        tx = self.v.tx
        if n is None:
            if not silencioso:
                QMessageBox.information(self.v, tx("titulo"), tx("act_al_dia", v=VERSION))
            return
        if silencioso and self._cfg("omitir") == n.version:
            return
        self._ofrecer(n)

    def _ofrecer(self, n):
        tx = self.v.tx
        dlg = QDialog(self.v)
        dlg.setWindowTitle(tx("act_titulo"))
        dlg.resize(520, 400)
        l = QVBoxLayout(dlg)
        cab = QLabel(tx("act_hay", nueva=n.version, actual=VERSION))
        cab.setStyleSheet("font-size:16px;font-weight:bold;color:#d9a845;")
        l.addWidget(cab)
        l.addWidget(QLabel(tx("act_notas")))
        notas = QPlainTextEdit(n.notas or tx("act_sin_notas"))
        notas.setReadOnly(True)
        l.addWidget(notas, 1)
        aviso = QLabel(tx("act_datos_seguros"))
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color:#a9b1c2;")
        l.addWidget(aviso)
        barra = QProgressBar()
        barra.setRange(0, 1000)
        barra.hide()
        l.addWidget(barra)
        fila = QHBoxLayout()
        omitir = QPushButton(tx("act_omitir"))
        luego = QPushButton(tx("act_luego"))
        ahora = QPushButton(tx("act_ahora"))
        ahora.setObjectName("primario")
        fila.addWidget(omitir)
        fila.addStretch()
        fila.addWidget(luego)
        fila.addWidget(ahora)
        l.addLayout(fila)
        omitir.clicked.connect(lambda: (self._cfg("omitir", n.version), dlg.reject()))
        luego.clicked.connect(dlg.reject)

        def instalar():
            if not actualizador.instalada():
                QDesktopServices.openUrl(QUrl(n.url_instalador))
                dlg.accept()
                return
            for b in (omitir, luego, ahora):
                b.setEnabled(False)
            barra.show()
            self.hilo = _Hilo(lambda h: actualizador.descargar(n, h.progreso.emit, lambda: h.parar))
            self.hilo.progreso.connect(lambda f: barra.setValue(int(f * 1000)))
            self.hilo.fallo.connect(lambda e: (QMessageBox.warning(dlg, tx("titulo"), tx("act_error", e=e)),
                                               [b.setEnabled(True) for b in (omitir, luego, ahora)]))
            self.hilo.hecho.connect(lambda ruta: self._instalar(ruta, dlg))
            self.hilo.start()
        ahora.clicked.connect(instalar)
        dlg.exec()

    def _instalar(self, ruta: Path, dlg):
        tx = self.v.tx
        if self.v.modo and self.v.motor and self.v.motor.p.ganador is None:
            if QMessageBox.question(dlg, tx("titulo"), tx("act_partida_en_curso")) != QMessageBox.Yes:
                dlg.reject()
                return
        try:
            actualizador.lanzar_instalador(ruta)
        except actualizador.ActualizacionError as e:
            QMessageBox.warning(dlg, tx("titulo"), str(e))
            return
        dlg.accept()
        self.v.close()
        QApplication.quit()

    # ------------------------------------------------------------ datos antiguos
    def ofrecer_importar_si_nuevo(self):
        """Primera vez con la app instalada: ofrece traer los datos de la versión en carpeta."""
        r = self.v.rutas
        if r.usuario == r.programa or self.v.perfiles.perfiles or self._cfg("importacion_preguntada"):
            return
        self._cfg("importacion_preguntada", "si")
        tx = self.v.tx
        if QMessageBox.question(self.v, tx("titulo"), tx("imp_pregunta")) == QMessageBox.Yes:
            self.importar()

    def importar(self):
        tx = self.v.tx
        carpeta = QFileDialog.getExistingDirectory(self.v, tx("imp_elegir"))
        if not carpeta:
            return
        if not R.parece_version_anterior(Path(carpeta)):
            QMessageBox.information(self.v, tx("titulo"), tx("imp_no_parece"))
            return
        copiados = R.importar(Path(carpeta), self.v.rutas)
        QMessageBox.information(self.v, tx("titulo"), tx("imp_hecho", n=len(copiados), lista=", ".join(copiados))
                                + "\n\n" + tx("imp_reinicia"))

    def acerca_de(self):
        tx = self.v.tx
        caja = QMessageBox(self.v)
        caja.setWindowTitle(tx("acerca"))
        caja.setText(tx("acerca_texto", v=VERSION, datos=str(self.v.rutas.usuario),
                        repo=self.repo or tx("act_sin_repo_corto")))
        abrir = caja.addButton(tx("abrir_datos"), QMessageBox.ActionRole)
        caja.addButton(QMessageBox.Close)
        caja.exec()
        if caja.clickedButton() is abrir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.v.rutas.usuario)))
