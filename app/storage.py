"""SEGMENTO: GUARDADO DE POSES Y SECUENCIAS
Poses y secuencias como archivos JSON en la carpeta de datos del usuario
(paths.py), sin contraseña ni servidor: son solo archivos locales.
"""

import json

from paths import directorio_datos

POSICIONES_DIR = directorio_datos() / "posiciones"
SECUENCIAS_DIR = directorio_datos() / "secuencias"
POSICIONES_DIR.mkdir(parents=True, exist_ok=True)
SECUENCIAS_DIR.mkdir(parents=True, exist_ok=True)


def _archivo_seguro(nombre):
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in nombre).strip() or "sin_nombre"


def guardar_posicion(nombre, angulos):
    ruta = POSICIONES_DIR / f"{_archivo_seguro(nombre)}.json"
    ruta.write_text(json.dumps({"nombre": nombre, "angulos": angulos}, indent=2, ensure_ascii=False), encoding="utf-8")


def cargar_posiciones():
    posiciones = {}
    for ruta in sorted(POSICIONES_DIR.glob("*.json")):
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        posiciones[datos["nombre"]] = datos["angulos"]
    return posiciones


def borrar_posicion(nombre):
    ruta = POSICIONES_DIR / f"{_archivo_seguro(nombre)}.json"
    if ruta.exists():
        ruta.unlink()


def guardar_secuencia(nombre, pasos, categoria=""):
    # pasos: lista de {"posicion": nombre_posicion, "duracion_ms": int}
    # categoria: etiqueta libre (Avanzar, Retroceder, Girar Izq, ...) para que
    # otro programa (ej. una app de mando por Bluetooth) pueda buscar
    # "la secuencia de tipo Avanzar" sin depender del nombre exacto.
    ruta = SECUENCIAS_DIR / f"{_archivo_seguro(nombre)}.json"
    ruta.write_text(
        json.dumps({"nombre": nombre, "categoria": categoria, "pasos": pasos}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def cargar_secuencias():
    secuencias = {}
    for ruta in sorted(SECUENCIAS_DIR.glob("*.json")):
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        secuencias[datos["nombre"]] = {"categoria": datos.get("categoria", ""), "pasos": datos["pasos"]}
    return secuencias


def borrar_secuencia(nombre):
    ruta = SECUENCIAS_DIR / f"{_archivo_seguro(nombre)}.json"
    if ruta.exists():
        ruta.unlink()


def exportar_todo(ruta, canales, posiciones, secuencias):
    # Un solo archivo autocontenido con todo lo necesario para que OTRO
    # programa (ej. la futura app de mando por Bluetooth) pueda mover el
    # robot sin depender de esta app: el mapeo de canales del PCA9685, las
    # poses, y las secuencias con su categoria.
    datos = {
        "version": 1,
        "canales": canales,
        "posiciones": posiciones,
        "secuencias": secuencias,
    }
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
