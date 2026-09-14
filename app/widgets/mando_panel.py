"""SEGMENTO: PANEL DE MANDO
Define que secuencia guardada le corresponde a cada direccion del D-pad de
un mando tipo Xbox. Es solo la asignacion -- la conexion Bluetooth real
entre el mando y el robot todavia no esta implementada en el firmware del
ESP32 (queda como siguiente etapa, aparte de esta app), asi que por ahora
esta pantalla solo guarda localmente que secuencia va en cada direccion,
lista para cuando esa parte del firmware exista.

Las cuatro direcciones se dibujan en cruz, imitando la cruceta fisica del
mando, para que se lea de un vistazo cual es cual sin ir leyendo etiqueta
por etiqueta.
"""

import storage
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# clave, flecha, titulo, gesto que representa, y su casilla (fila, columna)
# dentro de la cruz de 3x3.
DIRECCIONES = (
    ("ARRIBA", "▲", "Arriba", "Avanzar", 0, 1),
    ("IZQUIERDA", "◀", "Izquierda", "Girar a la izquierda", 1, 0),
    ("DERECHA", "▶", "Derecha", "Girar a la derecha", 1, 2),
    ("ABAJO", "▼", "Abajo", "Retroceder", 2, 1),
)
SIN_ASIGNAR = "(sin asignar)"
PREFIJO_ROTA = "⚠ "  # marca una asignacion que apunta a una secuencia borrada


class _TarjetaDireccion(QFrame):
    """Una casilla de la cruceta: flecha, direccion, el gesto que representa,
    y el desplegable con la secuencia asignada."""

    def __init__(self, flecha, titulo, gesto, parent=None):
        super().__init__(parent)
        self.setObjectName("tarjetaDireccion")

        label_flecha = QLabel(flecha)
        label_flecha.setObjectName("flechaDpad")
        label_titulo = QLabel(titulo)
        label_titulo.setObjectName("tituloDireccion")

        encabezado = QHBoxLayout()
        encabezado.setSpacing(8)
        encabezado.addWidget(label_flecha)
        encabezado.addWidget(label_titulo)
        encabezado.addStretch()

        label_gesto = QLabel(gesto)
        label_gesto.setObjectName("textoSecundario")

        self.combo = QComboBox()
        self.combo.setMinimumWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        layout.addLayout(encabezado)
        layout.addWidget(label_gesto)
        layout.addWidget(self.combo)


