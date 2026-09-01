"""SEGMENTO: PANEL DE POSES
Guardar la pose actual, aplicar una guardada, o borrarla.
"""

import storage
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.posiciones = storage.cargar_posiciones()
        # True desde que el usuario mueve un slider a mano hasta que guarda o
        # aplica algo. Mientras este en True, seleccionar otra pose en la
        # lista NO la aplica -- solo se revierte la seleccion visualmente
        # (ver _on_seleccion_cambiada), para que un click accidental en la
        # lista no pise un ajuste que todavia no se guardo.
        self._hay_ediciones_sin_guardar = False

        self.lista = QListWidget()
        self.lista.setToolTip(
            "Tus poses guardadas. Selecciona una para aplicarla (sliders y robot). "
            "Si estas editando sliders sin guardar todavia, seleccionar otra pose "
            "no te los pisa -- guarda o sobrescribe primero."
        )
        # Dos señales: currentItemChanged cubre cambiar a OTRA pose (mouse o
        # teclado); itemClicked cubre volver a hacer click en la que YA
        # estaba seleccionada (Qt no dispara currentItemChanged en ese caso,
        # y sin esto un click de mas se sentia "bloqueado", sin reaccionar).
        # Las dos respetan _hay_ediciones_sin_guardar por igual.
        self.lista.currentItemChanged.connect(self._on_seleccion_cambiada)
        self.lista.itemClicked.connect(self._on_click_en_pose)
        self._refrescar_lista()

        btn_guardar = QPushButton("Guardar como nueva")
        btn_guardar.setToolTip("Guarda la posicion actual de los sliders como una pose con nombre nuevo.")
        btn_sobrescribir = QPushButton("Sobrescribir")
        btn_sobrescribir.setToolTip("Reemplaza la pose seleccionada en la lista con la posicion actual de los sliders.")
        btn_aplicar = QPushButton("Aplicar")
        btn_aplicar.setToolTip("Mueve los sliders (y el robot, si esta conectado) a la pose seleccionada.")
        btn_borrar = QPushButton("Borrar")
        btn_borrar.setToolTip("Elimina la pose seleccionada.")

        btn_guardar.clicked.connect(lambda: self.solicitar_captura.emit())
        btn_sobrescribir.clicked.connect(self._on_sobrescribir)
        btn_aplicar.clicked.connect(self._on_aplicar)
        btn_borrar.clicked.connect(self._on_borrar)

        botones = QHBoxLayout()
        botones.addWidget(btn_guardar)
        botones.addWidget(btn_sobrescribir)
        botones.addWidget(btn_aplicar)
        botones.addWidget(btn_borrar)

        layout = QVBoxLayout(self)
        layout.addWidget(self.lista)
        layout.addLayout(botones)

    def _refrescar_lista(self):
        self.lista.clear()
        self.lista.addItems(sorted(self.posiciones.keys()))

    def nombres(self):
        return sorted(self.posiciones.keys())

    def angulos_de(self, nombre):
        return self.posiciones.get(nombre)

    def marcar_edicion_pendiente(self):
        """Llamado desde afuera cuando el usuario mueve un slider a mano."""
        self._hay_ediciones_sin_guardar = True

    def _limpiar_edicion_pendiente(self):
        self._hay_ediciones_sin_guardar = False

    def guardar_captura(self, angulos):
        nombre, ok = QInputDialog.getText(self, "Guardar pose", "Nombre de la pose:")
        if not ok or not nombre.strip():
            return
        nombre = nombre.strip()
        if nombre in self.posiciones:
            respuesta = QMessageBox.question(
                self, "La pose ya existe", f"Ya existe una pose llamada '{nombre}'. ¿Reemplazarla?"
            )
            if respuesta != QMessageBox.Yes:
                return
        storage.guardar_posicion(nombre, angulos)
        self.posiciones[nombre] = angulos
        self._refrescar_lista()
        self._limpiar_edicion_pendiente()
        self.lista_cambiada.emit()

    def sobrescribir(self, nombre, angulos):
        storage.guardar_posicion(nombre, angulos)
        self.posiciones[nombre] = angulos
        self._limpiar_edicion_pendiente()
        self.lista_cambiada.emit()

    def _on_sobrescribir(self):
        item = self.lista.currentItem()
        if not item:
            QMessageBox.information(self, "Selecciona una pose", "Selecciona primero la pose que quieres sobrescribir.")
            return
        self.solicitar_sobrescritura.emit(item.text())

    def _on_aplicar(self):
        item = self.lista.currentItem()
        if not item:
            return
        self._limpiar_edicion_pendiente()
        self.posicion_aplicada.emit(self.posiciones[item.text()])

    def _on_seleccion_cambiada(self, actual, anterior):
        if not actual:
            return
        if self._hay_ediciones_sin_guardar:
            # Hay un ajuste de slider sin guardar: no lo pisamos. Se revierte
            # la seleccion visual al item de antes, para que "Sobrescribir"
            # siga apuntando a la pose correcta.
            self.lista.blockSignals(True)
            self.lista.setCurrentItem(anterior)  # anterior puede ser None, y eso tambien esta bien
            self.lista.blockSignals(False)
            return
        self.posicion_aplicada.emit(self.posiciones[actual.text()])

    def _on_click_en_pose(self, item):
        # Solo pasa cuando el item clickeado YA era el seleccionado (si no,
        # currentItemChanged ya disparo arriba, incluido el revertir si hacia
        # falta). Mismo chequeo de ediciones sin guardar, por si estan
        # editando esta misma pose y la re-clickean sin querer.
        if self._hay_ediciones_sin_guardar:
            return
        self.posicion_aplicada.emit(self.posiciones[item.text()])

    def _on_borrar(self):
        item = self.lista.currentItem()
        if not item:
            return
        nombre = item.text()
        respuesta = QMessageBox.question(self, "Borrar pose", f"¿Borrar la pose '{nombre}'?")
        if respuesta == QMessageBox.Yes:
            storage.borrar_posicion(nombre)
            del self.posiciones[nombre]
            self._refrescar_lista()
            self.lista_cambiada.emit()
