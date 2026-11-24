"""Aspecto visual: tonos de despacho de detective (azul noche, papel y dorado)."""

FONDO = "#151b27"
PANEL = "#1f2838"
PANEL_2 = "#283347"
BORDE = "#3a4760"
TEXTO = "#ece6d8"
TEXTO_SUAVE = "#a9b1c2"
ORO = "#d9a845"
ORO_OSCURO = "#a87d27"
ROJO = "#c0533f"

QSS = f"""
QMainWindow, QDialog, QWidget#pagina {{ background:{FONDO}; }}
QWidget {{ color:{TEXTO}; font-size:13px; }}
QLabel {{ background:transparent; }}
QMenuBar {{ background:{PANEL}; color:{TEXTO}; border-bottom:1px solid {BORDE}; }}
QMenuBar::item:selected {{ background:{PANEL_2}; }}
QMenu {{ background:{PANEL}; color:{TEXTO}; border:1px solid {BORDE}; }}
QMenu::item:selected {{ background:{ORO_OSCURO}; color:white; }}
QMenu::item:disabled {{ color:#6c7487; }}
QPushButton, QToolButton {{
    background:{PANEL_2}; color:{TEXTO}; border:1px solid {BORDE}; border-radius:6px; padding:6px 12px;
}}
QPushButton:hover, QToolButton:hover {{ border-color:{ORO}; }}
QPushButton:pressed {{ background:{ORO_OSCURO}; }}
QPushButton:disabled, QToolButton:disabled {{ color:#6c7487; background:#1b2231; border-color:#2b3447; }}
QPushButton#primario {{ background:{ORO}; color:#1a1408; font-weight:bold; border-color:{ORO}; }}
QPushButton#primario:hover {{ background:#e8bb5c; }}
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit, QListWidget, QTableWidget {{
    background:{PANEL}; color:{TEXTO}; border:1px solid {BORDE}; border-radius:6px; padding:4px;
    selection-background-color:{ORO_OSCURO}; selection-color:white;
}}
QComboBox QAbstractItemView {{ background:{PANEL}; color:{TEXTO}; selection-background-color:{ORO_OSCURO}; }}
QHeaderView::section {{ background:{PANEL_2}; color:{TEXTO}; border:none; padding:5px; }}
QTableWidget {{ gridline-color:{BORDE}; }}
QGroupBox {{ color:{TEXTO}; }}
QScrollArea {{ background:transparent; border:none; }}
QScrollArea > QWidget > QWidget {{ background:transparent; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background:{FONDO}; width:10px; height:10px; }}
QScrollBar::handle {{ background:{BORDE}; border-radius:5px; min-height:24px; min-width:24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QProgressBar {{ background:{PANEL}; border:1px solid {BORDE}; border-radius:6px; text-align:center; color:{TEXTO}; }}
QProgressBar::chunk {{ background:{ORO}; border-radius:5px; }}
QCheckBox::indicator, QTableView::indicator {{ width:16px; height:16px; border:1px solid {TEXTO_SUAVE};
    border-radius:3px; background:{PANEL}; }}
QCheckBox::indicator:checked, QTableView::indicator:checked {{ background:{ORO}; border-color:{ORO}; }}
QTabWidget::pane {{ border:1px solid {BORDE}; border-radius:6px; top:-1px; }}
QTabBar::tab {{ background:{PANEL}; color:{TEXTO_SUAVE}; padding:8px 16px; border:1px solid {BORDE};
               border-bottom:none; border-top-left-radius:6px; border-top-right-radius:6px; }}
QTabBar::tab:selected {{ background:{PANEL_2}; color:{TEXTO}; }}
QToolTip {{ background:{PANEL}; color:{TEXTO}; border:1px solid {ORO}; padding:6px; }}
QSplitter::handle {{ background:{FONDO}; }}
"""

TITULO = f"font-size:26px;font-weight:bold;color:{ORO};"
SUBTITULO = f"color:{TEXTO_SUAVE};"
