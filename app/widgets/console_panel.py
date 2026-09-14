"""SEGMENTO: CONSOLA DE CONEXION
Solo lectura: muestra todo lo que entra y sale por el puerto serie.
"""

import datetime

from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget


class ConsolePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.texto = QPlainTextEdit()
        self.texto.setReadOnly(True)
        self.texto.setMaximumBlockCount(2000)
        # El estilo vive en estilos.py junto con el resto de la paleta; antes
        # estaba puesto a mano aca con un verde que no pertenecia a ninguna
        # otra parte de la app.
        self.texto.setObjectName("consola")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.texto)

    def agregar_linea(self, texto, es_error=False):
        marca = datetime.datetime.now().strftime("%H:%M:%S")
        prefijo = "⚠" if es_error else "›"
        self.texto.appendPlainText(f"[{marca}] {prefijo} {texto}")
