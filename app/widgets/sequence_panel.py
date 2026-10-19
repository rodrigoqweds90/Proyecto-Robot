"""SEGMENTO: PANEL DE SECUENCIAS
Encadena poses guardadas con una pausa entre cada una, con repeticion o bucle.

Este widget arma DOS cajas que la ventana principal coloca en columnas
distintas (`caja_secuencias` a la derecha, `caja_pasos` abajo del control
manual): la logica y el estado viven aca en un solo lugar, pero en pantalla
quedan separadas para que la lista de secuencias y la de pasos dejen de estar
amontonadas una encima de la otra.
"""

import storage
from PySide6.QtCore import Qt, QTimer, Signal
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
    paso_sincronizado = Signal(object, int)  # angulos + ms: los servos llegan todos juntos (POSET)
    reproduccion_cambiada = Signal(bool)  # True mientras esta reproduciendo
    secuencias_cambiadas = Signal()  # se guardo, sobrescribio, borro o importo alguna

    def __init__(self, positions_panel, parent=None):
        super().__init__(parent)
        self._positions_panel = positions_panel
        self.secuencias = storage.cargar_secuencias()
        self._pasos_actuales = []  # lista de dicts {"posicion": str, "duracion_ms": int}

        self.caja_secuencias = self._construir_caja_secuencias()
        self.caja_pasos = self._construir_caja_pasos()
        # Este widget en si nunca se agrega a ningun layout ni se muestra: solo
        # es el dueño de las dos cajas de arriba (que si se reparentan en la
        # ventana) y del estado compartido entre ellas. Por eso se deja sin
        # padre -- como hijo suelto de la ventana se dibujaria encima del
        # contenido, al no estar dentro de ningun layout.

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._avanzar_reproduccion)
        self._reproduciendo = False
        self._indice_paso = 0
        self._repeticion_actual = 0

    # ------------------------------------------------------------------
    # SEGMENTO: CAJA DE SECUENCIAS GUARDADAS
    # ------------------------------------------------------------------
    def _construir_caja_secuencias(self):
        self.lista_secuencias = QListWidget()
        self.lista_secuencias.setToolTip("Tus secuencias guardadas. Selecciona una para cargar sus pasos.")
        self.lista_secuencias.addItems(sorted(self.secuencias.keys()))
        # Dos señales: currentItemChanged cubre cambiar a OTRA secuencia
        # (mouse o teclado); itemClicked cubre volver a hacer click en la que
        # YA estaba seleccionada (Qt no dispara currentItemChanged en ese
        # caso).
        self.lista_secuencias.currentItemChanged.connect(self._on_seleccion_cambiada)
        self.lista_secuencias.itemClicked.connect(self._on_click_en_secuencia)

        btn_nueva = QPushButton("Nueva")
        btn_nueva.setToolTip("Vacia los pasos para armar una secuencia distinta.")
        btn_guardar = QPushButton("Guardar")
        btn_guardar.setToolTip("Guarda los pasos actuales con un nombre (sobrescribe si ya existe ese nombre).")
        btn_borrar = QPushButton("Borrar")
        btn_borrar.setToolTip("Elimina la secuencia seleccionada.")
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

        fila_categoria = QHBoxLayout()
        fila_categoria.addWidget(QLabel("Categoría:"))
        fila_categoria.addWidget(self.combo_categoria, 1)

        self.combo_copiar_de = QComboBox()
        self.combo_copiar_de.setToolTip(
            "Elige una secuencia guardada para copiar sus pasos al final de los pasos actuales."
        )
        self._refrescar_combo_copiar()
        btn_copiar_pasos = QPushButton("Copiar pasos")
        btn_copiar_pasos.setToolTip(
            "Agrega los pasos de la secuencia elegida al final de los pasos actuales (se suman, no reemplazan)."
        )
        btn_copiar_pasos.clicked.connect(self._copiar_pasos_de)

        fila_copiar = QHBoxLayout()
        fila_copiar.addWidget(QLabel("Copiar de:"))
        fila_copiar.addWidget(self.combo_copiar_de, 1)
        fila_copiar.addWidget(btn_copiar_pasos)

        caja = QWidget()
        layout = QVBoxLayout(caja)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.lista_secuencias)
        layout.addLayout(fila_gestion)
        layout.addLayout(fila_categoria)
        layout.addLayout(fila_copiar)
        return caja

    # ------------------------------------------------------------------
    # SEGMENTO: CAJA DE PASOS DE LA SECUENCIA ACTUAL
    # ------------------------------------------------------------------
    def _construir_caja_pasos(self):
        self.lista_pasos = QListWidget()
        self.lista_pasos.setToolTip("El robot ejecuta estos pasos en orden, de arriba hacia abajo.")

        self.spin_duracion = QSpinBox()
        self.spin_duracion.setRange(100, 60000)
        self.spin_duracion.setSingleStep(100)
        self.spin_duracion.setValue(1000)
        self.spin_duracion.setSuffix(" ms")
        self.spin_duracion.setToolTip("Cuanto espera el robot en esa pose antes de pasar al siguiente paso.")

        btn_agregar_paso = QPushButton("+ Agregar pose seleccionada")
        btn_agregar_paso.setToolTip(
            "Agrega al final de la secuencia la pose que tengas seleccionada en la lista de Poses,\n"
            "con la duracion de aca al lado."
        )
        btn_quitar_paso = QPushButton("− Quitar paso")
        btn_quitar_paso.setToolTip("Quita el paso seleccionado en la lista de arriba.")
        btn_agregar_paso.clicked.connect(self._agregar_paso)
        btn_quitar_paso.clicked.connect(self._quitar_paso)

        fila_paso = QHBoxLayout()
        fila_paso.addWidget(QLabel("Duración:"))
        fila_paso.addWidget(self.spin_duracion)
        fila_paso.addWidget(btn_agregar_paso, 1)
        fila_paso.addWidget(btn_quitar_paso)

        self.spin_repeticiones = QSpinBox()
        self.spin_repeticiones.setRange(1, 999)
        self.spin_repeticiones.setValue(1)
        self.spin_repeticiones.setToolTip(
            "Cuantas veces se repite la secuencia completa (se ignora si 'Repetir en bucle' esta marcado)."
        )
        self.check_bucle = QCheckBox("Repetir en bucle")
        self.check_bucle.setToolTip("Repite la secuencia sin parar, hasta que presiones Detener.")
        # Apagada = como siempre (POSE con la velocidad de arriba). Prendida = cada paso se manda
        # con su duracion y el robot reparte el movimiento para que todos los servos lleguen juntos.
        # Necesita el firmware con el comando POSET.
        self.check_sincronizado = QCheckBox("Movimiento sincronizado")
        self.check_sincronizado.setToolTip(
            "Todos los servos arrancan y llegan juntos a cada pose, en la duracion de ese paso\n"
            "(sin tirones). Ignora la velocidad de arriba. Requiere el firmware nuevo (POSET)."
        )

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
        fila_reproduccion.addWidget(self.check_sincronizado, 1, 2)
        fila_reproduccion.addWidget(self.btn_reproducir, 2, 0, 1, 2)
        fila_reproduccion.addWidget(self.btn_detener, 2, 2)

        caja = QWidget()
        layout = QVBoxLayout(caja)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.lista_pasos)
        layout.addLayout(fila_paso)
        layout.addLayout(fila_reproduccion)
        return caja

    # ------------------------------------------------------------------
    # SEGMENTO: SINCRONIZACION CON EL PANEL DE POSES
    # ------------------------------------------------------------------
    def refrescar_posiciones_disponibles(self):
        """Se guardo o borro una pose: los pasos se redibujan para que se vea
        si alguno quedo apuntando a una pose que ya no existe."""
        self._refrescar_lista_pasos()

    def renombrar_pose_en_secuencias(self, nombre_viejo, nombre_nuevo):
        """Una pose cambio de nombre: se actualizan todos los pasos que la
        usaban, tanto los que se estan editando como los ya guardados en disco.
        Sin esto, renombrar una pose dejaria pasos apuntando a un nombre que ya
        no existe."""
        for nombre, datos in self.secuencias.items():
            afectada = False
            for paso in datos["pasos"]:
                if paso["posicion"] == nombre_viejo:
                    paso["posicion"] = nombre_nuevo
                    afectada = True
            if afectada:
                storage.guardar_secuencia(nombre, datos["pasos"], datos["categoria"])
        for paso in self._pasos_actuales:
            if paso["posicion"] == nombre_viejo:
                paso["posicion"] = nombre_nuevo
        self._refrescar_lista_pasos()

    def _refrescar_lista_pasos(self):
        self.lista_pasos.clear()
        for i, paso in enumerate(self._pasos_actuales, start=1):
            # Un paso puede quedar huerfano si se borro la pose que usaba: se
            # marca en el texto en vez de fallar recien al reproducir.
            falta = "" if self._positions_panel.angulos_de(paso["posicion"]) else "  ⚠ pose borrada"
            self.lista_pasos.addItem(f"{i}. {paso['posicion']}  —  {paso['duracion_ms']} ms{falta}")

    def _recargar_lista_secuencias(self, seleccionar=None):
        # Un solo lugar que rearma la lista + el combo de copiar, para que
        # guardar, borrar e importar no se desincronicen entre si. Las señales
        # se bloquean porque clear() dispara currentItemChanged, y eso volveria
        # a cargar pasos encima de los que el usuario acaba de editar.
        self.lista_secuencias.blockSignals(True)
        self.lista_secuencias.clear()
        self.lista_secuencias.addItems(sorted(self.secuencias.keys()))
        if seleccionar:
            item = self.lista_secuencias.findItems(seleccionar, Qt.MatchExactly)
            if item:
                self.lista_secuencias.setCurrentItem(item[0])
        self.lista_secuencias.blockSignals(False)
        self._refrescar_combo_copiar()

    def _refrescar_combo_copiar(self):
        seleccion = self.combo_copiar_de.currentText()
        self.combo_copiar_de.clear()
        self.combo_copiar_de.addItems(sorted(self.secuencias.keys()))
        indice = self.combo_copiar_de.findText(seleccion)
        if indice >= 0:
            self.combo_copiar_de.setCurrentIndex(indice)

    def _copiar_pasos_de(self):
        nombre = self.combo_copiar_de.currentText()
        if not nombre or nombre not in self.secuencias:
            QMessageBox.information(
                self.caja_secuencias, "Elige una secuencia", "Selecciona de qué secuencia guardada copiar los pasos."
            )
            return
        pasos_copiados = [dict(p) for p in self.secuencias[nombre]["pasos"]]
        if not pasos_copiados:
            QMessageBox.information(self.caja_secuencias, "Secuencia vacia", f"'{nombre}' no tiene pasos guardados.")
            return
        self._pasos_actuales.extend(pasos_copiados)
        self._refrescar_lista_pasos()

    def importar_secuencias(self, nuevas):
        """Agrega/reemplaza secuencias desde un archivo importado (ver 'Importar movimientos').
        Sobrescribe sin preguntar por nombre repetido -- es una importacion masiva."""
        for nombre, datos in nuevas.items():
            pasos = datos.get("pasos", [])
            categoria = datos.get("categoria", "")
            storage.guardar_secuencia(nombre, pasos, categoria)
            self.secuencias[nombre] = {"categoria": categoria, "pasos": pasos}
        self._recargar_lista_secuencias()
        self.secuencias_cambiadas.emit()

    # ------------------------------------------------------------------
    # SEGMENTO: EDICION DE PASOS
    # ------------------------------------------------------------------
    def _agregar_paso(self):
        # La pose sale de la seleccion en el panel de Poses (no de un
        # desplegable aparte): asi el filtro por carpeta de ese panel sirve
        # tambien para armar la secuencia, y ves la pose en el robot antes de
        # agregarla.
        posicion = self._positions_panel.nombre_seleccionado()
        if not posicion:
            QMessageBox.information(
                self.caja_pasos, "Ninguna pose seleccionada",
                "Selecciona primero una pose en la lista de Poses y despues agregala como paso.",
            )
            return
        self._pasos_actuales.append({"posicion": posicion, "duracion_ms": self.spin_duracion.value()})
        self._refrescar_lista_pasos()

    def _quitar_paso(self):
        fila = self.lista_pasos.currentRow()
        if fila < 0:
            QMessageBox.information(
                self.caja_pasos, "Selecciona un paso", "Haz click en el paso de la lista que quieres quitar."
            )
            return
        del self._pasos_actuales[fila]
        self._refrescar_lista_pasos()

    # ------------------------------------------------------------------
    # SEGMENTO: GUARDAR Y BORRAR SECUENCIAS
    # ------------------------------------------------------------------
    def _nueva_secuencia(self):
        self._pasos_actuales = []
        self._refrescar_lista_pasos()
        self.lista_secuencias.clearSelection()
        self.combo_categoria.setCurrentIndex(-1)
        self.combo_categoria.clearEditText()

    def _guardar_secuencia(self):
        if not self._pasos_actuales:
            QMessageBox.information(self.caja_secuencias, "Secuencia vacia", "Agrega al menos un paso antes de guardar.")
            return
        item_actual = self.lista_secuencias.currentItem()
        nombre_sugerido = item_actual.text() if item_actual else ""
        nombre, ok = QInputDialog.getText(
            self.caja_secuencias, "Guardar secuencia", "Nombre de la secuencia:", text=nombre_sugerido
        )
        if not ok or not nombre.strip():
            return
        nombre = nombre.strip()
        categoria = self.combo_categoria.currentText().strip()
        storage.guardar_secuencia(nombre, self._pasos_actuales, categoria)
        # Se guarda una COPIA de los pasos, no la misma lista: si se guardara
        # `self._pasos_actuales` tal cual, seguir editando los pasos despues de
        # guardar (agregar, quitar, copiar de otra) mutaria tambien la secuencia
        # ya guardada en memoria, y quedaba mostrando pasos que nunca llegaron
        # al disco.
        self.secuencias[nombre] = {"categoria": categoria, "pasos": [dict(p) for p in self._pasos_actuales]}
        self._recargar_lista_secuencias(seleccionar=nombre)
        self.secuencias_cambiadas.emit()

    def _borrar_secuencia(self):
        item = self.lista_secuencias.currentItem()
        if not item:
            return
        nombre = item.text()
        respuesta = QMessageBox.question(self.caja_secuencias, "Borrar secuencia", f"¿Borrar la secuencia '{nombre}'?")
        if respuesta == QMessageBox.Yes:
            storage.borrar_secuencia(nombre)
            del self.secuencias[nombre]
            self._recargar_lista_secuencias()
            self.secuencias_cambiadas.emit()

    def _on_seleccion_cambiada(self, actual, anterior):
        if not actual:
            return
        self._cargar_secuencia(actual.text())

    def _on_click_en_secuencia(self, item):
        # Cubre volver a hacer click en la secuencia ya seleccionada (ver
        # nota de las dos señales en _construir_caja_secuencias).
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
    # SEGMENTO: REPRODUCCION
    # ------------------------------------------------------------------
    def _reproducir(self):
        if not self._pasos_actuales:
            QMessageBox.information(self.caja_pasos, "Secuencia vacia", "No hay pasos que reproducir.")
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
            if self.check_sincronizado.isChecked():
                self.paso_sincronizado.emit(angulos, paso["duracion_ms"])
            else:
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
