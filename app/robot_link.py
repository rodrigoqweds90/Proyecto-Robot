"""SEGMENTO: COMUNICACION CON EL ROBOT (USB o WIFI)
Habla con el ESP32 por dos canales posibles: cable USB (puerto serie) o WiFi
(el ESP32 crea su propia red y expone un servidor TCP). Los dos hablan el
mismo protocolo de texto por linea, asi que el resto de la app no necesita
saber cual esta activo: solo usa is_connected() / send() / las senales.
Toda la lectura corre en un hilo aparte para no bloquear la interfaz.
"""

import socket

import serial
import serial.tools.list_ports
from PySide6.QtCore import QObject, QThread, QTimer, Signal

ESPERA_REINICIO_ESP32_MS = 2000
IP_AP_POR_DEFECTO = "192.168.4.1"
PUERTO_TCP_POR_DEFECTO = 8888


class _SerialReader(QThread):
    line_received = Signal(str)
    connection_lost = Signal(str)

    def __init__(self, ser):
        super().__init__()
        self._ser = ser
        self._running = True

    def run(self):
        while self._running:
            try:
                raw = self._ser.readline()
            except serial.SerialException as exc:
                if self._running:
                    self.connection_lost.emit(str(exc))
                return
            if not raw:
                continue
            text = raw.decode("utf-8", errors="replace").strip()
            if text:
                self.line_received.emit(text)

    def stop(self):
        self._running = False


class _WifiReader(QThread):
    line_received = Signal(str)
    connection_lost = Signal(str)

    def __init__(self, sock):
        super().__init__()
        self._sock = sock
        self._running = True

    def run(self):
        buffer = b""
        while self._running:
            try:
                datos = self._sock.recv(1024)
            except socket.timeout:
                continue
            except OSError as exc:
                if self._running:
                    self.connection_lost.emit(str(exc))
                return
            if not datos:
                if self._running:
                    self.connection_lost.emit("El ESP32 cerro la conexion WiFi.")
                return
            buffer += datos
            while b"\n" in buffer:
                cruda, buffer = buffer.split(b"\n", 1)
                texto = cruda.decode("utf-8", errors="replace").strip()
                if texto:
                    self.line_received.emit(texto)

    def stop(self):
        self._running = False


class _WifiConector(QThread):
    """Abre el socket TCP en un hilo aparte: conectar puede tardar varios
    segundos (o fallar) si el robot esta fuera de rango, y eso congelaria
    la interfaz si se hiciera en el hilo principal."""

    conectado = Signal(object)
    fallo = Signal(str)

    def __init__(self, host, puerto):
        super().__init__()
        self._host = host
        self._puerto = puerto

    def run(self):
        try:
            sock = socket.create_connection((self._host, self._puerto), timeout=5)
            sock.settimeout(1.0)
        except OSError as exc:
            self.fallo.emit(str(exc))
            return
        self.conectado.emit(sock)


