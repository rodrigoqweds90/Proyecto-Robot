"""SEGMENTO: EDITOR DE CANALES DEL PCA9685
Ventana para decidir que servo va en cada pin del PCA9685 (0-15), a que grupo
del panel Manual pertenece, y su rango de angulo/pulso. No toca el firmware:
el ESP32 solo mueve "canal, pulso, velocidad", el significado de cada canal
vive aqui.
"""

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

import channel_config as cc

COLUMNAS = ["Canal PCA", "Nombre", "Grupo", "Áng. min", "Áng. max", "Pulso min", "Pulso max"]
SERVO_VACIO = {"canal": 0, "nombre": "Nuevo servo", "grupo": "Otro",
               "angMin": -90, "angMax": 90, "pwmMin": 500, "pwmMax": 2450}


class ChannelsDialog(QDialog):
    def __init__(self, servos, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Canales de servos — PCA9685")
        self.resize(760, 480)
        self._servos_resultado = None

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)

        for servo in sorted(servos, key=lambda s: s["canal"]):
            self._agregar_fila(servo)

        btn_agregar = QPushButton("+ Agregar servo")
        btn_quitar = QPushButton("- Quitar seleccionado")
        btn_agregar.clicked.connect(lambda: self._agregar_fila())
        btn_quitar.clicked.connect(self._quitar_fila)

        fila_botones = QHBoxLayout()
        fila_botones.addWidget(btn_agregar)
        fila_botones.addWidget(btn_quitar)
        fila_botones.addStretch()

        botones = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botones.button(QDialogButtonBox.Save).setText("Guardar")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self._guardar)
        botones.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabla)
        layout.addLayout(fila_botones)
        layout.addWidget(botones)

    # ------------------------------------------------------------------
    def _agregar_fila(self, servo=None):
        servo = servo or SERVO_VACIO
        fila = self.tabla.rowCount()
        self.tabla.insertRow(fila)

        spin_canal = QSpinBox()
        spin_canal.setRange(0, 15)
        spin_canal.setValue(int(servo["canal"]))
        self.tabla.setCellWidget(fila, 0, spin_canal)

        self.tabla.setItem(fila, 1, QTableWidgetItem(servo["nombre"]))

        combo_grupo = QComboBox()
        combo_grupo.setEditable(True)
        combo_grupo.addItems(cc.GRUPOS_SUGERIDOS)
        combo_grupo.setCurrentText(servo["grupo"])
        self.tabla.setCellWidget(fila, 2, combo_grupo)

        for columna, clave in ((3, "angMin"), (4, "angMax"), (5, "pwmMin"), (6, "pwmMax")):
            spin = QSpinBox()
            spin.setRange(-180, 3000)
            spin.setValue(int(servo[clave]))
            self.tabla.setCellWidget(fila, columna, spin)

    def _quitar_fila(self):
        fila = self.tabla.currentRow()
        if fila >= 0:
            self.tabla.removeRow(fila)

    # ------------------------------------------------------------------
    def _leer_tabla(self):
        servos = []
        canales_vistos = set()
        for fila in range(self.tabla.rowCount()):
            canal = self.tabla.cellWidget(fila, 0).value()
            if canal in canales_vistos:
                QMessageBox.warning(self, "Canal repetido",
                                     f"El canal {canal} esta asignado a mas de un servo.")
                return None
            canales_vistos.add(canal)

            nombre = self.tabla.item(fila, 1).text().strip() or f"Canal {canal}"
            grupo = self.tabla.cellWidget(fila, 2).currentText().strip() or "Otro"
            ang_min = self.tabla.cellWidget(fila, 3).value()
            ang_max = self.tabla.cellWidget(fila, 4).value()
            pwm_min = self.tabla.cellWidget(fila, 5).value()
            pwm_max = self.tabla.cellWidget(fila, 6).value()

            if ang_min >= ang_max:
                QMessageBox.warning(self, "Rango invalido",
                                     f"'{nombre}': el angulo minimo debe ser menor al maximo. "
                                     "(el pulso si puede ir invertido, para servos montados en espejo)")
                return None
            if pwm_min == pwm_max:
                QMessageBox.warning(self, "Rango invalido",
                                     f"'{nombre}': el pulso minimo y maximo no pueden ser iguales.")
                return None

            servos.append({
                "canal": canal, "nombre": nombre, "grupo": grupo,
                "angMin": ang_min, "angMax": ang_max, "pwmMin": pwm_min, "pwmMax": pwm_max,
            })
        return servos

    def _guardar(self):
        servos = self._leer_tabla()
        if servos is None:
            return
        self._servos_resultado = servos
        self.accept()

    def servos_guardados(self):
        return self._servos_resultado
