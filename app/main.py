"""SEGMENTO: PUNTO DE ENTRADA
Arranca la aplicacion: crea la ventana principal y aplica la paleta de
colores unica de toda la interfaz (fondo neutro + un solo color de acento;
el rojo queda reservado nada mas para la parada de emergencia).
"""

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from estilos import HOJA_DE_ESTILOS
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
