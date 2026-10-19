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
Uso: python caminata_usuario.py [--ms 400] [--pasos 3]
"""
import json
import os
import sys

DATOS = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "RobotControl")
CARPETA = "paso usuario"
REF = "Inicionx25"
INCLINAR = {0: 4, 3: 8, 12: 8, 15: 4}    # peso al pie derecho; al izquierdo, los mismos con signo contrario
FEMUR = 40
DOBLA = 25               # rodilla de la pierna que pasa por debajo, en "Adelante doblando completo"

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


def main():
    ms = int(sys.argv[sys.argv.index("--ms") + 1]) if "--ms" in sys.argv else 400
    repetir = int(sys.argv[sys.argv.index("--pasos") + 1]) if "--pasos" in sys.argv else 3
    pos, sec = os.path.join(DATOS, "posiciones"), os.path.join(DATOS, "secuencias")
    ref = {int(k): v for k, v in json.load(open(os.path.join(pos, REF + ".json"), encoding="utf-8"))["angulos"].items()}
    for nombre, peso, i, d in POSES:
        a = pose(ref, peso, i, d)
        json.dump({"nombre": nombre, "angulos": {str(c): int(v) for c, v in sorted(a.items())}, "carpeta": CARPETA},
                  open(os.path.join(pos, archivo(nombre)), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"{nombre:6s} " + " ".join(f"{c}:{a[c]:>4}" for c in (0, 3, 12, 15, 1, 14)))
    # lo de versiones anteriores ya no se usa (ciclo 01..12, medias inclinaciones)
    for n in ("1.1a", "1.5a", "1.11a"):
        if os.path.exists(os.path.join(pos, archivo(n))):
            os.remove(os.path.join(pos, archivo(n)))
    for k in range(1, 13):
        if os.path.exists(os.path.join(pos, f"ciclo {k:02d}.json")):
            os.remove(os.path.join(pos, f"ciclo {k:02d}.json"))
    if os.path.exists(os.path.join(sec, "Paso usuario ciclo.json")):
        os.remove(os.path.join(sec, "Paso usuario ciclo.json"))
    nombres = [n for n, *_ in POSES]
    inicio = nombres[:4]                      # 1.1 .. 1.4
    caminar = nombres[4:]                     # 1.5 .. 1.16 (dos pasos, se repite en bucle)
    final = ["1.5", "1.6", "1.7", REF]        # junta los pies y vuelve a erguido
    # para atras: las mismas poses en orden inverso (cada pose sigue haciendo un solo cambio; el peso ahora va al pie
    # de atras y la pierna de apoyo, al volver a vertical o adelantarse, lleva el cuerpo hacia atras)
    atras_inicio = ["1.7", "1.6", "1.5", "1.4"]          # de erguido: inverso de "final"
    atras = nombres[3:-1][::-1]                          # 1.15 .. 1.4 (dos pasos, se repite en bucle)
    atras_final = ["1.3", "1.2", "1.1", REF]             # inverso de "inicio"
    # prueba: la pierna que pasa por debajo (1.7 izquierda, 1.13 derecha) dobla la rodilla para que el pie pase mas
    # alto; el resto es igual. Poses aparte para no tocar "Adelante completo", que ya funciona
    dobladas = {"1.7": ("1.7 doblada", {1: -DOBLA, 2: DOBLA}), "1.13": ("1.13 doblada", {14: DOBLA, 13: -DOBLA})}
    for base, (nombre, cambios) in dobladas.items():
        _, peso, i, d = next(p for p in POSES if p[0] == base)
        a = pose(ref, peso, i, d)
        for c, v in cambios.items():
            a[c] = ref[c] + v
        json.dump({"nombre": nombre, "angulos": {str(c): int(v) for c, v in sorted(a.items())}, "carpeta": CARPETA},
                  open(os.path.join(pos, archivo(nombre)), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    caminar_doblando = [dobladas[n][0] if n in dobladas else n for n in caminar]
    # solo las completas (pedido del usuario): de erguido, varios pasos y de vuelta a erguido
    secuencias = {"Adelante completo": inicio + caminar * repetir + final,
                  "Atras completo": atras_inicio + atras * repetir + atras_final,
                  "Adelante doblando completo": inicio + caminar_doblando * repetir + final}
    for nombre, pasos in secuencias.items():
        json.dump({"nombre": nombre, "categoria": "Retroceder" if nombre.startswith("Atras") else "Caminar", "pasos": [{"posicion": p, "duracion_ms": ms} for p in pasos]},
                  open(os.path.join(sec, nombre + ".json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"secuencia '{nombre}': {len(pasos)} poses de {ms} ms")


if __name__ == "__main__":
    main()
