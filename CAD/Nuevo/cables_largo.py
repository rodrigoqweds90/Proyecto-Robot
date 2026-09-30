"""SEGMENTO: LARGO DE CABLE DE CADA SERVO HASTA EL PCA9685
Recorrido por puntos de paso (pegado a los ejes de las articulaciones, donde el cable
casi no se estira al moverse) + holgura por articulacion cruzada + 20 mm de margen.
Coordenadas del robot en mm: X izquierda, Y arriba, Z adelante.
"""
import numpy as np

LARGO_CABLE_MG90S = 250.0     # tipico; medir el de los servos propios
MARGEN = 20.0

# fichas del PCA: cuelgan bajo la placa (componentes abajo), fila de atras
Y_FICHA, Z_FICHA = -6.5, -22.2
GRUPOS_X = (-25.4, -12.7, 2.5, 15.2)       # inicio de cada grupo de 4 canales (visto desde abajo, canal 0 a -X)


def x_canal(c):
    return GRUPOS_X[c // 4] + 1.27 + 2.54 * (c % 4)


def pierna(s):
    atras_cintura = (6 * s, -8, -3)
    atras_cadera = (21 * s, -24, -3)
    eje_femur = (30 * s, -39, 4)
    rodilla = (40 * s, -75, 20)
    eje_tobillo = (30 * s, -111, 4)
    base = [(atras_cintura, 30), (atras_cadera, 10)]
    return {
        "Cadera": base + [((14.8 * s, -25, 28.6), 0)],
        "Femur": base + [(eje_femur, 15), ((35.4 * s, -39, 14.2), 0)],
        "Tibia": base + [(eje_femur, 15), (rodilla, 20), ((35.4 * s, -111, 14.2), 0)],
        "Pie": base + [(eje_femur, 15), (rodilla, 20), (eje_tobillo, 15), ((14.8 * s, -125, 28.6), 0)],
    }


def brazo(s):
    lateral_torso = (28 * s, 10, -15)
    entrada_hombro = (34 * s, 45, 5)
    eje_codo = (62 * s, 30, 30)
    return {
        "Hombro": [(lateral_torso, 0), ((28 * s, 42, 0), 0), ((19.5 * s, 42.4, 25.2), 0)],
        "Codo": [(lateral_torso, 0), (entrada_hombro, 20), ((75.2 * s, 36.4, 34.9), 0)],
        "Mano": [(lateral_torso, 0), (entrada_hombro, 20), (eje_codo, 15), ((66.7 * s, -1, 36.7), 0)],
    }


# canal: (lado, recorrido)
CANALES = {
    0: ("izquierda", pierna(1)["Cadera"]), 1: ("izquierda", pierna(1)["Femur"]),
    2: ("izquierda", pierna(1)["Tibia"]), 3: ("izquierda", pierna(1)["Pie"]),
    4: ("izquierda", brazo(1)["Mano"]), 5: ("izquierda", brazo(1)["Codo"]), 6: ("izquierda", brazo(1)["Hombro"]),
    7: ("", [((10, 16, 0), 0), ((0, 23.5, 31.4), 0)]),
    8: ("", [((29, 20, -15), 0), ((15, 45, -2), 0), ((0, 43.2, 7.9), 0)]),
    9: ("derecha", brazo(-1)["Hombro"]), 10: ("derecha", brazo(-1)["Codo"]), 11: ("derecha", brazo(-1)["Mano"]),
    12: ("derecha", pierna(-1)["Pie"]), 13: ("derecha", pierna(-1)["Tibia"]),
    14: ("derecha", pierna(-1)["Femur"]), 15: ("derecha", pierna(-1)["Cadera"]),
}
NOMBRES = ["Cadera izq", "Femur izq", "Tibia izq", "Pie izq", "Mano izq", "Codo izq", "Hombro izq", "Torso",
           "Cabeza", "Hombro der", "Codo der", "Mano der", "Pie der", "Tibia der", "Femur der", "Cadera der"]


def largo(c):
    puntos = [np.array([x_canal(c), Y_FICHA, Z_FICHA])] + [np.array(p, float) for p, _ in CANALES[c][1]]
    tramo = sum(np.linalg.norm(b - a) for a, b in zip(puntos, puntos[1:]))
    holgura = sum(h for _, h in CANALES[c][1])
    return tramo, holgura, tramo + holgura + MARGEN


if __name__ == "__main__":
    print(f"{'canal':>5}  {'servo':12s} {'recorrido':>9} {'holgura':>8} {'total':>6}  vs {LARGO_CABLE_MG90S:.0f} mm")
    for c in range(16):
        tramo, holgura, total = largo(c)
        estado = "OK" if total <= LARGO_CABLE_MG90S else f"FALTAN {total - LARGO_CABLE_MG90S:.0f} mm"
        print(f"{c:5d}  {NOMBRES[c]:12s} {tramo:9.0f} {holgura:8.0f} {total:6.0f}  {estado}")
