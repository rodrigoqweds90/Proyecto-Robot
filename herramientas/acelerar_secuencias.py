"""SEGMENTO: SECUENCIAS MAS RAPIDAS, PASO POR PASO, SIN QUE NINGUN SERVO QUEDE A MEDIAS
Calcula para cada paso de una secuencia el tiempo minimo con dos limites y usa el mayor:
  1. velocidad del servo: con POSET (movimiento sincronizado) el servo arranca y frena suave, asi que su pico de
     velocidad es 1.5 veces el promedio. Tiene que poder seguirlo con carga:
       MG90S a 6 V: 0.08 s / 60 grados sin carga; MG92B (caderas): 0.10 s / 60 grados. Se usa el 40 % (con carga).
  2. equilibrio: mover el cuerpo rapido corre el punto de apoyo efectivo (centro de masa - h/g * aceleracion).
     Se recorre el paso con el simulador y la curva suave del firmware, instante por instante, y ese punto tiene
     que quedar SEGURIDAD mm adentro de los pies que tocan el piso en ese instante.
Los servos no avisan donde quedaron (no hay realimentacion): por eso se calcula con datos de fabrica y margen.
Las secuencias rapidas NECESITAN la casilla "Movimiento sincronizado" o "Continuo" (POSET).
Uso: python acelerar_secuencias.py [--minimo 150]   (solo muestra el detalle; escribe secuencias_finales.py)
"""
import math
import os
import sys

import numpy as np
from shapely.geometry import MultiPoint, Point

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import simular_caminata as sc  # noqa: E402

# las secuencias rapidas de la app (las arma secuencias_finales.py con estas mismas funciones)
SECUENCIAS = ["Adelante 3 pasos", "Atras 3 pasos", "Costado izq 3 pasos", "Costado der 3 pasos"]
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


def verificar_continuo(nombre_sec, trim, paso_ms=20):
    """modo Continuo de la app (app/curva.py): recorre la curva cada paso_ms y devuelve
    (peor sobra de velocidad del servo en grados/s, peor margen del punto de apoyo efectivo en mm, instante del peor)"""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
    import curva
    pasos = sc.leer(nombre_sec, "secuencias")["pasos"]
    nudos, t = [(0, {str(c): v for c, v in angulos("Inicionx25").items()})], 0
    for p in pasos:
        t += p["duracion_ms"]
        nudos.append((t, {str(c): v for c, v in angulos(p["posicion"]).items()}))
    cv = curva.Curva(nudos)
    muestras, r = [], None
    for k in range(int(cv.total // paso_ms) + 1):
        a = {int(c): v for c, v in cv.en(k * paso_ms).items()}
        r = sc.analizar(a, trim, (0.0, 0.0) if r is None else r["inc"], 2.0)
        muestras.append((a, r))
    # velocidad de cada servo contra lo que puede con carga
    peor_v = 1e9
    for (a0, _), (a1, _) in zip(muestras, muestras[1:]):
        for c in a0:
            v = abs(a1[c] - a0[c]) / (paso_ms / 1000)
            peor_v = min(peor_v, GRADOS_POR_S["MG92B" if c in MG92B else "MG90S"] * CARGA - v)
    # punto de apoyo efectivo: diferencias finitas contra un pie que apoya en los tres instantes
    peor_m, cuando = 1e9, 0
    dt = paso_ms / 1000
    for i in range(1, len(muestras) - 1):
        rs = [muestras[j][1] for j in (i - 1, i, i + 1)]
        comunes = [l for l in ("izq", "der") if all(l in x["toca"] for x in rs)]
        if not comunes:
            continue
        pie = comunes[0]
        rel = [(x["com"] - x["mundo"][pie][1].mean(axis=0))[[0, 2]] for x in rs]
        # aceleracion solo de lo que mueven los servos (marco del cuerpo): el "balanceo" de un pie al otro del
        # simulador es instantaneo y daria aceleraciones falsas; ese balanceo ya se revisa en cada pose quieta
        cuerpo = []
        for j in (i - 1, i, i + 1):
            piernas, com_c, _ = sc.cuerpo(muestras[j][0], trim)
            cuerpo.append((com_c - piernas[pie][1].mean(axis=0))[[0, 2]])
        acel = (cuerpo[2] - 2 * cuerpo[1] + cuerpo[0]) / dt ** 2
        zmp = rel[1] - rs[1]["com"][1] / G * acel
        pies = set().union(*[x["toca"] for x in rs])
        o = rs[1]["mundo"][pie][1].mean(axis=0)
        apoyo = np.vstack([rs[1]["mundo"][l][1][:, [0, 2]] - o[[0, 2]] for l in pies])
        pol = MultiPoint([tuple(q) for q in apoyo]).convex_hull
        d = pol.exterior.distance(Point(*zmp))
        m = d if pol.contains(Point(*zmp)) else -d
        if m < peor_m:
            peor_m, cuando = m, i * paso_ms
    return peor_v, peor_m, cuando


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

if __name__ == "__main__":
    main()
