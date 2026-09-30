"""SEGMENTO: VENTANA PRINCIPAL
Conecta el puerto serie con los paneles de control, poses y secuencias,
y con el editor de canales del PCA9685 (menu Configuracion).
"""

import channel_config as cc
import flash_tool
import storage
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from robot_link import RobotLink, IP_AP_POR_DEFECTO
from widgets.channels_dialog import ChannelsDialog
from widgets.console_panel import ConsolePanel
from widgets.control_panel import ControlPanel
from widgets.balance_panel import BalancePanel
from widgets.mando_panel import MandoPanel
from widgets.positions_panel import PositionsPanel
from widgets.sequence_panel import SequencePanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Robot Control")
        self.resize(1440, 840)

        # SEGMENTO: ESTADO DE CANALES Y CONEXION -------------------------
        self.servos = cc.cargar()
        self.servos_por_canal = {s["canal"]: s for s in self.servos}

        self.serial_link = RobotLink()
        self.serial_link.connected_changed.connect(self._on_connected_changed)
        self.serial_link.line_received.connect(self._on_line_received)
        self.serial_link.error.connect(self._on_link_error)

        self._emergencia_activa = False
        self._pendientes = {}  # canal -> (pulso, velocidad) por enviar en el proximo tick

        self._construir_menu()
        self._construir_ui()

        self._timer_envio = QTimer(self)
        self._timer_envio.timeout.connect(self._vaciar_pendientes)
        self._timer_envio.start(40)

        self._refrescar_puertos()

    # ------------------------------------------------------------------
    # SEGMENTO: CONSTRUCCION DE LA INTERFAZ
    # ------------------------------------------------------------------
    def _construir_menu(self):
        menu = self.menuBar().addMenu("Configuración")
        accion_canales = menu.addAction("Canales de servos…")
        accion_canales.triggered.connect(self._abrir_editor_canales)
        menu.addSeparator()
        accion_escanear = menu.addAction("Escanear bus I2C")
        accion_escanear.triggered.connect(self._escanear_i2c)
        menu.addSeparator()
        accion_exportar = menu.addAction("Exportar movimientos…")
        accion_exportar.setToolTip(
            "Guarda canales, poses y secuencias en un solo archivo, para usarlo desde otro programa."
        )
        accion_exportar.triggered.connect(self._exportar_movimientos)
        accion_importar = menu.addAction("Importar movimientos…")
        accion_importar.setToolTip(
            "Carga canales, poses y secuencias desde un archivo exportado por esta misma app."
        )
        accion_importar.triggered.connect(self._importar_movimientos)
        menu.addSeparator()
        self.accion_subir_firmware = menu.addAction("Subir firmware al ESP32…")
        self.accion_subir_firmware.triggered.connect(self._subir_firmware)
        self._flash_worker = None

    def _construir_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout_raiz = QVBoxLayout(central)

        layout_raiz.addWidget(self._construir_barra_superior())

        # Todo visible a la vez, sin pestañas: control manual a la izquierda,
        # poses/secuencias apilados a la derecha, consola abajo.
        self.control_panel = ControlPanel(self.servos)
        self.control_panel.angulo_cambiado.connect(self._on_slider_cambiado)

        self.positions_panel = PositionsPanel()
        self.positions_panel.posicion_aplicada.connect(self._aplicar_pose)
        self.positions_panel.solicitar_captura.connect(self._guardar_pose_actual)
        self.positions_panel.solicitar_sobrescritura.connect(self._sobrescribir_pose)
        self.positions_panel.lista_cambiada.connect(self._on_posiciones_cambiadas)

        self.sequence_panel = SequencePanel(self.positions_panel)
        self.sequence_panel.paso_activado.connect(self._aplicar_pose)
        # Renombrar una pose tiene que arreglar los pasos que la usaban, o
        # quedarian apuntando a un nombre que ya no existe.
        self.positions_panel.pose_renombrada.connect(self.sequence_panel.renombrar_pose_en_secuencias)

        vista_caras = self._construir_caras_oled()

        # Izquierda: control manual arriba, los pasos de la secuencia en el
        # medio (aprovechando el hueco que antes quedaba vacio) y las caras del
        # OLED al final, que son solo 4 botones. Derecha: poses y secuencias.
        # Los pasos van con el control manual y NO con la lista de secuencias
        # porque es lo que se mira mientras se arma el movimiento.
        columna_izquierda = QSplitter(Qt.Vertical)
        columna_izquierda.addWidget(self._en_caja("Control manual", self.control_panel))
        columna_izquierda.addWidget(self._en_caja("Pasos de la secuencia actual", self.sequence_panel.caja_pasos))
        columna_izquierda.addWidget(self._en_caja("Cara (pantalla OLED)", vista_caras))
        columna_izquierda.setSizes([420, 300, 90])
        # Sin esto, el splitter reparte el alto sobrante de la ventana en
        # proporcion entre las tres cajas -- y "Cara" (4 botones) terminaba con
        # un hueco vacio enorme abajo. El espacio de mas se lo reparten control
        # manual y pasos, no las caras.
        columna_izquierda.setStretchFactor(0, 1)
        columna_izquierda.setStretchFactor(1, 1)
        columna_izquierda.setStretchFactor(2, 0)

        columna_derecha = QSplitter(Qt.Vertical)
        columna_derecha.addWidget(self._en_caja("Poses", self.positions_panel))
        columna_derecha.addWidget(self._en_caja("Secuencias", self.sequence_panel.caja_secuencias))
        columna_derecha.setSizes([450, 300])

        contenido = QSplitter(Qt.Horizontal)
        contenido.addWidget(columna_izquierda)
        contenido.addWidget(columna_derecha)
        contenido.setStretchFactor(0, 1)
        contenido.setStretchFactor(1, 1)

        # Dos pestañas bien separadas: "Creación" para diseñar poses/
        # secuencias, "Mando" para asignarlas a cada direccion del D-pad. Al
        # cambiar de pestaña no se ve nada de la otra.
        self.mando_panel = MandoPanel(self.sequence_panel, self.positions_panel)
        self.sequence_panel.secuencias_cambiadas.connect(self.mando_panel.refrescar_secuencias)
        self.positions_panel.lista_cambiada.connect(self.mando_panel.refrescar_secuencias)

        self.balance_panel = BalancePanel(self.servos)
        self.balance_panel.comando.connect(self.serial_link.send)

        pestañas = QTabWidget()
        pestañas.addTab(contenido, "Creación de movimientos")
        pestañas.addTab(self.mando_panel, "Mando")
        pestañas.addTab(self.balance_panel, "Balance")
        pestañas.setCurrentIndex(0)

        self.consola = ConsolePanel()
        self.consola.setMaximumHeight(170)

        layout_raiz.addWidget(pestañas, 1)
        layout_raiz.addWidget(self.consola)

        self._actualizar_estado_controles(conectado=False)

    @staticmethod
    def _en_caja(titulo, widget):
        caja = QGroupBox(titulo)
        layout = QVBoxLayout(caja)
        layout.setContentsMargins(6, 12, 6, 6)
        layout.addWidget(widget)
        return caja

    def _construir_barra_superior(self):
        """Una sola fila con todo: conexion al robot y las acciones que se le
        mandan una vez conectado, en el mismo orden en que aparecian antes de
        separarlas en dos filas."""
        barra = QWidget()
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(8)

        self.combo_modo = QComboBox()
        self.combo_modo.addItems(["USB", "WiFi"])
        self.combo_modo.setToolTip(
            "USB: por el cable, con el puerto de al lado.\n"
            f"WiFi: se conecta directo a la red propia del robot ({IP_AP_POR_DEFECTO})."
        )

        self.combo_puertos = QComboBox()
        self.combo_puertos.setMinimumWidth(180)
        btn_refrescar = QPushButton("Actualizar")
        btn_refrescar.setToolTip("Vuelve a buscar puertos serie conectados.")
        btn_refrescar.clicked.connect(self._refrescar_puertos)

        self.btn_conectar = QPushButton("Conectar")
        self.btn_conectar.setObjectName("botonPrimario")
        self.btn_conectar.clicked.connect(self._toggle_conexion)

        self.label_estado = QLabel("● Desconectado")
        self.label_estado.setObjectName("estadoDesconectado")

        self.spin_velocidad = QSpinBox()
        self.spin_velocidad.setRange(1, 100)
        self.spin_velocidad.setValue(15)
        self.spin_velocidad.setToolTip("Que tan rapido se mueven los servos al aplicar una pose (us por paso).")

        self.btn_home = QPushButton("Inicio")
        self.btn_home.setToolTip("Lleva el robot a la pose de inicio guardada en el ESP32.")
        self.btn_home.clicked.connect(self._ir_a_inicio)
        self.btn_homeset = QPushButton("Fijar inicio")
        self.btn_homeset.setToolTip("Guarda la pose actual como la pose de arranque del robot.")
        self.btn_homeset.clicked.connect(self._fijar_inicio)
        self.btn_relax = QPushButton("Relajar")
        self.btn_relax.setToolTip("Corta el PWM: los servos dejan de hacer fuerza.")
        self.btn_relax.clicked.connect(self._relajar)
        self.btn_resume = QPushButton("Reanudar")
        self.btn_resume.setToolTip("Sale de la parada de emergencia y vuelve a permitir movimiento.")
        self.btn_resume.clicked.connect(self._reanudar)

        self.btn_stop = QPushButton("PARADA DE EMERGENCIA")
        self.btn_stop.setObjectName("botonEmergencia")
        self.btn_stop.setToolTip("Detiene todo movimiento al instante.")
        self.btn_stop.clicked.connect(self._parada_emergencia)

        for boton in (self.btn_home, self.btn_homeset, self.btn_relax, self.btn_resume, self.btn_stop):
            boton.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self.btn_consola = QPushButton("Ocultar consola")
        self.btn_consola.setCheckable(True)
        self.btn_consola.setChecked(True)
        self.btn_consola.toggled.connect(self._toggle_consola)

        fila.addWidget(self._etiqueta("Modo"))
        fila.addWidget(self.combo_modo)
        fila.addWidget(self._etiqueta("Puerto"))
        fila.addWidget(self.combo_puertos)
        fila.addWidget(btn_refrescar)
        fila.addWidget(self.btn_conectar)
        fila.addWidget(self.label_estado)
        fila.addWidget(self._separador())
        fila.addWidget(self._etiqueta("Velocidad"))
        fila.addWidget(self.spin_velocidad)
        fila.addWidget(self._separador())
        fila.addWidget(self.btn_home)
        fila.addWidget(self.btn_homeset)
        fila.addWidget(self.btn_relax)
        fila.addWidget(self.btn_resume)
        fila.addStretch()
        # La emergencia queda separada del resto, justo antes de la consola:
        # es el unico boton que no se debe apretar por error.
        fila.addWidget(self.btn_stop)
        fila.addWidget(self.btn_consola)
        return barra

    @staticmethod
    def _separador():
        linea = QFrame()
        linea.setObjectName("separadorBarra")
        linea.setFrameShape(QFrame.VLine)
        return linea

    @staticmethod
    def _etiqueta(texto):
        label = QLabel(texto)
        label.setObjectName("etiquetaBarra")
        return label

    def _toggle_consola(self, mostrar):
        self.consola.setVisible(mostrar)
        self.btn_consola.setText("Ocultar consola" if mostrar else "Mostrar consola")

    def _construir_caras_oled(self):
        vista = QWidget()
        layout = QVBoxLayout(vista)

        fila_cara = QHBoxLayout()
        self.botones_cara = {}
        for nombre, etiqueta in (
            ("FELIZ", "Feliz"), ("TRISTE", "Triste"),
            ("SORPRESA", "Sorpresa"), ("NEUTRAL", "Neutral"),
        ):
            boton = QPushButton(etiqueta)
            boton.clicked.connect(lambda _checked=False, n=nombre: self.serial_link.send(f"CARA,{n}"))
            self.botones_cara[nombre] = boton
            fila_cara.addWidget(boton)
        fila_cara.addStretch()
        layout.addLayout(fila_cara)

        layout.addStretch()
        return vista

    # ------------------------------------------------------------------
    # SEGMENTO: CONEXION SERIAL
    # ------------------------------------------------------------------
    def _refrescar_puertos(self):
        self.combo_puertos.clear()
        for device, descripcion in RobotLink.list_ports():
            self.combo_puertos.addItem(f"{device} — {descripcion}", userData=device)
        self.consola.agregar_linea(f"Puertos disponibles: {self.combo_puertos.count()}")

    def _toggle_conexion(self):
        if self.serial_link.is_connected():
            self.serial_link.disconnect()
            return

        if self.combo_modo.currentText() == "WiFi":
            self.consola.agregar_linea(f"Conectando por WiFi a {IP_AP_POR_DEFECTO}...")
            self.btn_conectar.setEnabled(False)
            self.serial_link.connect_wifi()
            return

        if self.combo_puertos.count() == 0:
            QMessageBox.warning(self, "Sin puertos", "No se encontro ningun puerto serie. Conecta el ESP32 por USB.")
            return
        puerto = self.combo_puertos.currentData()
        self.consola.agregar_linea(f"Conectando a {puerto}...")
        self.btn_conectar.setEnabled(False)
        if not self.serial_link.connect_serial(puerto):
            self.btn_conectar.setEnabled(True)

    def _on_link_error(self, mensaje):
        self.consola.agregar_linea(mensaje, es_error=True)
        # A diferencia de connect_serial (que falla al toque y ya se maneja
        # en _toggle_conexion), connect_wifi falla en un hilo de fondo, asi
        # que si nunca se llego a conectar hay que rehabilitar el boton aqui.
        if not self.serial_link.is_connected():
            self.btn_conectar.setEnabled(True)

    def _on_connected_changed(self, conectado):
        self.btn_conectar.setEnabled(True)
        self._actualizar_estado_controles(conectado)
        if conectado:
            self.label_estado.setText("● Conectado")
            self.label_estado.setObjectName("estadoConectado")
            self.btn_conectar.setText("Desconectar")
            self.consola.agregar_linea("Conectado. Enviando PING de prueba...")
            self.serial_link.send("PING")
            self.serial_link.send("BALCONF")  # sincroniza la pestaña Balance con lo guardado en el robot
        else:
            self.label_estado.setText("● Desconectado")
            self.label_estado.setObjectName("estadoDesconectado")
            self.btn_conectar.setText("Conectar")
            self.consola.agregar_linea("Desconectado.")
        self.label_estado.style().unpolish(self.label_estado)
        self.label_estado.style().polish(self.label_estado)

    def _actualizar_estado_controles(self, conectado):
        # Sliders, poses y secuencias son ediciones locales: se pueden usar
        # aunque el robot no este conectado (el firmware ya rechaza mover los
        # servos si esta en STOP). Solo las acciones que mandan un comando
        # directo al robot ahora mismo necesitan conexion.
        self.balance_panel.set_conectado(conectado, self._emergencia_activa)
        botones_de_hardware = (
            self.btn_home, self.btn_homeset, self.btn_relax, self.btn_stop,
            *self.botones_cara.values(),
        )
        for boton in botones_de_hardware:
            boton.setEnabled(conectado and not (self._emergencia_activa and boton is not self.btn_stop))
        self.btn_resume.setEnabled(conectado and self._emergencia_activa)
        if not conectado:
            self.btn_stop.setEnabled(False)

    # ------------------------------------------------------------------
    # SEGMENTO: RECEPCION DE DATOS DEL ESP32
    # ------------------------------------------------------------------
    def _on_line_received(self, texto):
        # La telemetria del balance llega 10 veces por segundo: va directo a
        # su pestaña y no a la consola, que si no se llenaria en segundos.
        if self.balance_panel.procesar_linea(texto):
            return
        # Botones apretados en el mando: iluminan su tarjeta y no llenan la consola.
        if self.mando_panel.procesar_linea(texto):
            return
        self.consola.agregar_linea(texto)
        # Las lineas "M," son solo eco informativo (consola/diagnostico) -- ya
        # NO se usan para mover sliders. Se probo hacerlo (sincronizar desde
        # ahi) y por WiFi esos ecos pueden llegar tarde, justo cuando el
        # usuario ya edito el slider a mano para sobrescribir una pose, y lo
        # hacian saltar de vuelta al valor viejo. Los sliders ya se actualizan
        # de forma sincronica en el momento de aplicar cualquier pose/paso
        # (ver _aplicar_pose), asi que no hace falta "confirmarlo" con el eco.
        # El unico caso que SI necesita sincronizarse desde el ESP32 es HOME,
        # porque la app no sabe de antemano a que pulso va cada canal -- para
        # eso el firmware manda un mensaje aparte, "HOME,ok,<16 pulsos>".
        if texto.startswith("HOME,ok,"):
            valores = texto[len("HOME,ok,"):].split(",")
            if len(valores) == 16:
                angulos = {}
                for canal, pulso_texto in enumerate(valores):
                    servo = self.servos_por_canal.get(canal)
                    if not servo:
                        continue
                    try:
                        pulso = int(pulso_texto)
                    except ValueError:
                        continue
                    angulos[str(canal)] = cc.pulso_a_angulo(servo, pulso)
                self.control_panel.aplicar_angulos(angulos, emitir=False)
        elif texto.startswith("STOP,activado"):
            self.sequence_panel.detener_por_emergencia()
            self._marcar_emergencia(True)
        elif texto.startswith("STOP,desactivado"):
            self._marcar_emergencia(False)

    # ------------------------------------------------------------------
    # SEGMENTO: ENVIO DE COMANDOS DE MOVIMIENTO
    # ------------------------------------------------------------------
    def _on_slider_cambiado(self, canal, angulo):
        servo = self.servos_por_canal.get(canal)
        if not servo:
            return
        pulso = cc.angulo_a_pulso(servo, angulo)
        self._pendientes[canal] = (pulso, 0)  # movimiento manual: instantaneo

    def _vaciar_pendientes(self):
        if not self._pendientes or not self.serial_link.is_connected():
            self._pendientes.clear()
            return
        for canal, (pulso, velocidad) in self._pendientes.items():
            self.serial_link.send(f"{canal},{pulso},{velocidad}")
        self._pendientes.clear()

    def _aplicar_pose(self, angulos):
        # Se manda como un solo comando POSE con los 16 pulsos, en vez de 16
        # comandos sueltos: por WiFi, cualquiera de 16 mensajes separados
        # podia llegar tarde o perderse y dejar la pose a medio aplicar.
        velocidad = self.spin_velocidad.value()
        self.control_panel.aplicar_angulos(angulos, emitir=False)

        pulsos = []
        for canal in range(16):
            servo = self.servos_por_canal.get(canal)
            if servo is None:
                pulsos.append(1475)  # canal sin mapear: pulso central, no se mueve a un extremo
                continue
            if str(canal) in angulos:
                angulo = angulos[str(canal)]
            elif canal in angulos:
                angulo = angulos[canal]
            else:
                fila = self.control_panel.sliders.get(canal)
                angulo = fila.slider.value() if fila else 0
            pulsos.append(int(cc.angulo_a_pulso(servo, angulo)))

        self.serial_link.send("POSE," + ",".join(str(p) for p in pulsos) + f",{velocidad}")

    def _guardar_pose_actual(self):
        self.positions_panel.guardar_captura(self.control_panel.obtener_angulos())

    def _sobrescribir_pose(self, nombre):
        respuesta = QMessageBox.question(
            self, "Sobrescribir pose", f"¿Reemplazar '{nombre}' con la posicion actual de los sliders?"
        )
        if respuesta == QMessageBox.Yes:
            self.positions_panel.sobrescribir(nombre, self.control_panel.obtener_angulos())

    def _on_posiciones_cambiadas(self):
        # Se guardo, sobrescribio o borro una pose: el combo de "Agregar
        # paso" en Secuencias tiene que reflejarlo (si no, podrias armar un
        # paso apuntando a una pose que ya no existe).
        self.sequence_panel.refrescar_posiciones_disponibles()

    # ------------------------------------------------------------------
    # SEGMENTO: BOTONES GLOBALES (INICIO, RELAJAR, EMERGENCIA)
    # ------------------------------------------------------------------
    def _ir_a_inicio(self):
        self.sequence_panel.detener_por_emergencia()
        self.serial_link.send("HOME")

    def _fijar_inicio(self):
        respuesta = QMessageBox.question(
            self,
            "Fijar posicion de inicio",
            "El robot arrancara siempre en la pose actual la proxima vez que se le "
            "de energia. ¿Guardar la pose actual como inicio?",
        )
        if respuesta == QMessageBox.Yes:
            self.serial_link.send("HOMESET")

    def _relajar(self):
        self.sequence_panel.detener_por_emergencia()
        self.serial_link.send("RELAX")

    def _reanudar(self):
        self.serial_link.send("RESUME")
        self._marcar_emergencia(False)  # optimista, igual que hace _parada_emergencia con STOP

    def _parada_emergencia(self):
        self.sequence_panel.detener_por_emergencia()
        self._pendientes.clear()
        self.serial_link.send("STOP")
        self._marcar_emergencia(True)

    def _marcar_emergencia(self, activa):
        self._emergencia_activa = activa
        self._actualizar_estado_controles(self.serial_link.is_connected())

    # ------------------------------------------------------------------
    # SEGMENTO: EDITOR DE CANALES DEL PCA9685
    # ------------------------------------------------------------------
    def _abrir_editor_canales(self):
        dialogo = ChannelsDialog(self.servos, self)
        if dialogo.exec():
            nuevos_servos = dialogo.servos_guardados()
            if nuevos_servos is None:
                return
            cc.guardar(nuevos_servos)
            self.servos = nuevos_servos
            self.servos_por_canal = {s["canal"]: s for s in self.servos}
            self.control_panel.reconstruir(self.servos)
            self.balance_panel.reconstruir(self.servos)
            self.consola.agregar_linea("Mapeo de canales actualizado.")

    def _escanear_i2c(self):
        if not self.serial_link.is_connected():
            QMessageBox.warning(self, "Escanear bus I2C", "Conecta primero al ESP32 (USB o WiFi).")
            return
        self.serial_link.send("SCAN")

    def _exportar_movimientos(self):
        # Un archivo autocontenido (canales + poses + secuencias) para que
        # otro programa -- por ejemplo la futura app de mando por Bluetooth --
        # pueda usar estos movimientos sin depender de esta app para nada.
        ruta_texto, _ = QFileDialog.getSaveFileName(
            self, "Exportar movimientos", "movimientos_robot.json", "JSON (*.json)"
        )
        if not ruta_texto:
            return
        storage.exportar_todo(
            Path(ruta_texto),
            self.servos,
            self.positions_panel.posiciones,
            self.sequence_panel.secuencias,
            self.positions_panel.carpetas,
        )
        QMessageBox.information(self, "Exportar movimientos", f"Guardado en:\n{ruta_texto}")

    def _importar_movimientos(self):
        ruta_texto, _ = QFileDialog.getOpenFileName(
            self, "Importar movimientos", "", "JSON (*.json)"
        )
        if not ruta_texto:
            return
        try:
            canales, posiciones, secuencias, carpetas_poses = storage.importar_todo(Path(ruta_texto))
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.critical(self, "Error al importar", f"No se pudo leer el archivo:\n{exc}")
            return

        aviso_canales = " y reemplazar el mapeo de canales" if canales else ""
        respuesta = QMessageBox.question(
            self, "Importar movimientos",
            f"Se van a agregar/reemplazar {len(posiciones)} pose(s) y {len(secuencias)} secuencia(s)"
            f"{aviso_canales}.\n\nSi ya tienes algo guardado con el mismo nombre, se sobrescribe."
            "\n¿Continuar?",
        )
        if respuesta != QMessageBox.Yes:
            return

        if canales:
            cc.guardar(canales)
            self.servos = canales
            self.servos_por_canal = {s["canal"]: s for s in self.servos}
            self.control_panel.reconstruir(self.servos)
            self.balance_panel.reconstruir(self.servos)

        self.positions_panel.importar_posiciones(posiciones, carpetas_poses)
        self.sequence_panel.importar_secuencias(secuencias)

        self.consola.agregar_linea(
            f"Importado: {len(posiciones)} pose(s), {len(secuencias)} secuencia(s)"
            f"{', canales' if canales else ''}."
        )
        QMessageBox.information(self, "Importar movimientos", "Importación completa.")

    # ------------------------------------------------------------------
    # SEGMENTO: SUBIR FIRMWARE (esptool)
    # ------------------------------------------------------------------
    def _subir_firmware(self):
        if not flash_tool.firmware_disponible():
            QMessageBox.warning(
                self, "Firmware no encontrado",
                "No se encontro el firmware compilado en app/firmware/.\n"
                "Corre sync_firmware.ps1 en la carpeta del proyecto para generarlo."
            )
            return
        if self.combo_puertos.count() == 0:
            QMessageBox.warning(self, "Sin puertos", "No se encontro ningun puerto serie. Conecta el ESP32 por USB.")
            return

        puerto = self.combo_puertos.currentData()
        respuesta = QMessageBox.question(
            self, "Subir firmware",
            f"Esto va a sobrescribir el programa del ESP32 en {puerto} con el firmware actual "
            "de esta app. El robot puede moverse brevemente al reiniciar. ¿Continuar?",
        )
        if respuesta != QMessageBox.Yes:
            return

        if self.serial_link.is_connected():
            self.serial_link.disconnect()

        self.accion_subir_firmware.setEnabled(False)
        self.btn_conectar.setEnabled(False)
        self.consola.agregar_linea(f"Subiendo firmware a {puerto}...")

        self._flash_worker = flash_tool.FlashWorker(puerto)
        self._flash_worker.linea.connect(self.consola.agregar_linea)
        self._flash_worker.terminado.connect(self._on_firmware_terminado)
        self._flash_worker.start()

    def _on_firmware_terminado(self, exito, mensaje):
        self.consola.agregar_linea(mensaje, es_error=not exito)
        self.accion_subir_firmware.setEnabled(True)
        self.btn_conectar.setEnabled(True)
        if exito:
            QMessageBox.information(self, "Firmware actualizado", mensaje)
        else:
            QMessageBox.critical(self, "Error al subir firmware", mensaje)

    # ------------------------------------------------------------------
    def closeEvent(self, event):
        self.serial_link.disconnect()
        super().closeEvent(event)