class RobotLink(QObject):
    line_received = Signal(str)
    imu_received = Signal(float, float, float, float, float, float, float, float)
    connected_changed = Signal(bool)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._modo = None  # "serial" o "wifi"
        self._ser = None
        self._sock = None
        self._reader = None
        self._conector = None
        self._listo = False  # True recien cuando ya se puede mandar comandos
        # Se incrementa en cada connect_wifi()/disconnect(). connect_wifi() es
        # asincrono (el socket se abre en un hilo aparte); si el usuario le da
        # Desconectar mientras ese hilo todavia esta conectando, este numero
        # permite que _on_wifi_conectado() note que ese intento ya quedo viejo
        # y no reconecte solo por accidente.
        self._generacion_conexion = 0

    @staticmethod
    def list_ports():
        return [(p.device, p.description) for p in serial.tools.list_ports.comports()]

    def is_connected(self):
        if not self._listo:
            return False
        if self._modo == "serial":
            return self._ser is not None and self._ser.is_open
        if self._modo == "wifi":
            return self._sock is not None
        return False

    # ------------------------------------------------------------------
    # SEGMENTO: CONEXION POR USB
    # ------------------------------------------------------------------
    def connect_serial(self, port, baudrate=115200):
        if self.is_connected():
            self.disconnect()
        try:
            self._ser = serial.Serial(port, baudrate, timeout=1)
        except serial.SerialException as exc:
            self.error.emit(str(exc))
            return False

        self._modo = "serial"
        self._listo = False
        # La lectura arranca de inmediato: el ESP32 se reinicia al abrir el
        # puerto y sus primeros mensajes salen en el primer medio segundo,
        # no hay que perderselos. Lo que SI espera es el envio de comandos
        # (mas abajo), para no mandar nada mientras el ESP32 todavia reinicia.
        self._reader = _SerialReader(self._ser)
        self._reader.line_received.connect(self._on_line)
        self._reader.connection_lost.connect(self._on_connection_lost)
        self._reader.start()
        QTimer.singleShot(ESPERA_REINICIO_ESP32_MS, self._finalizar_conexion_serial)
        return True

    def _finalizar_conexion_serial(self):
        if self._modo != "serial" or not self._ser or not self._ser.is_open:
            return  # se desconecto durante la espera
        self._listo = True
        self.connected_changed.emit(True)

    # ------------------------------------------------------------------
    # SEGMENTO: CONEXION POR WIFI
    # ------------------------------------------------------------------
    def connect_wifi(self, host=IP_AP_POR_DEFECTO, puerto=PUERTO_TCP_POR_DEFECTO):
        if self.is_connected():
            self.disconnect()
        self._modo = "wifi"
        self._listo = False
        self._generacion_conexion += 1
        generacion = self._generacion_conexion
        self._conector = _WifiConector(host, puerto)
        self._conector.conectado.connect(lambda sock: self._on_wifi_conectado(sock, generacion))
        self._conector.fallo.connect(self._on_wifi_fallo)
        self._conector.start()
        return True

    def _on_wifi_conectado(self, sock, generacion):
        if self._modo != "wifi" or generacion != self._generacion_conexion:
            sock.close()  # se cancelo/cambio de modo mientras conectaba, o ya se desconecto
            return
        self._sock = sock
        self._listo = True
        self._reader = _WifiReader(sock)
        self._reader.line_received.connect(self._on_line)
        self._reader.connection_lost.connect(self._on_connection_lost)
        self._reader.start()
        self.connected_changed.emit(True)

    def _on_wifi_fallo(self, mensaje):
        self.error.emit(mensaje)

    # ------------------------------------------------------------------
    # SEGMENTO: COMUN A LOS DOS MODOS
    # ------------------------------------------------------------------
    def disconnect(self):
        self._listo = False
        self._generacion_conexion += 1  # invalida cualquier conexion WiFi en curso
        if self._reader:
            self._reader.stop()
            self._reader.wait(1500)
            self._reader = None
        if self._modo == "serial" and self._ser is not None:
            if self._ser.is_open:
                try:
                    self._ser.close()
                except serial.SerialException:
                    pass
            self._ser = None
        if self._modo == "wifi" and self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self.connected_changed.emit(False)

    def send(self, line):
        if not self.is_connected():
            return
        datos = (line.strip() + "\n").encode("utf-8")
        try:
            if self._modo == "serial":
                self._ser.write(datos)
            else:
                self._sock.sendall(datos)
        except (serial.SerialException, OSError) as exc:
            self.error.emit(str(exc))

    def _on_line(self, text):
        self.line_received.emit(text)
        if text.startswith("IMU,"):
            partes = text[4:].split(",")
            if len(partes) == 8:
                try:
                    valores = [float(v) for v in partes]
                except ValueError:
                    return
                self.imu_received.emit(*valores)

    def _on_connection_lost(self, message):
        self.error.emit(message)
        self.disconnect()
