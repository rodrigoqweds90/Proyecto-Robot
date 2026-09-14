"""SEGMENTO: PANEL DE POSES
Guardar la pose actual, aplicarla, duplicarla, renombrarla o borrarla, y
agruparlas en carpetas para no tener que buscarlas una por una.
"""

import storage
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Valores internos del combo de filtro. Van como userData (no como texto) para
# que no choquen con una carpeta que el usuario llame justo "Todas".
FILTRO_TODAS = "__todas__"
FILTRO_SIN_CARPETA = "__sin_carpeta__"


# ----------------------------------------------------------------------
# SEGMENTO: DIALOGO DE NOMBRE + CARPETA
# ----------------------------------------------------------------------
class DialogoPose(QDialog):
    """Pide nombre y carpeta de una pose en un solo paso (guardar y duplicar)."""

    def __init__(self, titulo, nombre_inicial, carpeta_inicial, carpetas, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)

        self.campo_nombre = QLineEdit(nombre_inicial)
        self.campo_nombre.selectAll()

        self.combo_carpeta = QComboBox()
        self.combo_carpeta.setEditable(True)  # editable: se puede escribir una carpeta nueva aqui mismo
        self.combo_carpeta.addItem("")        # primera opcion vacia = sin carpeta
        self.combo_carpeta.addItems(carpetas)
        self.combo_carpeta.setCurrentText(carpeta_inicial)
        self.combo_carpeta.setToolTip("Deja esto vacio si no quieres meterla en ninguna carpeta.")

        formulario = QFormLayout()
        formulario.addRow("Nombre:", self.campo_nombre)
        formulario.addRow("Carpeta:", self.combo_carpeta)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(formulario)
        layout.addWidget(botones)

    def valores(self):
        return self.campo_nombre.text().strip(), self.combo_carpeta.currentText().strip()


