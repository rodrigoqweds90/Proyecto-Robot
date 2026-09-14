"""SEGMENTO: PANEL DE CONTROL MANUAL
Un control compacto por servo: nombre + slider + valor en una sola fila,
agrupados por zona del cuerpo y acomodados en columnas para que los 16
servos quepan en pantalla sin tener que hacer tanto scroll. Se reconstruye
cada vez que cambia el mapeo de canales (ver channels_dialog.py).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

ORDEN_GRUPOS_PREFERIDO = ["Pierna derecha", "Pierna izquierda", "Brazo izquierdo", "Brazo derecho", "Torso"]
COLUMNAS_DE_GRUPOS = 2  # el panel ahora comparte la ventana con Poses/Secuencias


class _FilaServo(QWidget):
    angulo_cambiado = Signal(int, int)  # canal, angulo

    def __init__(self, servo, parent=None):
        super().__init__(parent)
        self.canal = servo["canal"]

        label_nombre = QLabel(servo["nombre"])
        label_nombre.setMinimumWidth(96)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(int(servo["angMin"]), int(servo["angMax"]))
        # 0 es el centro habitual, pero si el rango configurado no lo incluye
        # (por ejemplo 10-90), arrancamos en el minimo para que el label
        # siempre muestre el valor real del slider, nunca uno inventado.
        valor_inicial = 0 if servo["angMin"] <= 0 <= servo["angMax"] else int(servo["angMin"])
        self.slider.setValue(valor_inicial)

        self.label_valor = QLabel(f"{self.slider.value()}°")
        self.label_valor.setObjectName("valorServo")
        self.label_valor.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.label_valor.setMinimumWidth(34)

        self.slider.valueChanged.connect(self._on_change)

        fila = QHBoxLayout(self)
        fila.setContentsMargins(2, 1, 2, 1)
        fila.setSpacing(8)
        fila.addWidget(label_nombre)
        fila.addWidget(self.slider, 1)
        fila.addWidget(self.label_valor)

    def _on_change(self, valor):
        self.label_valor.setText(f"{valor}°")
        self.angulo_cambiado.emit(self.canal, valor)

    def set_angulo(self, valor, emitir=False):
        self.slider.blockSignals(not emitir)
        self.slider.setValue(int(valor))
        self.slider.blockSignals(False)
        self.label_valor.setText(f"{int(valor)}°")


class ControlPanel(QWidget):
    angulo_cambiado = Signal(int, int)

    def __init__(self, servos, parent=None):
        super().__init__(parent)
        self.sliders = {}

        # La cuadricula de grupos vive en un widget aparte, dentro de un
        # QVBoxLayout con un "stretch" al final. Asi, si el panel recibe mas
        # alto del que necesita (por el splitter), el espacio sobrante queda
        # vacio abajo en vez de estirar cada fila de servo — eso era lo que
        # hacia ver el grupo "Torso" (con pocos servos) mas grande de lo normal.
        self._cuadricula_widget = QWidget()
        self._layout = QGridLayout(self._cuadricula_widget)
        self._layout.setSpacing(10)

        layout_raiz = QVBoxLayout(self)
        layout_raiz.setContentsMargins(0, 0, 0, 0)
        layout_raiz.addWidget(self._cuadricula_widget)
        layout_raiz.addStretch()

        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.reconstruir(servos)

    # ------------------------------------------------------------------
    def reconstruir(self, servos):
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.sliders = {}

        grupos = {}
        for servo in sorted(servos, key=lambda s: s["canal"]):
            grupos.setdefault(servo["grupo"], []).append(servo)

        nombres_grupos = [g for g in ORDEN_GRUPOS_PREFERIDO if g in grupos]
        nombres_grupos += [g for g in grupos if g not in nombres_grupos]

        for indice, nombre_grupo in enumerate(nombres_grupos):
            caja = QGroupBox(nombre_grupo)
            layout_caja = QVBoxLayout(caja)
            layout_caja.setSpacing(1)
            for servo in grupos[nombre_grupo]:
                fila = _FilaServo(servo)
                fila.angulo_cambiado.connect(self.angulo_cambiado)
                self.sliders[servo["canal"]] = fila
                layout_caja.addWidget(fila)
            layout_caja.addStretch()
            fila_grid, columna_grid = divmod(indice, COLUMNAS_DE_GRUPOS)
            self._layout.addWidget(caja, fila_grid, columna_grid)

    def obtener_angulos(self):
        return {canal: s.slider.value() for canal, s in self.sliders.items()}

    def aplicar_angulos(self, angulos, emitir=False):
        for canal_str, valor in angulos.items():
            canal = int(canal_str)
            if canal in self.sliders:
                self.sliders[canal].set_angulo(valor, emitir=emitir)
