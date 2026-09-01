"""SEGMENTO: PUNTO DE ENTRADA
Arranca la aplicacion: crea la ventana principal y aplica la paleta de
colores unica de toda la interfaz (fondo neutro + un solo color de acento;
el rojo queda reservado nada mas para la parada de emergencia).
"""

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from main_window import MainWindow
from paths import directorio_app

ICONO_APP = directorio_app() / "assets" / "icon.ico"


def _registrar_app_en_windows():
    # Sin esto, Windows agrupa la ventana bajo el icono de python.exe en la
    # barra de tareas en vez de usar el icono propio de la app.
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RobotControl.App")
    except Exception:
        pass

HOJA_DE_ESTILOS = """
QWidget { background-color: #14161b; color: #e6e8ec; font-family: 'Segoe UI', sans-serif; font-size: 13px; }
QMainWindow { background-color: #14161b; }

QMenuBar { background-color: #1b1e25; color: #e6e8ec; border-bottom: 1px solid #2b303a; }
QMenuBar::item:selected { background-color: #20242c; }
QMenu { background-color: #1b1e25; color: #e6e8ec; border: 1px solid #2b303a; }
QMenu::item:selected { background-color: #20242c; }

QGroupBox { border: 1px solid #2b303a; border-radius: 6px; margin-top: 14px; background-color: #1b1e25; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #8a90a0; }

QTabWidget::pane { border: 1px solid #2b303a; border-radius: 6px; top: -1px; }
QTabBar::tab { background: #1b1e25; color: #8a90a0; padding: 8px 16px; border: 1px solid #2b303a; border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
QTabBar::tab:selected { background: #20242c; color: #e6e8ec; }

QPushButton { background-color: #20242c; color: #e6e8ec; border: 1px solid #2b303a; border-radius: 5px; padding: 6px 14px; }
QPushButton:hover { background-color: #262b35; border-color: #3a4150; }
QPushButton:pressed { background-color: #1b1e25; }
QPushButton:disabled { color: #565c68; background-color: #1b1e25; }

QPushButton#botonPrimario { background-color: #5b8fd6; color: #0d1420; border: none; font-weight: 600; }
QPushButton#botonPrimario:hover { background-color: #6f9fe0; }

QPushButton#botonEmergencia { background-color: #c0392b; color: white; font-weight: 700; border: none; padding: 8px 18px; }
QPushButton#botonEmergencia:hover { background-color: #d94632; }
QPushButton#botonEmergencia:disabled { background-color: #3a2a28; color: #8a6a66; }

QLabel#estadoConectado { color: #4fd18f; font-weight: 600; }
QLabel#estadoDesconectado { color: #c0392b; font-weight: 600; }
QLabel#textoSecundario { color: #8a90a0; font-family: Consolas, monospace; font-size: 12px; }
QLabel#valorServo { color: #5b8fd6; font-family: Consolas, monospace; }

QSlider::groove:horizontal { height: 4px; background: #2b303a; border-radius: 2px; }
QSlider::handle:horizontal { background: #5b8fd6; width: 14px; margin: -6px 0; border-radius: 7px; }
QSlider::handle:horizontal:hover { background: #6f9fe0; }

QComboBox, QSpinBox, QLineEdit { background-color: #20242c; color: #e6e8ec; border: 1px solid #2b303a; border-radius: 4px; padding: 4px 6px; }
QComboBox QAbstractItemView { background-color: #1b1e25; color: #e6e8ec; selection-background-color: #2b303a; }

QListWidget, QTableWidget { background-color: #1b1e25; color: #e6e8ec; border: 1px solid #2b303a; border-radius: 4px; gridline-color: #2b303a; }
QHeaderView::section { background-color: #20242c; color: #8a90a0; border: none; padding: 4px; }

QScrollBar:vertical { background: #1b1e25; width: 10px; }
QScrollBar::handle:vertical { background: #2b303a; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #3a4150; }

QSplitter::handle { background-color: #2b303a; }
"""


def main():
    _registrar_app_en_windows()
    app = QApplication(sys.argv)
    app.setStyleSheet(HOJA_DE_ESTILOS)
    if ICONO_APP.exists():
        app.setWindowIcon(QIcon(str(ICONO_APP)))
    ventana = MainWindow()
    if ICONO_APP.exists():
        ventana.setWindowIcon(QIcon(str(ICONO_APP)))
    ventana.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
