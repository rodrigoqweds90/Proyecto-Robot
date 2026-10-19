"""SEGMENTO: SUBIR FIRMWARE AL ESP32
Flashea el firmware ya compilado (bootloader + tabla de particiones + programa)
usando esptool, para que la otra persona no necesite instalar PlatformIO ni
Arduino IDE: solo el .exe de esta app y el cable USB.

Los .bin vienen de compilar src/main.cpp con PlatformIO (ver sync_firmware.ps1
en la raiz del proyecto) y se guardan en app/firmware/.
"""

import io
import sys
import time

import serial
from PySide6.QtCore import QThread, Signal

from paths import directorio_app

CARPETA_FIRMWARE = directorio_app() / "firmware"
ARCHIVOS_FIRMWARE = [
    ("0x1000", CARPETA_FIRMWARE / "bootloader.bin"),
    ("0x8000", CARPETA_FIRMWARE / "partitions.bin"),
    ("0x10000", CARPETA_FIRMWARE / "firmware.bin"),
]


def firmware_disponible():
    return all(ruta.exists() for _, ruta in ARCHIVOS_FIRMWARE)


# Cuanto esperar a que Windows suelte el puerto. Al desconectar la app justo antes de
# subir, el driver USB tarda un momento en liberar el COM y esptool fallaba con
# "Acceso denegado" aunque nadie mas lo estuviera usando.
ESPERA_PUERTO_S = 8.0

AYUDA_PUERTO_OCUPADO = (
    "El puerto {puerto} esta ocupado por otro programa.\n\n"
    "Cierra lo que pueda estar usandolo y vuelve a intentar:\n"
    "  - otra ventana de esta app (RobotControl)\n"
    "  - el Monitor Serie de Arduino IDE o de PlatformIO / VS Code\n"
    "  - cualquier otro programa de puerto serie (PuTTY, CoolTerm...)\n"
    "Si sigue igual: desenchufa el cable USB del robot, espera 3 segundos y vuelve a enchufarlo."
)
AYUDA_SIN_CONEXION = (
    "No se pudo hablar con el ESP32 en {puerto}.\n\n"
    "  - Revisa que el cable USB sea de datos (algunos solo cargan) y este bien enchufado.\n"
    "  - Elige el puerto correcto en la lista de arriba.\n"
    "  - Si sigue fallando: manten apretado el boton BOOT del ESP32 mientras dice\n"
    "    'Connecting...' y sueltalo cuando empiece a escribir."
)


def esperar_puerto_libre(puerto, segundos=ESPERA_PUERTO_S):
    """(True, "") si el puerto se puede abrir dentro del tiempo dado (y lo deja cerrado);
    si no, (False, error). Un puerto que no existe no se espera: no va a aparecer solo."""
    limite = time.monotonic() + segundos
    while True:
        try:
            serial.Serial(puerto).close()
            return True, ""
        except serial.SerialException as exc:
            error = str(exc)
            if "filenotfound" in error.lower() or time.monotonic() >= limite:
                return False, error
            time.sleep(0.3)


def explicar_error(texto, puerto):
    """Mensaje para el usuario segun lo que dijo esptool (sin necesitar a nadie que lo interprete)."""
    t = texto.lower()
    if "filenotfound" in t or "no puede encontrar" in t or "cannot find" in t:
        return AYUDA_SIN_CONEXION.format(puerto=puerto)
    if "acceso denegado" in t or "access is denied" in t or "permissionerror" in t or "busy" in t:
        return AYUDA_PUERTO_OCUPADO.format(puerto=puerto)
    if "failed to connect" in t or "no serial data" in t or "timed out" in t or "could not open port" in t:
        return AYUDA_SIN_CONEXION.format(puerto=puerto)
    return f"Error al subir firmware: {texto}"


class _CapturaLineas(io.TextIOBase):
    """Redirige lo que esptool imprime hacia una funcion, linea por linea."""

    def __init__(self, callback):
        super().__init__()
        self._callback = callback
        self._buffer = ""

    def write(self, texto):
        self._buffer += texto
        while "\n" in self._buffer:
            linea, self._buffer = self._buffer.split("\n", 1)
            if linea.strip():
                self._callback(linea.strip())
        return len(texto)

    def flush(self):
        pass


class FlashWorker(QThread):
    linea = Signal(str)
    terminado = Signal(bool, str)  # exito, mensaje

    def __init__(self, puerto):
        super().__init__()
        self._puerto = puerto

    def run(self):
        if not firmware_disponible():
            self.terminado.emit(False, "No se encontro el firmware compilado en app/firmware/.")
            return

        self.linea.emit(f"Esperando a que {self._puerto} quede libre...")
        libre, error = esperar_puerto_libre(self._puerto)
        if not libre:
            self.terminado.emit(False, explicar_error(error, self._puerto))
            return

        argv = ["--chip", "esp32", "--port", self._puerto, "--baud", "460800", "write_flash"]
        for direccion, ruta in ARCHIVOS_FIRMWARE:
            argv += [direccion, str(ruta)]

        stdout_anterior = sys.stdout
        lineas = []
        sys.stdout = _CapturaLineas(lambda l: (lineas.append(l), self.linea.emit(l)))
        try:
            import esptool
            esptool.main(argv)
            exito, mensaje = True, "Firmware actualizado correctamente."
        except SystemExit as exc:
            exito = exc.code in (0, None)
            mensaje = ("Firmware actualizado correctamente." if exito
                       else explicar_error(" ".join(lineas[-5:]), self._puerto))
        except Exception as exc:  # errores de esptool, puerto ocupado, etc.
            exito, mensaje = False, explicar_error(str(exc), self._puerto)
        finally:
            sys.stdout = stdout_anterior

        self.terminado.emit(exito, mensaje)
