"""SEGMENTO: HOJA DE ESTILOS COMPARTIDA
Paleta unica de toda la interfaz: fondo neutro en cuatro tonos + un solo
color de acento (azul). Los otros tres colores existen solo por su
significado, nunca de adorno: verde = conectado, ambar = algo que revisar,
rojo = parada de emergencia.
"""

# SEGMENTO: PALETA -----------------------------------------------------
# Cuatro tonos de fondo, del mas oscuro al mas claro, mas dos de texto.
FONDO = "#14161b"
PANEL = "#1b1e25"
ELEVADO = "#20242c"
BORDE = "#2b303a"
BORDE_CLARO = "#3a4150"
TEXTO = "#e6e8ec"
TEXTO_TENUE = "#8a90a0"

ACENTO = "#5b8fd6"
ACENTO_CLARO = "#6f9fe0"
VERDE_CONECTADO = "#4fd18f"
AMBAR_ATENCION = "#d9a05b"
ROJO_EMERGENCIA = "#c0392b"

HOJA_DE_ESTILOS = f"""
QWidget {{ background-color: {FONDO}; color: {TEXTO}; font-family: 'Segoe UI', sans-serif; font-size: 13px; }}
QMainWindow {{ background-color: {FONDO}; }}

QMenuBar {{ background-color: {PANEL}; color: {TEXTO}; border-bottom: 1px solid {BORDE}; }}
QMenuBar::item:selected {{ background-color: {ELEVADO}; }}
QMenu {{ background-color: {PANEL}; color: {TEXTO}; border: 1px solid {BORDE}; }}
QMenu::item:selected {{ background-color: {ELEVADO}; }}

QGroupBox {{ border: 1px solid {BORDE}; border-radius: 6px; margin-top: 14px; background-color: {PANEL}; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {TEXTO_TENUE}; }}

QTabWidget::pane {{ border: 1px solid {BORDE}; border-radius: 6px; top: -1px; }}
QTabBar::tab {{ background: {PANEL}; color: {TEXTO_TENUE}; padding: 8px 16px; border: 1px solid {BORDE}; border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {ELEVADO}; color: {TEXTO}; }}

QPushButton {{ background-color: {ELEVADO}; color: {TEXTO}; border: 1px solid {BORDE}; border-radius: 5px; padding: 6px 14px; }}
QPushButton:hover {{ background-color: #262b35; border-color: {BORDE_CLARO}; }}
QPushButton:pressed {{ background-color: {PANEL}; }}
QPushButton:disabled {{ color: #565c68; background-color: {PANEL}; }}

QPushButton#botonPrimario {{ background-color: {ACENTO}; color: #0d1420; border: none; font-weight: 600; }}
QPushButton#botonPrimario:hover {{ background-color: {ACENTO_CLARO}; }}
QPushButton#botonPrimario:disabled {{ background-color: #2f3d51; color: #6a7686; }}

QPushButton#botonEmergencia {{ background-color: {ROJO_EMERGENCIA}; color: white; font-weight: 700; border: none; padding: 8px 18px; }}
QPushButton#botonEmergencia:hover {{ background-color: #d94632; }}
QPushButton#botonEmergencia:disabled {{ background-color: #3a2a28; color: #8a6a66; }}

QLabel#estadoConectado {{ color: {VERDE_CONECTADO}; font-weight: 600; }}
QLabel#estadoDesconectado {{ color: {ROJO_EMERGENCIA}; font-weight: 600; }}
QLabel#textoSecundario {{ color: {TEXTO_TENUE}; }}
QLabel#valorServo {{ color: {ACENTO}; font-family: Consolas, monospace; }}

/* SEGMENTO: TITULOS Y AVISOS DE SECCION */
QLabel#tituloSeccion {{ font-size: 19px; font-weight: 600; color: {TEXTO}; }}
QLabel#avisoInfo {{ color: {TEXTO_TENUE}; border-top: 1px solid {BORDE}; padding-top: 10px; }}
QLabel#avisoAtencion {{ color: {AMBAR_ATENCION}; font-weight: 600; }}

/* SEGMENTO: CRUCETA DEL PANEL DE MANDO */
QFrame#tarjetaDireccion {{ background-color: {PANEL}; border: 1px solid {BORDE}; border-radius: 8px; }}
QFrame#tarjetaDireccion QLabel {{ background: transparent; }}
QFrame#tarjetaDireccion[activo="true"] {{ border: 2px solid {ACENTO}; }}
QLabel#flechaDpad {{ color: {ACENTO}; font-size: 17px; font-weight: 700; }}
QLabel#tituloDireccion {{ font-weight: 600; }}

/* SEGMENTO: BARRA SUPERIOR */
QFrame#separadorBarra {{ background-color: {BORDE}; max-width: 1px; }}
QLabel#etiquetaBarra {{ color: {TEXTO_TENUE}; }}

QSlider::groove:horizontal {{ height: 4px; background: {BORDE}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACENTO}; width: 14px; margin: -6px 0; border-radius: 7px; }}
QSlider::handle:horizontal:hover {{ background: {ACENTO_CLARO}; }}

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{ background-color: {ELEVADO}; color: {TEXTO}; border: 1px solid {BORDE}; border-radius: 4px; padding: 4px 6px; }}
QComboBox QAbstractItemView {{ background-color: {PANEL}; color: {TEXTO}; selection-background-color: {BORDE}; }}

QListWidget, QTableWidget {{ background-color: {PANEL}; color: {TEXTO}; border: 1px solid {BORDE}; border-radius: 4px; gridline-color: {BORDE}; }}
QListWidget::item {{ padding: 3px 4px; }}
QListWidget::item:selected {{ background-color: {BORDE}; color: {TEXTO}; }}
QHeaderView::section {{ background-color: {ELEVADO}; color: {TEXTO_TENUE}; border: none; padding: 4px; }}

/* SEGMENTO: CONSOLA
   Antes tenia su propio verde fosforescente puesto a mano en console_panel.py,
   que era el unico color de toda la app fuera de esta paleta. */
QPlainTextEdit#consola {{ background-color: #0d0f14; color: #aab3c0; border: 1px solid {BORDE}; border-radius: 4px;
                          font-family: Consolas, 'Courier New', monospace; font-size: 12px; }}

QScrollBar:vertical {{ background: {PANEL}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDE}; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {BORDE_CLARO}; }}

QSplitter::handle {{ background-color: {BORDE}; }}
"""
