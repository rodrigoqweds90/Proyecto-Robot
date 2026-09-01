"""SEGMENTO: SUBIR FIRMWARE AL ESP32
Flashea el firmware ya compilado (bootloader + tabla de particiones + programa)
usando esptool, para que la otra persona no necesite instalar PlatformIO ni
Arduino IDE: solo el .exe de esta app y el cable USB.

Los .bin vienen de compilar src/main.cpp con PlatformIO (ver sync_firmware.ps1
en la raiz del proyecto) y se guardan en app/firmware/.
"""

import io
import sys

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

        argv = ["--chip", "esp32", "--port", self._puerto, "--baud", "460800", "write_flash"]
        for direccion, ruta in ARCHIVOS_FIRMWARE:
            argv += [direccion, str(ruta)]

        stdout_anterior = sys.stdout
        sys.stdout = _CapturaLineas(self.linea.emit)
        try:
            import esptool
            esptool.main(argv)
            exito, mensaje = True, "Firmware actualizado correctamente."
        except SystemExit as exc:
            exito = exc.code in (0, None)
            mensaje = "Firmware actualizado correctamente." if exito else "esptool termino con errores (revisa la consola)."
        except Exception as exc:  # errores de esptool, puerto ocupado, etc.
            exito, mensaje = False, f"Error al subir firmware: {exc}"
        finally:
            sys.stdout = stdout_anterior

        self.terminado.emit(exito, mensaje)
