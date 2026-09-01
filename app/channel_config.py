"""SEGMENTO: MAPEO DE CANALES DEL PCA9685
Que servo va en cada uno de los 16 pines del PCA9685, y su rango de angulo y
de pulso PWM. Editable desde la app (menu Configuracion > Canales de servos),
sin tocar codigo. Se guarda en la carpeta de datos del usuario (paths.py) para
que sobreviva a copiar la app a otra computadora.
"""

import json

from paths import directorio_datos

RUTA_CONFIG = directorio_datos() / "channels.json"

GRUPOS_SUGERIDOS = ["Pierna derecha", "Pierna izquierda", "Brazo izquierdo", "Brazo derecho", "Torso", "Otro"]

# Mapeo real del robot, usado la primera vez que se abre la app en un equipo nuevo.
_DEFAULT = [
    {"canal": 0,  "nombre": "Tobillo Der", "grupo": "Pierna derecha",   "angMin": -90, "angMax": 90, "pwmMin": 500,  "pwmMax": 2450},
    {"canal": 1,  "nombre": "Muslo Der",   "grupo": "Pierna derecha",   "angMin": -90, "angMax": 90, "pwmMin": 500,  "pwmMax": 2450},
    {"canal": 2,  "nombre": "Rodilla Der", "grupo": "Pierna derecha",   "angMin": -90, "angMax": 90, "pwmMin": 500,  "pwmMax": 2450},
    {"canal": 3,  "nombre": "Cadera Der",  "grupo": "Pierna derecha",   "angMin": -90, "angMax": 90, "pwmMin": 500,  "pwmMax": 2450},
    {"canal": 4,  "nombre": "Tobillo Izq", "grupo": "Pierna izquierda", "angMin": -90, "angMax": 90, "pwmMin": 500,  "pwmMax": 2450},
    {"canal": 5,  "nombre": "Muslo Izq",   "grupo": "Pierna izquierda", "angMin": -90, "angMax": 90, "pwmMin": 500,  "pwmMax": 2450},
    {"canal": 7,  "nombre": "Libre Izq",   "grupo": "Pierna izquierda", "angMin": -90, "angMax": 90, "pwmMin": 500,  "pwmMax": 2450},
    {"canal": 8,  "nombre": "Cadera Izq",  "grupo": "Pierna izquierda", "angMin": -90, "angMax": 90, "pwmMin": 2450, "pwmMax": 500},
    {"canal": 9,  "nombre": "Hombro Izq",  "grupo": "Brazo izquierdo",  "angMin": -90, "angMax": 90, "pwmMin": 500,  "pwmMax": 2450},
    {"canal": 12, "nombre": "Codo Izq",    "grupo": "Brazo izquierdo",  "angMin": -90, "angMax": 90, "pwmMin": 500,  "pwmMax": 2450},
    {"canal": 13, "nombre": "Mano Izq",    "grupo": "Brazo izquierdo",  "angMin": -90, "angMax": 90, "pwmMin": 500,  "pwmMax": 2450},
    {"canal": 10, "nombre": "Hombro Der",  "grupo": "Brazo derecho",    "angMin": -90, "angMax": 90, "pwmMin": 500,  "pwmMax": 2450},
    {"canal": 14, "nombre": "Codo Der",    "grupo": "Brazo derecho",    "angMin": -90, "angMax": 90, "pwmMin": 500,  "pwmMax": 2450},
    {"canal": 15, "nombre": "Mano Der",    "grupo": "Brazo derecho",    "angMin": -90, "angMax": 90, "pwmMin": 500,  "pwmMax": 2450},
    {"canal": 11, "nombre": "Torso",       "grupo": "Torso",            "angMin": -90, "angMax": 90, "pwmMin": 500,  "pwmMax": 2450},
    {"canal": 6,  "nombre": "Cuello",      "grupo": "Torso",            "angMin": -90, "angMax": 90, "pwmMin": 500,  "pwmMax": 2450},
]


def cargar():
    if RUTA_CONFIG.exists():
        try:
            return json.loads(RUTA_CONFIG.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    guardar(_DEFAULT)
    return [dict(item) for item in _DEFAULT]


def guardar(servos):
    RUTA_CONFIG.write_text(json.dumps(servos, indent=2, ensure_ascii=False), encoding="utf-8")


def angulo_a_pulso(servo, angulo):
    if servo["angMax"] == servo["angMin"]:
        return servo["pwmMin"]
    factor = (angulo - servo["angMin"]) / (servo["angMax"] - servo["angMin"])
    pulso = servo["pwmMin"] + factor * (servo["pwmMax"] - servo["pwmMin"])
    return int(round(pulso))


def pulso_a_angulo(servo, pulso):
    if servo["pwmMax"] == servo["pwmMin"]:
        return 0
    factor = (pulso - servo["pwmMin"]) / (servo["pwmMax"] - servo["pwmMin"])
    return servo["angMin"] + factor * (servo["angMax"] - servo["angMin"])