class MandoPanel(QWidget):
    def __init__(self, sequence_panel, parent=None):
        super().__init__(parent)
        self._sequence_panel = sequence_panel
        self.asignaciones = storage.cargar_asignaciones_mando()
        self._cargando = False  # evita marcar "sin guardar" al rellenar los combos

        # SEGMENTO: ENCABEZADO -------------------------------------------
        titulo = QLabel("Mando")
        titulo.setObjectName("tituloSeccion")
        subtitulo = QLabel("Qué secuencia ejecuta el robot con cada dirección del D-pad.")
        subtitulo.setObjectName("textoSecundario")

        # SEGMENTO: CRUCETA DEL D-PAD ------------------------------------
        cruceta = QGridLayout()
        cruceta.setHorizontalSpacing(14)
        cruceta.setVerticalSpacing(14)

        self.tarjetas = {}
        self.combos = {}  # clave -> QComboBox (misma API que antes)
        for clave, flecha, titulo_dir, gesto, fila, columna in DIRECCIONES:
            tarjeta = _TarjetaDireccion(flecha, titulo_dir, gesto)
            tarjeta.combo.currentTextChanged.connect(self._marcar_sin_guardar)
            self.tarjetas[clave] = tarjeta
            self.combos[clave] = tarjeta.combo
            cruceta.addWidget(tarjeta, fila, columna)

        contenedor_cruceta = QWidget()
        contenedor_cruceta.setLayout(cruceta)

        fila_centrada = QHBoxLayout()
        fila_centrada.addStretch()
        fila_centrada.addWidget(contenedor_cruceta)
        fila_centrada.addStretch()

        # SEGMENTO: GUARDAR Y ESTADO -------------------------------------
        self.label_estado = QLabel("")
        self.label_estado.setObjectName("textoSecundario")
        self.label_estado.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.btn_guardar = QPushButton("Guardar asignación")
        self.btn_guardar.setObjectName("botonPrimario")
        self.btn_guardar.clicked.connect(self._guardar)

        fila_guardar = QHBoxLayout()
        fila_guardar.addStretch()
        fila_guardar.addWidget(self.label_estado)
        fila_guardar.addSpacing(12)
        fila_guardar.addWidget(self.btn_guardar)
        fila_guardar.addStretch()

        # Una sola linea, abajo y discreta: antes era un parrafo de cuatro
        # renglones arriba de todo, que dominaba la pantalla entera.
        aviso = QLabel(
            "El robot todavía no lee esta asignación: falta implementar el Bluetooth "
            "del mando en el firmware del ESP32."
        )
        aviso.setObjectName("avisoInfo")
        aviso.setWordWrap(True)

        # SEGMENTO: ARMADO -----------------------------------------------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(4)
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        layout.addSpacing(24)
        layout.addLayout(fila_centrada)
        layout.addSpacing(20)
        layout.addLayout(fila_guardar)
        layout.addStretch()
        layout.addWidget(aviso)

        self.refrescar_secuencias()

    # ------------------------------------------------------------------
    # SEGMENTO: SINCRONIZACION CON LAS SECUENCIAS GUARDADAS
    # ------------------------------------------------------------------
    def refrescar_secuencias(self):
        nombres = sorted(self._sequence_panel.secuencias.keys())
        hay_rotas = False

        self._cargando = True
        for clave, combo in self.combos.items():
            asignada = self.asignaciones.get(clave, "")
            combo.clear()
            combo.addItem(SIN_ASIGNAR)
            combo.addItems(nombres)

            if not asignada:
                combo.setCurrentIndex(0)
                continue

            indice = combo.findText(asignada)
            if indice >= 0:
                combo.setCurrentIndex(indice)
                continue

            # La secuencia asignada ya no existe (se borro o se renombro).
            # Antes esto caia en silencio a "(sin asignar)" mientras el archivo
            # seguia guardando el nombre viejo: la pantalla y el archivo decian
            # cosas distintas y el usuario no se enteraba. Ahora se muestra la
            # asignacion rota como tal, para que se vea y se pueda corregir.
            combo.addItem(f"{PREFIJO_ROTA}{asignada} (ya no existe)")
            combo.setCurrentIndex(combo.count() - 1)
            hay_rotas = True
        self._cargando = False

        if hay_rotas:
            self._poner_estado("Hay asignaciones que apuntan a secuencias borradas", "avisoAtencion")
        else:
            self._poner_estado("", "textoSecundario")

    def _marcar_sin_guardar(self):
        if self._cargando:
            return
        self._poner_estado("Cambios sin guardar", "avisoAtencion")

    def _poner_estado(self, texto, nombre_estilo):
        self.label_estado.setText(texto)
        self.label_estado.setObjectName(nombre_estilo)
        # Cambiar objectName no vuelve a aplicar la hoja de estilos por si
        # solo: hay que pedirle a Qt que re-evalue el widget.
        self.label_estado.style().unpolish(self.label_estado)
        self.label_estado.style().polish(self.label_estado)

    # ------------------------------------------------------------------
    # SEGMENTO: GUARDADO
    # ------------------------------------------------------------------
    def _guardar(self):
        asignaciones = {}
        rotas = []
        for clave, combo in self.combos.items():
            texto = combo.currentText()
            if not texto or texto == SIN_ASIGNAR:
                continue
            if texto.startswith(PREFIJO_ROTA):
                rotas.append(clave.capitalize())
                continue
            asignaciones[clave] = texto

        if rotas:
            respuesta = QMessageBox.question(
                self,
                "Asignaciones rotas",
                f"{', '.join(rotas)} apunta(n) a una secuencia que ya no existe.\n\n"
                "Si continúas, esa(s) dirección(es) quedan sin asignar. ¿Guardar igual?",
            )
            if respuesta != QMessageBox.Yes:
                return

        storage.guardar_asignaciones_mando(asignaciones)
        self.asignaciones = asignaciones
        self.refrescar_secuencias()
        self._poner_estado("Guardado", "textoSecundario")
