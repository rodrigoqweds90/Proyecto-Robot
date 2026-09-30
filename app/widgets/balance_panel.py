"""SEGMENTO: PANEL DE BALANCE (MPU6050)
Todo el balance automatico en una pestaña: inclinacion en vivo, prenderlo o
apagarlo, cuanto corrige y el autoajuste. A proposito no hay que calibrar
nada a mano ni decirle hacia donde se mueve cada servo: el firmware aprende
el "derecho" solo y el autoajuste mide cuanto inclina el torso cada grupo
(ver SEGMENTO: BALANCE en main.cpp).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from widgets.attitude_indicator import AttitudeIndicator

# (clave, etiqueta, maximo, decimales, ayuda). Mismos rangos que valida el
# firmware en BALGAIN.
GANANCIAS = [
    ("kpRoll", "Fuerza lateral", 2, 2, "Qué parte de la inclinación lateral corrige (0.5 = la mitad)."),
    ("kdRoll", "Freno lateral", 0.5, 2, "Frena el vaivén lateral (segundos). Súbelo si oscila de lado a lado."),
    ("kpPitch", "Fuerza adelante/atrás", 2, 2, "Qué parte de la inclinación adelante/atrás corrige."),
    ("kdPitch", "Freno adelante/atrás", 0.5, 2, "Frena el cabeceo (segundos)."),
    ("maxUs", "Corrección máxima (us)", 400, 0, "Tope de corrección por servo, para que nunca haga un movimiento brusco."),
]
VALORES_BALCONF = 10  # 5 ganancias, autoajuste listo, 3 efectos, balance activo

# Canales que usa el firmware (CANAL_* en main.cpp), solo para mostrarlos.
GRUPOS = [("Caderas", (0, 15)), ("Pies", (3, 12)), ("Fémures", (1, 14))]


class BalancePanel(QWidget):
    comando = Signal(str)

    def __init__(self, servos, parent=None):
        super().__init__(parent)
        self._servos_por_canal = {}
        self._conectado = False
        self._emergencia = False
        self._mpu_disponible = None  # None = el robot todavia no lo informo
        self._config_recibida = False  # sin esto "Enviar ajustes" podria mandar los ceros iniciales
        self._autoajustando = False

        self.setLayout(self._construir())
        self.reconstruir(servos)
        self.set_conectado(False)

    # ------------------------------------------------------------------
    # SEGMENTO: CONSTRUCCION DE LA INTERFAZ
    # ------------------------------------------------------------------
    def _construir(self):
        # Estado en vivo
        self.indicador = AttitudeIndicator()
        self.label_sensor = QLabel("Sensor: sin conexión")
        self.label_sensor.setObjectName("textoSecundario")
        self.label_calibracion = QLabel("")
        self.label_calibracion.setObjectName("textoSecundario")
        self.label_calibracion.setWordWrap(True)
        self.label_correccion = QLabel("")
        self.label_correccion.setObjectName("valorServo")

        self.btn_balance = QPushButton("Activar balance")
        self.btn_balance.setObjectName("botonPrimario")
        self.btn_balance.setCheckable(True)
        self.btn_balance.toggled.connect(self._on_balance)
        self.btn_balance.setToolTip(
            "La primera vez se autoajusta solo (~17 s, parado en el piso en su pose de Inicio). "
            "Apágalo mientras creas poses con los sliders: si no, la corrección se suma a lo que ves."
        )
        self.btn_vivo = QPushButton("Ver inclinación en vivo")
        self.btn_vivo.setCheckable(True)
        self.btn_vivo.toggled.connect(self._on_vivo)
        self.btn_rumbo = QPushButton("Rumbo a cero")
        self.btn_rumbo.setToolTip("Pone en 0 el desvío acumulado. Úsalo antes de probar una caminata recta.")
        self.btn_rumbo.clicked.connect(lambda: self.comando.emit("RUMBO,0"))

        fila_botones = QHBoxLayout()
        fila_botones.addWidget(self.btn_balance)
        fila_botones.addWidget(self.btn_vivo)
        fila_botones.addWidget(self.btn_rumbo)
        fila_botones.addStretch()

        caja_vivo = QGroupBox("Inclinación del torso")
        layout_vivo = QVBoxLayout(caja_vivo)
        layout_vivo.addWidget(self.indicador, 1)
        layout_vivo.addWidget(self.label_correccion)
        layout_vivo.addWidget(self.label_sensor)
        layout_vivo.addWidget(self.label_calibracion)
        layout_vivo.addLayout(fila_botones)

        # Cuanto corrige
        self.spins = {}
        formulario = QFormLayout()
        for clave, etiqueta, maximo, decimales, ayuda in GANANCIAS:
            spin = QDoubleSpinBox()
            spin.setRange(0, maximo)
            spin.setDecimals(decimales)
            spin.setSingleStep(0.05 if maximo <= 2 else 10)
            spin.setToolTip(ayuda)
            self.spins[clave] = spin
            formulario.addRow(etiqueta, spin)
        self.btn_enviar_ajustes = QPushButton("Enviar ajustes")
        self.btn_enviar_ajustes.clicked.connect(self._enviar_ajustes)

        caja_ajustes = QGroupBox("Cuánto corrige")
        layout_ajustes = QVBoxLayout(caja_ajustes)
        layout_ajustes.addLayout(formulario)
        layout_ajustes.addWidget(self.btn_enviar_ajustes, 0, Qt.AlignLeft)

        # Autoajuste
        explicacion = QLabel(
            "Mueve caderas, pies y fémures unos 5° —siempre una pierna hacia adentro y la otra hacia afuera, "
            "así no chocan— y mide cuánto se inclina el torso. Con eso sabe solo hacia dónde corregir, "
            "sin importar cómo esté pegado el sensor. Se hace solo la primera vez que activas el balance."
        )
        explicacion.setObjectName("textoSecundario")
        explicacion.setWordWrap(True)
        self.label_servos = QLabel("")
        self.label_servos.setObjectName("textoSecundario")
        self.label_servos.setWordWrap(True)
        self.btn_autoajuste = QPushButton("Autoajustar ahora")
        self.btn_autoajuste.setToolTip("Parado en el piso, en su pose de Inicio y quieto.")
        self.btn_autoajuste.clicked.connect(lambda: self.comando.emit("AUTOAJUSTE"))
        self.label_auto = QLabel("")
        self.label_auto.setObjectName("avisoInfo")
        self.label_auto.setWordWrap(True)

        caja_auto = QGroupBox("Autoajuste")
        layout_auto = QVBoxLayout(caja_auto)
        layout_auto.addWidget(explicacion)
        layout_auto.addWidget(self.label_servos)
        layout_auto.addWidget(self.btn_autoajuste, 0, Qt.AlignLeft)
        layout_auto.addWidget(self.label_auto)
        layout_auto.addStretch()

        columna_derecha = QVBoxLayout()
        columna_derecha.addWidget(caja_ajustes)
        columna_derecha.addWidget(caja_auto, 1)

        layout_raiz = QHBoxLayout()
        layout_raiz.addWidget(caja_vivo, 1)
        layout_raiz.addLayout(columna_derecha, 1)
        return layout_raiz

    # ------------------------------------------------------------------
    # SEGMENTO: API PARA LA VENTANA PRINCIPAL
    # ------------------------------------------------------------------
    def reconstruir(self, servos):
        self._servos_por_canal = {s["canal"]: s for s in servos}
        partes = []
        for grupo, canales in GRUPOS:
            nombres = [self._servos_por_canal.get(c, {}).get("nombre", "sin nombre") + f" ({c})" for c in canales]
            partes.append(f"{grupo}: {', '.join(nombres)}")
        self.label_servos.setText("Servos que usa: " + " · ".join(partes))

    def set_conectado(self, conectado, emergencia=False):
        self._conectado = conectado
        self._emergencia = emergencia
        if not conectado:
            self._mpu_disponible = None
            self._config_recibida = False
            self._autoajustando = False
            self._marcar(self.btn_vivo, False)
            self._marcar(self.btn_balance, False)
            self.label_sensor.setText("Sensor: sin conexión")
            self.label_calibracion.setText("")
            self.label_correccion.setText("")
        self._actualizar_habilitados()

    def procesar_linea(self, texto):
        """Devuelve True si la linea no debe ir a la consola (telemetria a 10 Hz)."""
        if texto.startswith("ACT,"):
            self._on_actitud(texto)
            return True
        if texto.startswith("BALCONF,"):
            self._on_config(texto)
            return True
        if texto.startswith("MPU6050: "):
            self._mpu_disponible = "no detectado" not in texto
            self.label_sensor.setText(
                "Sensor: detectado" if self._mpu_disponible else "Sensor: no detectado (revisa el cableado I2C)"
            )
            self._actualizar_habilitados()
        elif texto.startswith("AUTOAJUSTE,"):
            self._on_autoajuste(texto)
        elif texto == "BALANCE,OFF" or texto.startswith("BALANCE,error"):
            self._marcar(self.btn_balance, False)
        elif texto in ("BALANCE,ON", "BALANCE,autoajustando") or texto.startswith("BALANCE,esperando"):
            self._marcar(self.btn_balance, True)
            if texto.startswith("BALANCE,esperando"):
                self.label_auto.setText("Esperando para autoajustarse: " + texto.split(",", 2)[2])
        elif texto in ("IMUSTREAM,ON", "IMUSTREAM,OFF"):
            self._marcar(self.btn_vivo, texto == "IMUSTREAM,ON")
        elif texto.startswith("IMUSTREAM,error"):
            self._marcar(self.btn_vivo, False)
        return False

    # ------------------------------------------------------------------
    # SEGMENTO: MENSAJES DEL ROBOT
    # ------------------------------------------------------------------
    def _on_actitud(self, texto):
        partes = texto.split(",")
        if len(partes) != 10:
            return
        try:
            roll, pitch, rumbo, corr_lateral, corr_frontal = (float(p) for p in partes[1:6])
        except ValueError:
            return
        estado = partes[6]
        giro_listo, nivel_listo, auto_listo = (p == "1" for p in partes[7:10])
        self.indicador.set_attitude(pitch, roll)
        if estado == "CAIDA":
            self.label_correccion.setText("Caído: el balance no corrige hasta que vuelva a estar parado")
        elif estado == "AUTO":
            self.label_correccion.setText(
                f"Autoajustando, no lo toques · caderas {corr_lateral:+.0f} us · fémures {corr_frontal:+.0f} us"
            )
        else:
            self.label_correccion.setText(
                f"Rumbo {rumbo:+.1f}°   Corrección caderas {corr_lateral:+.0f} us · fémures {corr_frontal:+.0f} us"
            )
        pendientes = []
        if not giro_listo:
            pendientes.append("giroscopio (déjalo quieto 1 s)")
        if not nivel_listo:
            pendientes.append("derecho (quieto en Inicio)")
        if not auto_listo:
            pendientes.append("autoajuste (se hace al activar el balance)")
        self.label_calibracion.setText(
            "Calibración completa." if not pendientes else "Falta: " + ", ".join(pendientes) + "."
        )

    def _on_config(self, texto):
        valores = texto.split(",")[1:]
        if len(valores) != VALORES_BALCONF:
            return
        try:
            numeros = [float(v) for v in valores]
        except ValueError:
            return
        for (clave, *_), valor in zip(GANANCIAS, numeros[:5]):
            self.spins[clave].setValue(valor)
        self._config_recibida = True
        auto_listo = numeros[5] == 1
        if not self._autoajustando:
            self.label_auto.setText(
                self._resumen_efectos(*numeros[6:9]) if auto_listo
                else "Todavía no se autoajustó: se hace solo al activar el balance."
            )
        self._marcar(self.btn_balance, numeros[9] == 1)

    def _on_autoajuste(self, texto):
        _, estado, *resto = texto.split(",")
        detalle = ",".join(resto)
        if estado == "inicio":
            self._autoajustando = True
            self.label_auto.setText("Autoajustando (~17 s). No lo toques ni lo muevas.")
        elif estado == "ok":
            self._autoajustando = False
            efectos = dict(parte.split("=") for parte in resto if "=" in parte)
            try:
                self.label_auto.setText(self._resumen_efectos(
                    float(efectos["caderas"]), float(efectos["pies"]), float(efectos["femures"])))
            except (KeyError, ValueError):
                self.label_auto.setText("Autoajuste listo.")
        else:  # error o pendiente
            self._autoajustando = False
            self.label_auto.setText(("No se pudo autoajustar: " if estado == "error" else "") + detalle)
        self._actualizar_habilitados()

    def _resumen_efectos(self, caderas, pies, femures):
        def texto(nombre, grados):
            return f"{nombre} {abs(grados):.1f}°" if grados else f"{nombre} no corrigen (casi no inclinan el torso)"
        return ("Autoajuste listo. Con 50 us el torso se inclina: "
                + " · ".join((texto("caderas", caderas), texto("pies", pies), texto("fémures", femures))) + ".")

    # ------------------------------------------------------------------
    # SEGMENTO: ACCIONES Y AUXILIARES
    # ------------------------------------------------------------------
    def _on_vivo(self, activo):
        self.btn_vivo.setText("Ocultar inclinación en vivo" if activo else "Ver inclinación en vivo")
        self.comando.emit("IMUON" if activo else "IMUOFF")

    def _on_balance(self, activo):
        self.btn_balance.setText("Balance activo" if activo else "Activar balance")
        self.comando.emit("BALANCE,ON" if activo else "BALANCE,OFF")
        self._actualizar_habilitados()

    def _enviar_ajustes(self):
        valores = ",".join(f"{self.spins[clave].value():.2f}" for clave, *_ in GANANCIAS)
        self.comando.emit(f"BALGAIN,{valores}")

    def _marcar(self, boton, activo):
        # Refleja lo que confirma el robot sin volver a mandarle el comando.
        boton.blockSignals(True)
        boton.setChecked(activo)
        boton.blockSignals(False)
        if boton is self.btn_balance:
            boton.setText("Balance activo" if activo else "Activar balance")
        else:
            boton.setText("Ocultar inclinación en vivo" if activo else "Ver inclinación en vivo")
        self._actualizar_habilitados()

    def _actualizar_habilitados(self):
        base = self._conectado and not self._emergencia and self._mpu_disponible is not False
        for widget in (self.btn_vivo, self.btn_balance, self.btn_rumbo):
            widget.setEnabled(base)
        self.btn_enviar_ajustes.setEnabled(base and self._config_recibida)
        self.btn_autoajuste.setEnabled(base and not self._autoajustando)
