"""SEGMENTO: UBICACION DE DATOS DEL USUARIO
Esta app se va a compilar como un .exe y copiar a otras computadoras, asi que
las poses, secuencias y el mapeo de canales NO se guardan junto al programa
(esa carpeta puede quedar de solo lectura, o borrarse si se reinstala). Se
guardan en la carpeta de datos de la aplicacion de Windows, que siempre es
escribible y sobrevive a mover o actualizar el .exe.
"""

import os
import sys
from pathlib import Path

NOMBRE_APP = "RobotControl"


def directorio_datos():
    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home())
    carpeta = Path(base) / NOMBRE_APP
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def directorio_app():
    """Carpeta donde viven los archivos empaquetados con la app (assets/,
    firmware/) — de solo lectura, a diferencia de directorio_datos(). Cuando
    la app corre como .exe de PyInstaller, esos archivos se extraen a una
    carpeta temporal (sys._MEIPASS); corriendo desde el codigo fuente, es
    simplemente la carpeta app/.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent
