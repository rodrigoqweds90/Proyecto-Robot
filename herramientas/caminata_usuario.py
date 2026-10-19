"""SEGMENTO: CAMINATA DEL USUARIO (poses "paso usuario", 2026-10-18)
El usuario armo a mano un paso que camina (1.1 a 1.8): inclinar, pierna libre adelante con el femur (40), la de
apoyo atras, centrar. Su 1.8 hacia tres cosas a la vez (izquierda adelante, derecha atras y centrar el peso) y el
robot se ladeaba a la izquierda: el pie izquierdo apoyaba todavia viajando. Aca:
  - 1.8 queda separado en 1.8 (izquierda adelante), 1.9 (derecha atras) y 1.10 (centrar)
  - 1.11 a 1.16: el mismo paso con la otra pierna, para que se pueda repetir sin juntar los pies
  - inclinacion mas chica (cadera 4 y tobillo 8, antes 6 y 12): con 6 y 12 era brusca. Se probo entrar en dos poses
    (media inclinacion antes) y el usuario las vio de mas: se sacaron
Los movimientos de 1.1 a 1.7 son los del usuario; sus originales (y todas las poses viejas) estan en
Documents/RobotControl_respaldo_2026-10-18.
Signos (de sus poses): femur izq (1) + atras, femur der (14) + adelante.
Uso: python caminata_usuario.py   (solo poses; las secuencias: secuencias_finales.py)
"""
import json
import os

DATOS = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "RobotControl")
CARPETA = "paso usuario"
REF = "Inicionx25"
INCLINAR = {0: 4, 3: 8, 12: 8, 15: 4}    # peso al pie derecho; al izquierdo, los mismos con signo contrario
FEMUR = 40
DOBLA = 25               # rodilla de la pierna que pasa por debajo (modo fluido)

# (nombre, peso: -1 izquierdo / +1 derecho / 0 centro, muslo izq, muslo der)
# muslo: -1 atras, 0 vertical, +1 adelante. Un cambio por pose.
POSES = [
    ("1.1", -1, 0, 0),       # peso a la izquierda
    ("1.2", -1, 0, +1),      # derecha adelante (en el aire)
    ("1.3", -1, -1, +1),     # izquierda atras: el cuerpo avanza y la derecha apoya adelante
    ("1.4", 0, -1, +1),      # centrar
    ("1.5", 1, -1, +1),      # peso a la derecha (el pie de adelante)
    ("1.6", 1, -1, 0),       # derecha a vertical: el cuerpo avanza sobre ella
    ("1.7", 1, 0, 0),        # la izquierda pasa por debajo
    ("1.8", 1, +1, 0),       # izquierda adelante, todavia en el aire
    ("1.9", 1, +1, -1),      # derecha atras: el cuerpo avanza y la izquierda apoya adelante
    ("1.10", 0, +1, -1),     # recien ahora centrar
    ("1.11", -1, +1, -1),    # espejo: peso a la izquierda (el pie de adelante)
    ("1.12", -1, 0, -1),
    ("1.13", -1, 0, 0),
    ("1.14", -1, 0, +1),
    ("1.15", -1, -1, +1),
    ("1.16", 0, -1, +1),     # igual a 1.4: de aca se vuelve a 1.5a
]


def pose(ref, peso, izq, der):
    a = dict(ref)
    for c, d in INCLINAR.items():
        a[c] = ref[c] + round(d * peso)
    a[1] = ref[1] - FEMUR * izq
    a[14] = ref[14] + FEMUR * der
    return a


def archivo(nombre):
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in nombre).strip() + ".json"   # como app/storage.py


# ---------------------------------------------------------------------
# Orden de las poses (lo usa secuencias_finales.py para armar las secuencias)
# ---------------------------------------------------------------------
INICIO = ["1.1", "1.2", "1.3", "1.4"]                    # de pies juntos: paso con la derecha
CAMINAR = [n for n, *_ in POSES][4:]                     # 1.5 .. 1.16: paso izquierdo + paso derecho
FINAL = ["1.5", "1.6", "1.7", REF]                       # junta los pies y vuelve a erguido
# para atras: las mismas poses en orden inverso (cada pose sigue haciendo un solo cambio; el peso va al pie de atras
# y la pierna de apoyo, al volver a vertical o adelantarse, lleva el cuerpo hacia atras)
ATRAS_INICIO = ["1.7", "1.6", "1.5", "1.4"]
ATRAS = [n for n, *_ in POSES][3:-1][::-1]               # 1.15 .. 1.4
ATRAS_FINAL = ["1.3", "1.2", "1.1", REF]
# fluido: 4 poses por paso en vez de 6, juntando lo que no se estorba
#  - "centrar" + "peso al otro pie" = un solo movimiento de costado (1.9 -> 1.11 y 1.15 -> 1.5 directo)
#  - "la de apoyo a vertical" + "la otra pasa por debajo, doblada" = a la vez (los dos adelante-atras, con el peso
#    quieto sobre el mismo pie); la rodilla doblada (DOBLA) hace que el pie pase ~9 mm sobre el piso
JUNTAS = {"1.6+7 doblada": ("1.7", {1: -DOBLA, 2: DOBLA}), "1.12+13 doblada": ("1.13", {14: DOBLA, 13: -DOBLA})}
FLUIDO_INICIO = ["1.1", "1.2", "1.3"]
FLUIDO = ["1.5", "1.6+7 doblada", "1.8", "1.9", "1.11", "1.12+13 doblada", "1.14", "1.15"]
FLUIDO_FINAL = FINAL
ATRAS_FLUIDO_INICIO = ["1.7", "1.6", "1.5"]
ATRAS_FLUIDO = FLUIDO[::-1]
ATRAS_FLUIDO_FINAL = ["1.3", "1.2", "1.1", REF]


def guardar_poses():
    """escribe las poses 1.1 .. 1.16 y las dos 'juntas' del modo fluido en la carpeta de la app"""
    pos = os.path.join(DATOS, "posiciones")
    ref = {int(k): v for k, v in json.load(open(os.path.join(pos, REF + ".json"), encoding="utf-8"))["angulos"].items()}
    todas = [(n, pose(ref, peso, i, d)) for n, peso, i, d in POSES]
    for nombre, (base, cambios) in JUNTAS.items():
        _, peso, i, d = next(p for p in POSES if p[0] == base)
        a = pose(ref, peso, i, d)
        for c, v in cambios.items():
            a[c] = ref[c] + v
        todas.append((nombre, a))
    for nombre, a in todas:
        json.dump({"nombre": nombre, "angulos": {str(c): int(v) for c, v in sorted(a.items())}, "carpeta": CARPETA},
                  open(os.path.join(pos, archivo(nombre)), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    return [n for n, _ in todas]


if __name__ == "__main__":
    print("poses:", ", ".join(guardar_poses()))
    print("las secuencias las arma secuencias_finales.py")
