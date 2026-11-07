"""SEGMENTO: GUARDADO DE POSES Y SECUENCIAS
Poses y secuencias como archivos JSON en la carpeta de datos del usuario
(paths.py), sin contraseña ni servidor: son solo archivos locales.
"""

import json

from paths import directorio_datos

POSICIONES_DIR = directorio_datos() / "posiciones"
SECUENCIAS_DIR = directorio_datos() / "secuencias"
ASIGNACIONES_MANDO_ARCHIVO = directorio_datos() / "asignaciones_mando.json"
CARPETAS_ARCHIVO = directorio_datos() / "carpetas_poses.json"
POSICIONES_DIR.mkdir(parents=True, exist_ok=True)
SECUENCIAS_DIR.mkdir(parents=True, exist_ok=True)


def _archivo_seguro(nombre):
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in nombre).strip() or "sin_nombre"


def guardar_posicion(nombre, angulos, carpeta=""):
    # carpeta: etiqueta libre para agrupar poses en la lista (ej. "Intento 3").
    # Cadena vacia = la pose no esta en ninguna carpeta; igual se sigue viendo
    # en el filtro "Todas", nunca se oculta ni se borra por no tener carpeta.
    ruta = POSICIONES_DIR / f"{_archivo_seguro(nombre)}.json"
    ruta.write_text(
        json.dumps({"nombre": nombre, "angulos": angulos, "carpeta": carpeta}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def cargar_posiciones():
    """Devuelve (posiciones, carpetas): {nombre: angulos} y {nombre: carpeta}.

    Se devuelven separados a proposito: el resto de la app (y el archivo de
    exportacion que consume otro programa) sigue trabajando con el dict plano
    {nombre: angulos} de siempre, sin tener que saber nada de carpetas.
    """
    posiciones = {}
    carpetas = {}
    for ruta in sorted(POSICIONES_DIR.glob("*.json")):
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        posiciones[datos["nombre"]] = datos["angulos"]
        # .get: las poses guardadas antes de que existieran las carpetas no
        # tienen el campo, y tienen que seguir cargando igual.
        carpetas[datos["nombre"]] = datos.get("carpeta", "")
    return posiciones, carpetas


def borrar_posicion(nombre):
    ruta = POSICIONES_DIR / f"{_archivo_seguro(nombre)}.json"
    if ruta.exists():
        ruta.unlink()


def renombrar_posicion(nombre_viejo, nombre_nuevo, angulos, carpeta=""):
    # Se borra primero y se escribe despues: si los dos nombres caen en el
    # mismo archivo (_archivo_seguro puede colapsar caracteres raros), el
    # orden inverso borraria la pose recien escrita.
    borrar_posicion(nombre_viejo)
    guardar_posicion(nombre_nuevo, angulos, carpeta)


def guardar_carpetas(carpetas):
    # La lista de carpetas se guarda aparte de las poses para que una carpeta
    # recien creada (todavia sin ninguna pose adentro) no desaparezca al
    # cerrar la app. Si solo se dedujera de las poses, crear una carpeta vacia
    # no serviria de nada.
    CARPETAS_ARCHIVO.write_text(
        json.dumps(sorted(c for c in carpetas if c), indent=2, ensure_ascii=False), encoding="utf-8"
    )


def cargar_carpetas():
    if CARPETAS_ARCHIVO.exists():
        try:
            return json.loads(CARPETAS_ARCHIVO.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return []


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


def guardar_asignaciones_mando(asignaciones):
    # asignaciones: {"version": 2, "botones": {"A": {"tipo": "secuencia", "valor": "Caminar",
    # "repetir": true}, ...}}. Que hace cada boton del mando (ver widgets/mando_panel.py).
    # Esto queda en la PC; al robot le llega con "Enviar al robot" de la pestana Mando.
    ASIGNACIONES_MANDO_ARCHIVO.write_text(json.dumps(asignaciones, indent=2, ensure_ascii=False), encoding="utf-8")


def cargar_asignaciones_mando():
    if ASIGNACIONES_MANDO_ARCHIVO.exists():
        try:
            return json.loads(ASIGNACIONES_MANDO_ARCHIVO.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def exportar_todo(ruta, canales, posiciones, secuencias, carpetas_poses=None):
    # Un solo archivo autocontenido con todo lo necesario para que OTRO
    # programa (ej. la futura app de mando por Bluetooth) pueda mover el
    # robot sin depender de esta app: el mapeo de canales del PCA9685, las
    # poses, y las secuencias con su categoria.
    # "carpetas_poses" es solo organizacion de ESTA app (para no perderla al
    # exportar/importar como respaldo); quien solo quiera mover el robot lo
    # puede ignorar sin problema, por eso va en una clave aparte y no metido
    # dentro de cada pose.
    datos = {
        "version": 1,
        "canales": canales,
        "posiciones": posiciones,
        "secuencias": secuencias,
        "carpetas_poses": carpetas_poses or {},
    }
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")


def importar_todo(ruta):
    # Inverso de exportar_todo: solo LEE y devuelve lo que hay en el archivo,
    # sin escribir nada a disco todavia -- quien llama decide que hacer con
    # cada parte (ver PositionsPanel.importar_posiciones / SequencePanel.importar_secuencias).
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return (
        datos.get("canales", []),
        datos.get("posiciones", {}),
        datos.get("secuencias", {}),
        datos.get("carpetas_poses", {}),
    )