# ----------------------------------------------------------------------
# SEGMENTO: PANEL
# ----------------------------------------------------------------------
class PositionsPanel(QWidget):
    # Signal(object), no Signal(dict): PySide6 a veces falla al convertir un
    # dict directo entre el hilo/tipo C++ ("Cannot copy-convert dict to C++"),
    # perdiendo la señal en silencio. Signal(object) manda el Python object
    # tal cual, sin intentar una conversion estricta -- es la forma correcta
    # de pasar dicts/listas arbitrarios por una señal en PySide6.
    posicion_aplicada = Signal(object)       # aplicar una pose de verdad (sliders + robot)
    solicitar_captura = Signal()             # pide al main window los angulos actuales (para guardar nueva)
    solicitar_sobrescritura = Signal(str)    # idem, pero para reemplazar la pose ya seleccionada
    lista_cambiada = Signal()                # se guardo, sobrescribio o borro una pose
    pose_renombrada = Signal(str, str)       # (nombre viejo, nombre nuevo) -- para arreglar las secuencias

    def __init__(self, parent=None):
        super().__init__(parent)
        # posiciones: {nombre: angulos}  |  carpetas: {nombre: carpeta}
        # Van separados para que el dict de angulos siga siendo el mismo que
        # espera el resto de la app (y el archivo de exportacion).
        self.posiciones, self.carpetas = storage.cargar_posiciones()
        self._carpetas_guardadas = storage.cargar_carpetas()

        # --- Filtro de carpeta ---
        self.combo_filtro = QComboBox()
        self.combo_filtro.setToolTip("Muestra solo las poses de una carpeta. 'Todas' nunca esconde nada.")
        self.combo_filtro.currentIndexChanged.connect(self._on_filtro_cambiado)

        btn_nueva_carpeta = QPushButton("Nueva carpeta")
        btn_nueva_carpeta.setToolTip("Crea una carpeta vacia para ir metiendo poses despues.")
        btn_nueva_carpeta.clicked.connect(self._on_nueva_carpeta)

        fila_filtro = QHBoxLayout()
        fila_filtro.addWidget(QLabel("Carpeta:"))
        fila_filtro.addWidget(self.combo_filtro, 1)
        fila_filtro.addWidget(btn_nueva_carpeta)

        # --- Lista ---
        self.lista = QListWidget()
        self.lista.setToolTip(
            "Tus poses guardadas. Un click la aplica (sliders y robot).\n"
            "Doble click sobre el nombre para renombrarla."
        )
        # Dos señales: currentItemChanged cubre cambiar a OTRA pose (mouse o
        # teclado); itemClicked cubre volver a hacer click en la que YA
        # estaba seleccionada (Qt no dispara currentItemChanged en ese caso,
        # y sin esto un click de mas se sentia "bloqueado", sin reaccionar).
        self.lista.currentItemChanged.connect(self._on_seleccion_cambiada)
        self.lista.itemClicked.connect(self._on_click_en_pose)
        self.lista.itemDoubleClicked.connect(self._on_doble_click)

        # --- Botones ---
        btn_guardar = QPushButton("Guardar como nueva")
        btn_guardar.setToolTip("Guarda la posicion actual de los sliders como una pose con nombre nuevo.")
        btn_duplicar = QPushButton("Duplicar")
        btn_duplicar.setToolTip(
            "Hace una copia de la pose seleccionada con otro nombre.\n"
            "Sirve para partir de una pose ya calibrada sin tocar la original."
        )
        btn_sobrescribir = QPushButton("Sobrescribir")
        btn_sobrescribir.setToolTip("Reemplaza la pose seleccionada en la lista con la posicion actual de los sliders.")
        btn_aplicar = QPushButton("Aplicar")
        btn_aplicar.setToolTip("Mueve los sliders (y el robot, si esta conectado) a la pose seleccionada.")
        btn_mover = QPushButton("Mover a carpeta…")
        btn_mover.setToolTip("Cambia de carpeta la pose seleccionada (la pose no se copia ni se borra).")
        btn_borrar = QPushButton("Borrar")
        btn_borrar.setToolTip("Elimina la pose seleccionada.")

        btn_guardar.clicked.connect(lambda: self.solicitar_captura.emit())
        btn_duplicar.clicked.connect(self._on_duplicar)
        btn_sobrescribir.clicked.connect(self._on_sobrescribir)
        btn_aplicar.clicked.connect(self._on_aplicar)
        btn_mover.clicked.connect(self._on_mover_a_carpeta)
        btn_borrar.clicked.connect(self._on_borrar)

        # Dos filas de tres: seis botones en una sola fila quedaban ilegibles
        # en esta columna.
        botones = QGridLayout()
        botones.addWidget(btn_guardar, 0, 0)
        botones.addWidget(btn_duplicar, 0, 1)
        botones.addWidget(btn_sobrescribir, 0, 2)
        botones.addWidget(btn_aplicar, 1, 0)
        botones.addWidget(btn_mover, 1, 1)
        botones.addWidget(btn_borrar, 1, 2)

        layout = QVBoxLayout(self)
        layout.addLayout(fila_filtro)
        layout.addWidget(self.lista)
        layout.addLayout(botones)

        self._refrescar_filtro_carpetas()
        self._refrescar_lista()

    # ------------------------------------------------------------------
    # SEGMENTO: CARPETAS
    # ------------------------------------------------------------------
    def _carpetas_disponibles(self):
        """Carpetas creadas a mano + las que ya usa alguna pose, sin repetir."""
        nombres = set(self._carpetas_guardadas)
        nombres.update(c for c in self.carpetas.values() if c)
        return sorted(nombres)

    def _refrescar_filtro_carpetas(self):
        # Se bloquean las señales porque clear() dispara currentIndexChanged, y
        # eso rearmaria la lista a mitad de camino (y podria aplicar una pose
        # sin que el usuario haya hecho click en nada).
        seleccion = self.combo_filtro.currentData()
        self.combo_filtro.blockSignals(True)
        self.combo_filtro.clear()
        self.combo_filtro.addItem("Todas", FILTRO_TODAS)
        self.combo_filtro.addItem("Sin carpeta", FILTRO_SIN_CARPETA)
        for carpeta in self._carpetas_disponibles():
            self.combo_filtro.addItem(carpeta, carpeta)
        indice = self.combo_filtro.findData(seleccion) if seleccion else -1
        self.combo_filtro.setCurrentIndex(indice if indice >= 0 else 0)
        self.combo_filtro.blockSignals(False)

    def _registrar_carpeta(self, carpeta):
        if carpeta and carpeta not in self._carpetas_guardadas:
            self._carpetas_guardadas.append(carpeta)
            storage.guardar_carpetas(self._carpetas_disponibles())

    def _on_nueva_carpeta(self):
        carpeta, ok = QInputDialog.getText(self, "Nueva carpeta", "Nombre de la carpeta:")
        if not ok or not carpeta.strip():
            return
        carpeta = carpeta.strip()
        self._registrar_carpeta(carpeta)
        self._refrescar_filtro_carpetas()
        indice = self.combo_filtro.findData(carpeta)
        if indice >= 0:
            self.combo_filtro.setCurrentIndex(indice)

    def _on_filtro_cambiado(self, _indice):
        self._refrescar_lista()

    def _on_mover_a_carpeta(self):
        nombre = self.nombre_seleccionado()
        if not nombre:
            QMessageBox.information(self, "Selecciona una pose", "Selecciona primero la pose que quieres mover.")
            return
        opciones = ["(sin carpeta)"] + self._carpetas_disponibles()
        actual = self.carpetas.get(nombre, "")
        indice = opciones.index(actual) if actual in opciones else 0
        elegida, ok = QInputDialog.getItem(
            self, "Mover a carpeta", f"¿A que carpeta va '{nombre}'?", opciones, indice, True
        )
        if not ok:
            return
        elegida = "" if elegida.strip() == "(sin carpeta)" else elegida.strip()
        self.carpetas[nombre] = elegida
        storage.guardar_posicion(nombre, self.posiciones[nombre], elegida)
        self._registrar_carpeta(elegida)
        self._refrescar_filtro_carpetas()
        self._refrescar_lista(seleccionar=nombre)

    # ------------------------------------------------------------------
    # SEGMENTO: LISTA
    # ------------------------------------------------------------------
    def _nombres_visibles(self):
        filtro = self.combo_filtro.currentData()
        if filtro == FILTRO_SIN_CARPETA:
            nombres = [n for n in self.posiciones if not self.carpetas.get(n)]
        elif filtro and filtro != FILTRO_TODAS:
            nombres = [n for n in self.posiciones if self.carpetas.get(n) == filtro]
        else:
            nombres = list(self.posiciones)
        return sorted(nombres)

    def _refrescar_lista(self, seleccionar=None):
        # Señales bloqueadas: tanto clear() como setCurrentRow() disparan
        # currentItemChanged, y eso aplicaria una pose al robot sin que el
        # usuario la haya elegido (por ejemplo, al cambiar el filtro).
        anterior = seleccionar or self.nombre_seleccionado()
        self.lista.blockSignals(True)
        self.lista.clear()
        self.lista.addItems(self._nombres_visibles())
        if anterior:
            encontrado = self.lista.findItems(anterior, Qt.MatchExactly)
            if encontrado:
                self.lista.setCurrentItem(encontrado[0])
        self.lista.blockSignals(False)

    def nombre_seleccionado(self):
        """Nombre de la pose seleccionada, o None. Lo usa el panel de pasos."""
        item = self.lista.currentItem()
        return item.text() if item else None

    def angulos_de(self, nombre):
        return self.posiciones.get(nombre)

    # ------------------------------------------------------------------
    # SEGMENTO: GUARDAR, DUPLICAR, RENOMBRAR
    # ------------------------------------------------------------------
    def _nombre_repetido(self, nombre, excepto=None):
        """True (y avisa) si ya existe otra pose con ese nombre."""
        if nombre in self.posiciones and nombre != excepto:
            QMessageBox.warning(
                self, "Nombre repetido",
                f"Ya existe una pose llamada '{nombre}'. Elige otro nombre.",
            )
            return True
        return False

    def guardar_captura(self, angulos):
        """Guarda los angulos actuales de los sliders como una pose nueva."""
        # La carpeta del filtro activo viene precargada: si estas trabajando
        # dentro de "Intento 3", lo normal es que la pose nueva vaya ahi.
        filtro = self.combo_filtro.currentData()
        carpeta_sugerida = filtro if filtro not in (FILTRO_TODAS, FILTRO_SIN_CARPETA) else ""
        dialogo = DialogoPose("Guardar pose", "", carpeta_sugerida, self._carpetas_disponibles(), self)
        if not dialogo.exec():
            return
        nombre, carpeta = dialogo.valores()
        if not nombre or self._nombre_repetido(nombre):
            return
        self._guardar(nombre, angulos, carpeta)

    def _on_duplicar(self):
        nombre = self.nombre_seleccionado()
        if not nombre:
            QMessageBox.information(self, "Selecciona una pose", "Selecciona primero la pose que quieres duplicar.")
            return
        dialogo = DialogoPose(
            "Duplicar pose", f"{nombre} copia", self.carpetas.get(nombre, ""), self._carpetas_disponibles(), self
        )
        if not dialogo.exec():
            return
        nuevo, carpeta = dialogo.valores()
        if not nuevo or self._nombre_repetido(nuevo):
            return
        # dict(...): una copia de los angulos, no la misma referencia -- si no,
        # sobrescribir la copia cambiaria tambien la pose original en memoria.
        self._guardar(nuevo, dict(self.posiciones[nombre]), carpeta)

    def _on_doble_click(self, item):
        viejo = item.text()
        nuevo, ok = QInputDialog.getText(self, "Renombrar pose", "Nuevo nombre:", text=viejo)
        if not ok:
            return
        nuevo = nuevo.strip()
        if not nuevo or nuevo == viejo or self._nombre_repetido(nuevo, excepto=viejo):
            return
        carpeta = self.carpetas.pop(viejo, "")
        angulos = self.posiciones.pop(viejo)
        storage.renombrar_posicion(viejo, nuevo, angulos, carpeta)
        self.posiciones[nuevo] = angulos
        self.carpetas[nuevo] = carpeta
        self._refrescar_lista(seleccionar=nuevo)
        # Primero se avisa del renombre (para que las secuencias que usaban el
        # nombre viejo queden apuntando al nuevo) y recien despues del cambio
        # de lista: al reves, la lista de pasos se redibujaria todavia con el
        # nombre viejo.
        self.pose_renombrada.emit(viejo, nuevo)
        self.lista_cambiada.emit()

    def _guardar(self, nombre, angulos, carpeta):
        storage.guardar_posicion(nombre, angulos, carpeta)
        self.posiciones[nombre] = angulos
        self.carpetas[nombre] = carpeta
        self._registrar_carpeta(carpeta)
        self._refrescar_filtro_carpetas()
        self._refrescar_lista(seleccionar=nombre)
        self.lista_cambiada.emit()

    def sobrescribir(self, nombre, angulos):
        storage.guardar_posicion(nombre, angulos, self.carpetas.get(nombre, ""))
        self.posiciones[nombre] = angulos
        self.lista_cambiada.emit()

    def importar_posiciones(self, nuevas, carpetas_importadas=None):
        """Agrega/reemplaza poses desde un archivo importado (ver 'Importar movimientos').
        Sobrescribe sin preguntar por nombre repetido -- es una importacion masiva,
        no un guardado individual."""
        carpetas_importadas = carpetas_importadas or {}
        for nombre, angulos in nuevas.items():
            # Si el archivo no trae carpeta para esa pose, se respeta la que ya
            # tenia aca (no se la saca de su carpeta por reimportarla).
            carpeta = carpetas_importadas.get(nombre, self.carpetas.get(nombre, ""))
            storage.guardar_posicion(nombre, angulos, carpeta)
            self.posiciones[nombre] = angulos
            self.carpetas[nombre] = carpeta
            self._registrar_carpeta(carpeta)
        self._refrescar_filtro_carpetas()
        self._refrescar_lista()
        self.lista_cambiada.emit()

    # ------------------------------------------------------------------
    # SEGMENTO: APLICAR Y BORRAR
    # ------------------------------------------------------------------
    def _on_sobrescribir(self):
        nombre = self.nombre_seleccionado()
        if not nombre:
            QMessageBox.information(self, "Selecciona una pose", "Selecciona primero la pose que quieres sobrescribir.")
            return
        self.solicitar_sobrescritura.emit(nombre)

    def _on_aplicar(self):
        nombre = self.nombre_seleccionado()
        if not nombre:
            return
        self.posicion_aplicada.emit(self.posiciones[nombre])

    def _on_seleccion_cambiada(self, actual, anterior):
        if not actual:
            return
        self.posicion_aplicada.emit(self.posiciones[actual.text()])

    def _on_click_en_pose(self, item):
        # Solo pasa cuando el item clickeado YA era el seleccionado (si no,
        # currentItemChanged ya disparo arriba).
        self.posicion_aplicada.emit(self.posiciones[item.text()])

    def _on_borrar(self):
        nombre = self.nombre_seleccionado()
        if not nombre:
            return
        respuesta = QMessageBox.question(self, "Borrar pose", f"¿Borrar la pose '{nombre}'?")
        if respuesta == QMessageBox.Yes:
            storage.borrar_posicion(nombre)
            del self.posiciones[nombre]
            self.carpetas.pop(nombre, None)
            self._refrescar_lista()
            self.lista_cambiada.emit()
