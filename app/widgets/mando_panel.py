"""SEGMENTO: PANEL DE MANDO
Todos los botones del mando (distribucion tipo Xbox, como el EasySMX D10),
dibujados en el lugar que ocupan en el mando fisico. Cada uno tiene un
desplegable para elegir que hace: una secuencia, una pose o un comando del
robot (Inicio, relajar, balance, nivelar, caras...). Para las secuencias se
elige ademas si se repite mientras el boton esta apretado o si corre una vez.

Mientras el robot este conectado y mande MANDO_BOTON / MANDO_DPAD, la tarjeta
del boton apretado se ilumina: asi se reconoce cada boton del mando real sin
adivinar como lo llama el firmware.

Formato guardado (asignaciones_mando.json, version 2):
  {"version": 2, "botones": {"A": {"tipo": "secuencia", "valor": "Caminar", "repetir": true}, ...}}
tipo: "secuencia" | "pose" | "comando". El formato viejo ({"ARRIBA": "secuencia"}) se convierte solo.
"""

import storage
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# SEGMENTO: BOTONES DEL MANDO
# clave (la que usara el firmware), etiqueta, descripcion corta
# ---------------------------------------------------------------------------
GATILLOS_IZQ = (("LT", "LT", "Gatillo izquierdo"), ("LB", "LB", "Bumper izquierdo"))
GATILLOS_DER = (("RB", "RB", "Bumper derecho"), ("RT", "RT", "Gatillo derecho"))
CENTRO = (("VIEW", "View", "Botón de dos cuadros"), ("HOME", "Home", "Botón central"), ("MENU", "Menu", "Botón de tres rayas"))
# (clave, etiqueta, descripcion, fila, columna) dentro de una cruz de 3x3
CRUCETA = (
    ("DPAD_ARRIBA", "▲", "Cruceta arriba", 0, 1),
    ("DPAD_IZQUIERDA", "◀", "Cruceta izquierda", 1, 0),
    ("DPAD_DERECHA", "▶", "Cruceta derecha", 1, 2),
    ("DPAD_ABAJO", "▼", "Cruceta abajo", 2, 1),
)
FRONTALES = (
    ("Y", "Y", "Botón Y", 0, 1),
    ("X", "X", "Botón X", 1, 0),
    ("B", "B", "Botón B", 1, 2),
    ("A", "A", "Botón A", 2, 1),
)


def _palanca(prefijo, nombre):
    return (
        (f"{prefijo}_ARRIBA", "▲", f"{nombre} arriba", 0, 1),
        (f"{prefijo}_IZQUIERDA", "◀", f"{nombre} izquierda", 1, 0),
        (f"{prefijo}_CLICK", "●", f"Apretar {nombre.lower()}", 1, 1),
        (f"{prefijo}_DERECHA", "▶", f"{nombre} derecha", 1, 2),
        (f"{prefijo}_ABAJO", "▼", f"{nombre} abajo", 2, 1),
    )


PALANCA_IZQ = _palanca("LS", "Palanca izq.")
PALANCA_DER = _palanca("RS", "Palanca der.")

# Comandos del robot que se pueden poner en un boton (texto visible, comando)
COMANDOS = (
    ("Ir a Inicio", "HOME"),
    ("Relajar servos", "RELAX"),
    ("Parar (STOP)", "STOP"),
    ("Reanudar", "RESUME"),
    ("Balance encendido", "BALANCE,ON"),
    ("Balance apagado", "BALANCE,OFF"),
    ("Nivelar torso", "NIVELAR"),
    ("Cara feliz", "CARA,FELIZ"),
    ("Cara triste", "CARA,TRISTE"),
    ("Cara sorpresa", "CARA,SORPRESA"),
    ("Cara neutral", "CARA,NEUTRAL"),
)
NADA = ""


def _dato(tipo, valor):
    return f"{tipo}|{valor}"


def _partir(dato):
    tipo, _, valor = (dato or "").partition("|")
    return tipo, valor


DPAD_VIEJO = {"ARRIBA": "DPAD_ARRIBA", "ABAJO": "DPAD_ABAJO", "IZQUIERDA": "DPAD_IZQUIERDA", "DERECHA": "DPAD_DERECHA"}


def _normalizar(datos):
    """Convierte el formato viejo (solo D-pad -> nombre de secuencia) al nuevo."""
    if isinstance(datos, dict) and datos.get("version") == 2:
        return dict(datos.get("botones", {}))
    botones = {}
    for clave, nombre in (datos or {}).items():
        if clave in DPAD_VIEJO and isinstance(nombre, str) and nombre:
            botones[DPAD_VIEJO[clave]] = {"tipo": "secuencia", "valor": nombre, "repetir": True}
    return botones


