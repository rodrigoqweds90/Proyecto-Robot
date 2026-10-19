"""SEGMENTO: SECUENCIAS MAS RAPIDAS, PASO POR PASO, SIN QUE NINGUN SERVO QUEDE A MEDIAS
Calcula para cada paso de una secuencia el tiempo minimo con dos limites y usa el mayor:
  1. velocidad del servo: con POSET (movimiento sincronizado) el servo arranca y frena suave, asi que su pico de
     velocidad es 1.5 veces el promedio. Tiene que poder seguirlo con carga:
       MG90S a 6 V: 0.08 s / 60 grados sin carga; MG92B (caderas): 0.10 s / 60 grados. Se usa el 40 % (con carga).
  2. equilibrio: mover el cuerpo rapido corre el punto de apoyo efectivo (centro de masa - h/g * aceleracion).
     Se recorre el paso con el simulador y la curva suave del firmware, instante por instante, y ese punto tiene
     que quedar SEGURIDAD mm adentro de los pies que tocan el piso en ese instante.
Los servos no avisan donde quedaron (no hay realimentacion): por eso se calcula con datos de fabrica y margen.
Las secuencias nuevas se llaman "<nombre> rapido" y NECESITAN la casilla "Movimiento sincronizado" (POSET).
Uso: python acelerar_secuencias.py [--minimo 150] [--escribir]
"""
import json
import math
import os
import sys

import numpy as np
from shapely.geometry import MultiPoint, Point

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import simular_caminata as sc  # noqa: E402

SECUENCIAS = ["Adelante completo", "Atras completo", "Adelante doblando completo", "Costado izq completo",
              "Costado der completo"]
GRADOS_POR_S = {"MG90S": 60 / 0.08, "MG92B": 60 / 0.10}
CARGA = 0.40                 # fraccion de la velocidad sin carga que se usa
PICO = 1.5                   # pico / promedio de la curva suave del firmware
MG92B = {0, 15}              # caderas
SEGURIDAD = 3.0              # mm que el punto de apoyo efectivo tiene que quedar adentro del pie
G = 9810.0                   # mm/s2
ADELANTO_MS = 30             # el movimiento termina 30 ms antes del paso siguiente (2 ticks del firmware)


def arg(nombre, defecto):
    return float(sys.argv[sys.argv.index(nombre) + 1]) if nombre in sys.argv else defecto


def angulos(nombre):
    return {int(k): v for k, v in sc.leer(nombre, "posiciones")["angulos"].items()}


def t_servo(a, b):
    """ms minimos para que todos los servos lleguen (el mas exigido manda)"""
    peor = 0.0
    for c in a:
        v = GRADOS_POR_S["MG92B" if c in MG92B else "MG90S"] * CARGA
        peor = max(peor, PICO * abs(b.get(c, 0) - a[c]) / v * 1000)
    return peor


def recorrido(anterior, b, trim, inc, n=16):
    """el paso simulado en n tramos (en angulos, como el firmware): por tramo, centro de masa y lo que apoya,
    todo medido contra un pie que queda en el piso (el marco del simulador va con la pelvis)"""
    tramos, r = [], None
    for k in range(n + 1):
        f = k / n
        mezcla = {c: anterior[c] + (b.get(c, 0) - anterior[c]) * f for c in anterior}
        r = sc.analizar(mezcla, trim, inc if r is None else r["inc"], 2.0)
        tramos.append(r)
    pie = next((l for l in ("izq", "der") if l in tramos[0]["toca"] and l in tramos[-1]["toca"]), tramos[0]["toca"][0])
    # un pie que apoya al principio o al final del paso cuenta como apoyo todo el paso: no se despega en un
    # instante fijo, sigue en el piso mientras la inercia empuje hacia su lado (y el que baja, apoya antes)
    pies = set(tramos[0]["toca"]) | set(tramos[-1]["toca"])
    out = []
    for r in tramos:
        base = r["mundo"][pie][1]
        o = base.mean(axis=0)
        com = (r["com"] - o)[[0, 2]]
        apoyo = np.vstack([r["mundo"][l][1][:, [0, 2]] - o[[0, 2]] for l in pies])
        out.append((com, r["com"][1], MultiPoint([tuple(q) for q in apoyo]).convex_hull))
    return out, tramos[-1]


