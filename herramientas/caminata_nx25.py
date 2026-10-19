"""SEGMENTO: CAMINATA DEL NX25 -> POSES Y SECUENCIA DE LA APP
Toma la marcha hacia adelante del NX25 (22 cuadros, pie que avanza en arco: CAD/Nuevo/poses_marcha.py) y su
cinematica inversa, y la escribe como poses y una secuencia en la carpeta de datos de la app (RobotControl).

Signos de los servos (probados por el usuario en el robot, desde su pose "unoo"):
  - cadera izquierda (0) +: la pierna se abre hacia afuera. La derecha (15) tiene el eje para el mismo lado
    (CAD: los dos ejes de cadera salen hacia atras), asi que + es el mismo giro: la pierna derecha se cierra
  - femur izquierdo (1) +: la pierna va hacia atras. El derecho (14) esta en espejo: + va hacia adelante
    (lo confirman las poses del usuario: agachado = femur -10 / +10, tibia +10 / -10)
  - pie izquierdo (3) +: sube el borde de afuera. El derecho (12) tiene el eje como el izquierdo
  - pie plano: el pie gira lo mismo que la cadera pero al reves
Ajustes finos (trims): la pose de referencia es el robot PARADO RECTO (piernas verticales, pies planos) con los
servos ya calibrados; sus valores se suman a todos los canales de las piernas, y los brazos, torso y cabeza se
quedan como en ella.
Signos de los 8 servos probados uno por uno en el robot (2026-10-18): cadera izq + abre, der + cierra; femur izq +
atras; tibia izq + lleva el pie atras; pie izq + sube el borde de afuera, der + el de adentro. X va como en el NX25
(el pie que se levanta avanza en +X); se habia invertido porque "caminaba hacia atras", pero eso era un sintoma de que
no levantaba los pies, no del signo.
Uso: python caminata_nx25.py [--ref "Parado recto"] [--ms 300] [--paso 18] [--sube 18] [--balanceo 20] [--precarga 0]
     [--sin_escribir]
"""
import json
import math
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "..", "CAD", "Nuevo"))
import poses_marcha as pm  # noqa: E402

DATOS = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "RobotControl")
CARPETA = "Caminata NX25"
PREFIJO = "NX25 marcha"
SECUENCIA = "Caminar NX25"
PIERNAS = (0, 1, 2, 3, 12, 13, 14, 15)
ADELANTE = -1.0          # con la X del NX25 tal cual el robot camina hacia atras (probado dos veces, 2026-10-18)
LATERAL = 1.0            # Z del NX25: con los signos probados, + lleva la pelvis a la derecha cuando sube el pie izquierdo
# compensacion del juego (1-2 grados por servo, medido en las caderas MG92B): con 20 mm de balanceo las piernas se
# inclinaban 3-4 grados en vez de 11 y el peso no pasaba al pie de apoyo
BALANCEO = 20.0          # mm de balanceo lateral (el NX25 usa 20)
PASO = 18.0              # mm de paso: con eslabones de 28.7 mm, 18 es el maximo con el muslo en -20..60 y la canilla en
SUBE = 18.0              # -60..20 (rango sin choques del CAD); con 20 de paso el muslo ya llega a -20.4
PRECARGA = 0.0           # grados extra en las caderas con un pie en el aire (probado 3; lo que camino fue con 0)
PAUSA = 1.0              # el cuadro antes de despegar cada pie dura esto por la duracion normal
# ajustes del usuario en el robot (2026-10-18): el pie de apoyo mas inclinado justo antes de levantar el otro y al
# apoyarlo; con esto el peso pasa al pie de apoyo y el robot camina. {cuadro: {canal: grados que se suman}}
AJUSTES_USUARIO = {4: {12: -8}, 10: {12: -10}, 14: {3: 10}, 15: {3: 8}}


def arg(nombre, defecto):
    return sys.argv[sys.argv.index(nombre) + 1] if nombre in sys.argv else defecto