# ---------------------------------------------------------------------------
# SEGMENTO: TARJETA DE UN BOTON
# ---------------------------------------------------------------------------
class _TarjetaBoton(QFrame):
    """Etiqueta del boton + que hace + (solo secuencias) si se repite mientras se mantiene."""

    def __init__(self, clave, etiqueta, descripcion, al_cambiar, parent=None):
        super().__init__(parent)
        self.clave = clave
        self.setObjectName("tarjetaDireccion")
        self.setProperty("activo", False)
        self.setToolTip(descripcion)

        label = QLabel(etiqueta)
        label.setObjectName("flechaDpad")
        label.setAlignment(Qt.AlignCenter)

        self.combo = QComboBox()
        self.combo.setMinimumWidth(120)
        self.combo.setToolTip(f"{descripcion}: qué hace el robot")
        self.combo.currentIndexChanged.connect(self._actualizar_repetir)
        self.combo.currentIndexChanged.connect(al_cambiar)

        self.repetir = QCheckBox("Repetir al mantener")
        self.repetir.setChecked(True)
        self.repetir.setVisible(False)
        self.repetir.toggled.connect(al_cambiar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        layout.addWidget(label)
        layout.addWidget(self.combo)
        layout.addWidget(self.repetir)

    def _actualizar_repetir(self):
        tipo, _ = _partir(self.combo.currentData())
        self.repetir.setVisible(tipo == "secuencia")

    def rellenar(self, secuencias, poses, asignada):
        """Carga las opciones y marca la asignada; si apunta a algo borrado lo muestra como roto."""
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem("— nada —", NADA)
        for nombre in secuencias:
            self.combo.addItem(f"Secuencia: {nombre}", _dato("secuencia", nombre))
        for nombre in poses:
            self.combo.addItem(f"Pose: {nombre}", _dato("pose", nombre))
        for texto, comando in COMANDOS:
            self.combo.addItem(texto, _dato("comando", comando))
        roto = False
        if asignada:
            valor = asignada.get("valor", "")
            indice = self.combo.findData(_dato(asignada.get("tipo", ""), valor))
            if indice < 0:
                self.combo.addItem(f"⚠ {valor} (ya no existe)", _dato("roto", valor))
                indice = self.combo.count() - 1
                roto = True
            self.combo.setCurrentIndex(indice)
            self.repetir.setChecked(bool(asignada.get("repetir", True)))
        self.combo.blockSignals(False)
        self._actualizar_repetir()
        return roto

    def asignacion(self):
        tipo, valor = _partir(self.combo.currentData())
        if not tipo:
            return None
        datos = {"tipo": tipo, "valor": valor}
        if tipo == "secuencia":
            datos["repetir"] = self.repetir.isChecked()
        return datos

    def iluminar(self, activo):
        self.setProperty("activo", activo)
        self.style().unpolish(self)
        self.style().polish(self)


class MandoPanel(QWidget):
    def __init__(self, sequence_panel, positions_panel, parent=None):
        super().__init__(parent)
        self._sequence_panel = sequence_panel
        self._positions_panel = positions_panel
        self.asignaciones = _normalizar(storage.cargar_asignaciones_mando())
        self.tarjetas = {}

        # SEGMENTO: ENCABEZADO -------------------------------------------
        titulo = QLabel("Mando")
        titulo.setObjectName("tituloSeccion")
        subtitulo = QLabel("Elige qué hace el robot con cada botón. Con el robot conectado, el botón que aprietes se ilumina.")
        subtitulo.setObjectName("textoSecundario")
        self.label_conexion = QLabel("Mando: sin datos del robot")
        self.label_conexion.setObjectName("textoSecundario")

        # SEGMENTO: DIBUJO DEL MANDO -------------------------------------
        mando = QGridLayout()
        mando.setHorizontalSpacing(18)
        mando.setVerticalSpacing(18)
        mando.addLayout(self._fila(GATILLOS_IZQ), 0, 0)
        mando.addLayout(self._fila(GATILLOS_DER), 0, 2)
        # los botones del centro van en columna entre las dos mitades: en fila ensanchaban todo el panel
        mando.addLayout(self._columna(CENTRO), 1, 1, 2, 1, Qt.AlignTop)
        mando.addWidget(self._grupo("Cruceta", CRUCETA), 1, 0)
        mando.addWidget(self._grupo("Botones", FRONTALES), 1, 2)
        mando.addWidget(self._grupo("Palanca izquierda", PALANCA_IZQ), 2, 0)
        mando.addWidget(self._grupo("Palanca derecha", PALANCA_DER), 2, 2)

        contenido = QWidget()
        contenido.setLayout(mando)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(contenido)

        # SEGMENTO: GUARDAR Y ESTADO -------------------------------------
        self.label_estado = QLabel("")
        self.label_estado.setObjectName("textoSecundario")
        self.btn_guardar = QPushButton("Guardar asignación")
        self.btn_guardar.setObjectName("botonPrimario")
        self.btn_guardar.clicked.connect(self._guardar)
        fila_guardar = QHBoxLayout()
        fila_guardar.addWidget(self.label_conexion)
        fila_guardar.addStretch()
        fila_guardar.addWidget(self.label_estado)
        fila_guardar.addSpacing(12)
        fila_guardar.addWidget(self.btn_guardar)

        aviso = QLabel("El robot todavía no ejecuta esta asignación: falta el Bluetooth del mando en el firmware del ESP32.")
        aviso.setObjectName("avisoInfo")
        aviso.setWordWrap(True)

        # SEGMENTO: ARMADO -----------------------------------------------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(4)
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        layout.addSpacing(12)
        layout.addWidget(scroll, 1)
        layout.addSpacing(8)
        layout.addLayout(fila_guardar)
        layout.addWidget(aviso)

        self._cargando = False
        self.refrescar_secuencias()

    # ------------------------------------------------------------------
    # SEGMENTO: CONSTRUCCION DE GRUPOS
    # ------------------------------------------------------------------
    def _tarjeta(self, clave, etiqueta, descripcion):
        tarjeta = _TarjetaBoton(clave, etiqueta, descripcion, self._marcar_sin_guardar)
        self.tarjetas[clave] = tarjeta
        return tarjeta

    def _fila(self, botones):
        fila = QHBoxLayout()
        fila.setSpacing(12)
        for clave, etiqueta, descripcion in botones:
            fila.addWidget(self._tarjeta(clave, etiqueta, descripcion))
        return fila

    def _columna(self, botones):
        columna = QVBoxLayout()
        columna.setSpacing(10)
        for clave, etiqueta, descripcion in botones:
            columna.addWidget(self._tarjeta(clave, etiqueta, descripcion))
        return columna

    def _grupo(self, nombre, botones):
        caja = QWidget()
        rejilla = QGridLayout(caja)
        rejilla.setContentsMargins(0, 0, 0, 0)
        rejilla.setSpacing(10)
        titulo = QLabel(nombre)
        titulo.setObjectName("tituloDireccion")
        rejilla.addWidget(titulo, 0, 0, 1, 3)
        for clave, etiqueta, descripcion, fila, columna in botones:
            rejilla.addWidget(self._tarjeta(clave, etiqueta, descripcion), fila + 1, columna)
        return caja

    # ------------------------------------------------------------------
    # SEGMENTO: SINCRONIZACION CON SECUENCIAS Y POSES GUARDADAS
    # ------------------------------------------------------------------
    def refrescar_secuencias(self):
        secuencias = sorted(self._sequence_panel.secuencias.keys())
        poses = sorted(self._positions_panel.posiciones.keys())
        self._cargando = True
        rotas = [clave for clave, tarjeta in self.tarjetas.items()
                 if tarjeta.rellenar(secuencias, poses, self.asignaciones.get(clave))]
        self._cargando = False
        if rotas:
            self._poner_estado(f"Botones que apuntan a algo borrado: {', '.join(rotas)}", "avisoAtencion")
        else:
            self._poner_estado("", "textoSecundario")

    def _marcar_sin_guardar(self, *_):
        if not self._cargando:
            self._poner_estado("Cambios sin guardar", "avisoAtencion")

    def _poner_estado(self, texto, nombre_estilo):
        self.label_estado.setText(texto)
        self.label_estado.setObjectName(nombre_estilo)
        self.label_estado.style().unpolish(self.label_estado)
        self.label_estado.style().polish(self.label_estado)

    # ------------------------------------------------------------------
    # SEGMENTO: MENSAJES DEL ROBOT (boton apretado y conexion del mando)
    # ------------------------------------------------------------------
    def procesar_linea(self, texto):
        """Devuelve True si la linea era del mando (no hace falta mostrarla en la consola)."""
        if texto.startswith(("MANDO_BOTON,", "MANDO_DPAD,")):
            partes = texto.split(",")
            if len(partes) >= 3:
                clave = partes[1] if partes[0] == "MANDO_BOTON" else DPAD_VIEJO.get(partes[1], partes[1])
                tarjeta = self.tarjetas.get(clave)
                if tarjeta:
                    tarjeta.iluminar(partes[2] == "presionado")
            return True
        if texto.startswith("MANDO_EMPAREJADO,"):
            self.label_conexion.setText(f"Mando conectado: {texto.split(',', 1)[1]}")
        elif texto.startswith("MANDO_DESCONECTADO"):
            self.label_conexion.setText("Mando desconectado")
        return False

    # ------------------------------------------------------------------
    # SEGMENTO: GUARDADO
    # ------------------------------------------------------------------
    def _guardar(self):
        botones = {}
        rotas = []
        for clave, tarjeta in self.tarjetas.items():
            datos = tarjeta.asignacion()
            if not datos:
                continue
            if datos["tipo"] == "roto":
                rotas.append(clave)
                continue
            botones[clave] = datos
        if rotas:
            respuesta = QMessageBox.question(
                self,
                "Asignaciones rotas",
                f"{', '.join(rotas)} apunta(n) a algo que ya no existe.\n\nSi continúas, quedan sin asignar. ¿Guardar igual?",
            )
            if respuesta != QMessageBox.Yes:
                return
        storage.guardar_asignaciones_mando({"version": 2, "botones": botones})
        self.asignaciones = botones
        self.refrescar_secuencias()
        self._poner_estado("Guardado", "textoSecundario")