def margen_dinamico(tramos, T):
    """menor distancia (mm) del punto de apoyo efectivo al borde de lo que apoya, durante el paso de T ms.
    El firmware recorre el paso con s = 3f^2 - 2f^3: el angulo (y aprox. el centro de masa) sigue esa curva."""
    n = len(tramos) - 1
    peor = 1e9
    for i in range(1, 40):
        f = i / 40
        s_ = 3 * f * f - 2 * f ** 3
        s2 = (6 - 12 * f) / (T / 1000.0) ** 2            # aceleracion de s respecto del tiempo
        x = s_ * n
        k = min(int(x), n - 1)
        w = x - k
        com = tramos[k][0] * (1 - w) + tramos[k + 1][0] * w
        dcom = (tramos[k + 1][0] - tramos[k][0]) * n      # derivada respecto de s
        h = tramos[k][1]
        zmp = com - h / G * dcom * s2
        poligono = tramos[k + (1 if w > 0.5 else 0)][2]
        d = poligono.exterior.distance(Point(*zmp)) if poligono.area > 1 else 0.0
        peor = min(peor, d if poligono.contains(Point(*zmp)) else -d)
    return peor


def t_equilibrio(tramos, minimo):
    """ms minimos para que el punto de apoyo efectivo no salga de los pies (con SEGURIDAD mm de resguardo)"""
    estatico = margen_dinamico(tramos, 1e9)
    for T in range(int(minimo), 1210, 10):
        if margen_dinamico(tramos, T) >= min(SEGURIDAD, estatico):
            return T, estatico
    return 1200, estatico


def analizar(nombre_sec, trim, minimo):
    pasos = sc.leer(nombre_sec, "secuencias")["pasos"]
    previo, ra = (0.0, 0.0), None
    anterior = angulos("Inicionx25")
    ra = sc.analizar(anterior, trim, previo, 2.0)
    filas = []
    for p in pasos:
        b = angulos(p["posicion"])
        tramos, r = recorrido(anterior, b, trim, ra["inc"])
        ts = t_servo(anterior, b)
        te, estatico = t_equilibrio(tramos, minimo)
        # la app termina cada movimiento ADELANTO_MS antes del paso siguiente (main_window._aplicar_pose): el
        # movimiento dura t - ADELANTO_MS y ese es el que tiene que alcanzar
        t = int(math.ceil((max(ts, te, minimo) + ADELANTO_MS) / 10.0) * 10)
        t = min(t, p["duracion_ms"])     # nunca mas lento que lo ya probado en el robot (el modelo usa masas estimadas)
        filas.append({"posicion": p["posicion"], "antes": p["duracion_ms"], "nuevo": t, "servo": ts, "equilibrio": te,
                      "estatico": estatico, "con_antes": margen_dinamico(tramos, p["duracion_ms"]),
                      "con_nuevo": margen_dinamico(tramos, t),
                      "salto": max(abs(b.get(c, 0) - anterior[c]) for c in anterior)})
        anterior, ra = b, r
    return filas


def main():
    minimo = arg("--minimo", 150)
    ref = angulos("Inicionx25")
    trim = {c: ref[c] for c in sc.cn.PIERNAS}
    for nombre in SECUENCIAS:
        filas = analizar(nombre, trim, minimo)
        antes, ahora = sum(f["antes"] for f in filas), sum(f["nuevo"] for f in filas)
        print(f"\n=== {nombre}: {antes / 1000:.1f} s -> {ahora / 1000:.1f} s ({100 * (1 - ahora / antes):.0f} % mas rapido)")
        print(f"{'pose':34s} {'salto':>5s} {'servo':>6s} {'equil.':>6s} {'quieto':>7s} {'a 400':>7s} {'nuevo':>6s} {'margen':>7s}")
        vistos = set()
        for f in filas:
            if f["posicion"] in vistos:
                continue                     # las vueltas repetidas dan lo mismo
            vistos.add(f["posicion"])
            print(f"{f['posicion'][:34]:34s} {f['salto']:4.0f}° {f['servo']:5.0f}ms {f['equilibrio']:5.0f}ms "
                  f"{f['estatico']:5.1f}mm {f['con_antes']:5.1f}mm {f['nuevo']:5d}ms {f['con_nuevo']:5.1f}mm")
        if "--escribir" in sys.argv:
            nuevo = nombre.replace(" completo", "") + " rapido"
            d = sc.leer(nombre, "secuencias")
            d["nombre"] = nuevo
            d["pasos"] = [{"posicion": f["posicion"], "duracion_ms": f["nuevo"]} for f in filas]
            with open(os.path.join(sc.cn.DATOS, "secuencias", nuevo + ".json"), "w", encoding="utf-8") as fh:
                json.dump(d, fh, indent=2, ensure_ascii=False)
            print(f"-> secuencia '{nuevo}'")


if __name__ == "__main__":
    main()