def canales(pie_der, pie_izq, trim, precarga=0.0):
    """(X, Y, Z) de cada pie -> grados de la app por canal (sin los brazos)"""
    lat_d, mus_d, rod_d = pm.ik(ADELANTE * pie_der[0], pie_der[1], pie_der[2])
    lat_i, mus_i, rod_i = pm.ik(ADELANTE * pie_izq[0], pie_izq[1], pie_izq[2])
    lat_d, lat_i = LATERAL * lat_d, LATERAL * lat_i
    # precarga: con un pie en el aire la pelvis cae hacia ese lado por el juego; cadera + baja el lado izquierdo de la
    # pelvis (gira la pelvis respecto de la pierna de apoyo), asi que se resta hacia el lado del balanceo
    pc = -precarga * math.copysign(1.0, lat_i) if precarga else 0.0
    return {
        0: trim[0] + lat_i + pc, 3: trim[3] - lat_i, 1: trim[1] - mus_i, 2: trim[2] - rod_i,          # izquierda
        15: trim[15] + lat_d + pc, 12: trim[12] - lat_d, 14: trim[14] + mus_d, 13: trim[13] + rod_d,  # derecha
    }


def main():
    ref = arg("--ref", "Parado recto")
    ms = int(arg("--ms", "300"))
    pose_ref = json.load(open(os.path.join(DATOS, "posiciones", ref + ".json"), encoding="utf-8"))["angulos"]
    ref_ang = {int(k): v for k, v in pose_ref.items()}
    trim = {c: ref_ang.get(c, 0) for c in PIERNAS}
    marcha = dict(pm.MARCHA_ARCO, SideS=float(arg("--balanceo", BALANCEO)), Fws=float(arg("--paso", PASO)) / 2,
                  Up=float(arg("--sube", SUBE)))
    precarga = float(arg("--precarga", PRECARGA))
    cuadros = pm.cuadros_arco(marcha)
    H = marcha["H0"]
    en_el_aire = [pd[1] < H - 0.01 or pi[1] < H - 0.01 for pd, pi, _ in cuadros]
    poses, duraciones = [], []
    for k, (pd, pi, _) in enumerate(cuadros):
        a = dict(ref_ang)                                  # brazos, torso y cabeza como en la referencia
        a.update({c: v for c, v in canales(pd, pi, trim, precarga if en_el_aire[k] else 0.0).items()})
        for c, d in AJUSTES_USUARIO.get(k + 1, {}).items():
            a[c] += d
        poses.append((f"{PREFIJO} {k + 1:02d}", {str(c): int(round(v)) for c, v in sorted(a.items())}))
        despega = en_el_aire[(k + 1) % len(cuadros)] and not en_el_aire[k]
        duraciones.append(int(ms * PAUSA) if despega else ms)
    # tabla para revisar
    print(f"marcha: paso {2 * marcha['Fws']:.0f} mm, sube {marcha['Up']:.0f} mm, balanceo lateral {marcha['SideS']:.0f} mm, "
          f"altura {marcha['H0']:.0f} mm, precarga de cadera {precarga:.0f} grados; referencia '{ref}', {ms} ms por cuadro "
          f"({int(ms * PAUSA)} antes de despegar)")
    print("cuadro  " + " ".join(f"{c:>4}" for c in PIERNAS) + "    ms")
    for (n, a), d in zip(poses, duraciones):
        print(f"{n[-2:]:>6}  " + " ".join(f"{a[str(c)]:>4}" for c in PIERNAS) + f"  {d:>4}")
    if "--sin_escribir" in sys.argv:
        return
    os.makedirs(os.path.join(DATOS, "posiciones"), exist_ok=True)
    os.makedirs(os.path.join(DATOS, "secuencias"), exist_ok=True)
    for n, a in poses:
        with open(os.path.join(DATOS, "posiciones", n + ".json"), "w", encoding="utf-8") as f:
            json.dump({"nombre": n, "angulos": a, "carpeta": CARPETA}, f, indent=2, ensure_ascii=False)
    with open(os.path.join(DATOS, "secuencias", SECUENCIA + ".json"), "w", encoding="utf-8") as f:
        json.dump({"nombre": SECUENCIA, "categoria": "Caminar",
                   "pasos": [{"posicion": n, "duracion_ms": d} for (n, _), d in zip(poses, duraciones)]}, f, indent=2, ensure_ascii=False)
    ruta_c = os.path.join(DATOS, "carpetas_poses.json")
    carpetas = json.load(open(ruta_c, encoding="utf-8")) if os.path.exists(ruta_c) else []
    if CARPETA not in carpetas:
        carpetas = sorted(carpetas + [CARPETA])
        with open(ruta_c, "w", encoding="utf-8") as f:
            json.dump(carpetas, f, indent=2, ensure_ascii=False)
    print(f"\n{len(poses)} poses en la carpeta '{CARPETA}' y la secuencia '{SECUENCIA}' en {DATOS}")


if __name__ == "__main__":
    main()
