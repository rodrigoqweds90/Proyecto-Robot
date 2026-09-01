"""SEGMENTO: PANEL DE SECUENCIAS
Encadena poses guardadas con una pausa entre cada una, con repeticion o bucle.
"""

import storage
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


CATEGORIAS_SUGERIDAS = ["Avanzar", "Retroceder", "Girar Izquierda", "Girar Derecha", "Otro"]


class SequencePanel(QWidget):
    # Signal(object), no Signal(dict): ver la nota en positions_panel.py --
    # PySide6 a veces falla al convertir un dict directo ("Cannot
    # copy-convert dict to C++") y la señal se pierde en silencio.
    paso_activado = Signal(object)  # angulos de la pose que hay que aplicar ahora
    reproduccion_cambiada = Signal(bool)  # True mientras esta reproduciendo

    def __init__(self, positions_panel, parent=None):
        super().__init__(parent)
        self._positions_panel = positions_panel
        self.secuencias = storage.cargar_secuencias()
        self._pasos_actuales = []  # lista de dicts {"posicion": str, "duracion_ms": int}
        # True desde que se agrega/quita un paso hasta que se guarda. Mientras
        # este en True, cambiar de secuencia seleccionada no pisa los pasos
        # en curso (mismo mecanismo que en positions_panel.py).
        self._hay_ediciones_sin_guardar = False

        self.lista_secuencias = QListWidget()
        self.lista_secuencias.addItems(sorted(self.secuencias.keys()))
        # Dos señales: currentItemChanged cubre cambiar a OTRA secuencia
        # (mouse o teclado); itemClicked cubre volver a hacer click en la que
        # YA estaba seleccionada (Qt no dispara currentItemChanged en ese
        # caso). Las dos respetan _hay_ediciones_sin_guardar por igual.
        self.lista_secuencias.currentItemChanged.connect(self._on_seleccion_cambiada)
        self.lista_secuencias.itemClicked.connect(self._on_click_en_secuencia)

        self.lista_pasos = QListWidget()
        self.lista_pasos.setToolTip("El robot ejecuta estos pasos en orden, de arriba hacia abajo.")

        self.combo_posicion = QComboBox()
        self.combo_posicion.setToolTip("Pose que se agregara como proximo paso (viene de tu lista de Poses).")
        self._refrescar_combo_posiciones()
        self.spin_duracion = QSpinBox()
        self.spin_duracion.setRange(100, 60000)
        self.spin_duracion.setSingleStep(100)
        self.spin_duracion.setValue(1000)
        self.spin_duracion.setSuffix(" ms")
        self.spin_duracion.setToolTip("Cuanto espera el robot en esa pose antes de pasar al siguiente paso.")

        btn_agregar_paso = QPushButton("+ Agregar paso")
        btn_agregar_paso.setToolTip("Agrega la pose de arriba, con esa duracion, al final de la secuencia.")
        btn_quitar_paso = QPushButton("- Quitar paso")
        btn_quitar_paso.setToolTip("Quita el paso seleccionado en la lista de pasos.")
        btn_agregar_paso.clicked.connect(self._agregar_paso)
        btn_quitar_paso.clicked.connect(self._quitar_paso)

        fila_paso = QHBoxLayout()
        fila_paso.addWidget(QLabel("Pose:"))
        fila_paso.addWidget(self.combo_posicion, 2)
        fila_paso.addWidget(QLabel("Duración:"))
        fila_paso.addWidget(self.spin_duracion, 1)
        fila_paso.addWidget(btn_agregar_paso)
        fila_paso.addWidget(btn_quitar_paso)

        btn_nueva = QPushButton("Nueva")
        btn_nueva.setToolTip("Vacia los pasos de abajo para armar una secuencia distinta.")
        btn_guardar = QPushButton("Guardar")
        btn_guardar.setToolTip("Guarda los pasos actuales con un nombre (sobrescribe si ya existe ese nombre).")
        btn_borrar = QPushButton("Borrar")
        btn_borrar.setToolTip("Elimina la secuencia seleccionada arriba.")
        btn_nueva.clicked.connect(self._nueva_secuencia)
        btn_guardar.clicked.connect(self._guardar_secuencia)
        btn_borrar.clicked.connect(self._borrar_secuencia)

        self.combo_categoria = QComboBox()
        self.combo_categoria.setEditable(True)
        self.combo_categoria.addItems(CATEGORIAS_SUGERIDAS)
        self.combo_categoria.setCurrentIndex(-1)
        self.combo_categoria.setToolTip(
            "Que tipo de movimiento es (Avanzar, Retroceder, etc.) -- sirve para que otro "
            "programa (como una futura app de mando por Bluetooth) sepa que secuencia usar."
        )

        fila_gestion = QHBoxLayout()
        fila_gestion.addWidget(btn_nueva)
        fila_gestion.addWidget(btn_guardar)
        fila_gestion.addWidget(btn_borrar)
        fila_gestion.addWidget(QLabel("Categoría:"))
        fila_gestion.addWidget(self.combo_categoria, 1)

        self.spin_repeticiones = QSpinBox()
        self.spin_repeticiones.setRange(1, 999)
        self.spin_repeticiones.setValue(1)
        self.spin_repeticiones.setToolTip("Cuantas veces se repite la secuencia completa (se ignora si 'Repetir en bucle' esta marcado).")
        self.check_bucle = QCheckBox("Repetir en bucle")
        self.check_bucle.setToolTip("Repite la secuencia sin parar, hasta que presiones Detener.")

        self.btn_reproducir = QPushButton("▶ Reproducir")
        self.btn_reproducir.setToolTip("Ejecuta la secuencia de pasos en orden.")
        self.btn_detener = QPushButton("■ Detener")
        self.btn_detener.setToolTip("Detiene la reproduccion en el paso actual.")
        self.btn_detener.setEnabled(False)
        self.btn_reproducir.clicked.connect(self._reproducir)
        self.btn_detener.clicked.connect(self._detener)

        fila_reproduccion = QGridLayout()
        fila_reproduccion.addWidget(QLabel("Repeticiones:"), 0, 0)
        fila_reproduccion.addWidget(self.spin_repeticiones, 0, 1)
        fila_reproduccion.addWidget(self.check_bucle, 0, 2)
        fila_reproduccion.addWidget(self.btn_reproducir, 1, 0, 1, 2)
        fila_reproduccion.addWidget(self.btn_detener, 1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Secuencias guardadas"))
        layout.addWidget(self.lista_secuencias)
        layout.addLayout(fila_gestion)
        layout.addWidget(QLabel("Pasos de la secuencia actual"))
        layout.addWidget(self.lista_pasos)
        layout.addLayout(fila_paso)
        layout.addLayout(fila_reproduccion)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._avanzar_reproduccion)
        self._reproduciendo = False
        self._indice_paso = 0
        self._repeticion_actual = 0

    # ------------------------------------------------------------------
    def refrescar_posiciones_disponibles(self):
        self._refrescar_combo_posiciones()

    def _refrescar_combo_posiciones(self):
        seleccion = self.combo_posicion.currentText()
        self.combo_posicion.clear()
        self.combo_posicion.addItems(self._positions_panel.nombres())
        indice = self.combo_posicion.findText(seleccion)
        if indice >= 0:
            self.combo_posicion.setCurrentIndex(indice)

    def _refrescar_lista_pasos(self):
        self.lista_pasos.clear()
        for i, paso in enumerate(self._pasos_actuales, start=1):
            self.lista_pasos.addItem(f"{i}. {paso['posicion']}  —  {paso['duracion_ms']} ms")

    # ------------------------------------------------------------------
    def _agregar_paso(self):
        posicion = self.combo_posicion.currentText()
        if not posicion:
            QMessageBox.information(self, "Sin poses", "Primero guarda alguna pose en el panel de Poses.")
            return
        self._pasos_actuales.append({"posicion": posicion, "duracion_ms": self.spin_duracion.value()})
        self._hay_ediciones_sin_guardar = True
        self._refrescar_lista_pasos()

    def _quitar_paso(self):
        fila = self.lista_pasos.currentRow()
        if fila < 0:
            return
        del self._pasos_actuales[fila]
        self._hay_ediciones_sin_guardar = True
        self._refrescar_lista_pasos()

    def _nueva_secuencia(self):
        self._pasos_actuales = []
        self._hay_ediciones_sin_guardar = False
        self._refrescar_lista_pasos()
        self.lista_secuencias.clearSelection()
        self.combo_categoria.setCurrentIndex(-1)
        self.combo_categoria.clearEditText()

    def _guardar_secuencia(self):
        if not self._pasos_actuales:
            QMessageBox.information(self, "Secuencia vacia", "Agrega al menos un paso antes de guardar.")
            return
        item_actual = self.lista_secuencias.currentItem()
        nombre_sugerido = item_actual.text() if item_actual else ""
        nombre, ok = QInputDialog.getText(
            self, "Guardar secuencia", "Nombre de la secuencia:", text=nombre_sugerido
        )
        if not ok or not nombre.strip():
            return
        nombre = nombre.strip()
        categoria = self.combo_categoria.currentText().strip()
        storage.guardar_secuencia(nombre, self._pasos_actuales, categoria)
        self.secuencias[nombre] = {"categoria": categoria, "pasos": self._pasos_actuales}
        self._hay_ediciones_sin_guardar = False
        self.lista_secuencias.clear()
        self.lista_secuencias.addItems(sorted(self.secuencias.keys()))

    def _borrar_secuencia(self):
        item = self.lista_secuencias.currentItem()
        if not item:
            return
        nombre = item.text()
        respuesta = QMessageBox.question(self, "Borrar secuencia", f"¿Borrar la secuencia '{nombre}'?")
        if respuesta == QMessageBox.Yes:
            storage.borrar_secuencia(nombre)
            del self.secuencias[nombre]
            self.lista_secuencias.clear()
            self.lista_secuencias.addItems(sorted(self.secuencias.keys()))

    def _on_seleccion_cambiada(self, actual, anterior):
        if not actual:
            return
        if self._hay_ediciones_sin_guardar:
            # Pasos sin guardar en curso: no los pisamos. Se revierte la
            # seleccion visual al item de antes.
            self.lista_secuencias.blockSignals(True)
            self.lista_secuencias.setCurrentItem(anterior)
            self.lista_secuencias.blockSignals(False)
            return
        self._cargar_secuencia(actual.text())

    def _on_click_en_secuencia(self, item):
        # Cubre volver a hacer click en la secuencia ya seleccionada (ver
        # nota de las dos señales en __init__).
        if self._hay_ediciones_sin_guardar:
            return
        self._cargar_secuencia(item.text())

    def _cargar_secuencia(self, nombre):
        if not nombre or nombre not in self.secuencias:
            return
        self._pasos_actuales = [dict(p) for p in self.secuencias[nombre]["pasos"]]
        self._refrescar_lista_pasos()
        categoria = self.secuencias[nombre]["categoria"]
        indice = self.combo_categoria.findText(categoria)
        if indice >= 0:
            self.combo_categoria.setCurrentIndex(indice)
        else:
            self.combo_categoria.setCurrentText(categoria)

    # ------------------------------------------------------------------
    def _reproducir(self):
        if not self._pasos_actuales:
            QMessageBox.information(self, "Secuencia vacia", "No hay pasos que reproducir.")
            return
        self._reproduciendo = True
        self._indice_paso = 0
        self._repeticion_actual = 0
        self.btn_reproducir.setEnabled(False)
        self.btn_detener.setEnabled(True)
        self.reproduccion_cambiada.emit(True)
        self._ejecutar_paso_actual()

    def _detener(self):
        self._reproduciendo = False
        self._timer.stop()
        self.btn_reproducir.setEnabled(True)
        self.btn_detener.setEnabled(False)
        self.reproduccion_cambiada.emit(False)

    def _ejecutar_paso_actual(self):
        if not self._reproduciendo:
            return
        paso = self._pasos_actuales[self._indice_paso]
        angulos = self._positions_panel.angulos_de(paso["posicion"])
        if angulos:
            self.paso_activado.emit(angulos)
        self._timer.start(paso["duracion_ms"])

    def _avanzar_reproduccion(self):
        if not self._reproduciendo:
            return
        self._indice_paso += 1
        if self._indice_paso >= len(self._pasos_actuales):
            self._indice_paso = 0
            self._repeticion_actual += 1
            objetivo = self.spin_repeticiones.value()
            if not self.check_bucle.isChecked() and self._repeticion_actual >= objetivo:
                self._detener()
                return
        self._ejecutar_paso_actual()

    def detener_por_emergencia(self):
        """Llamado desde afuera cuando se presiona STOP: corta la reproduccion en curso."""
        if self._reproduciendo:
            self._detener()
