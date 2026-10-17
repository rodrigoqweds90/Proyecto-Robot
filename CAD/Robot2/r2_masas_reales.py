"""ROBOT 2 - MASAS REALES: centro de masa con las masas medidas/fichas de la electronica, masa oculta de cables
y tornilleria, y casos de estabilidad (brazos al frente, apoyo simple) con los torques de servo que piden.
Uso: python r2_masas_reales.py [bateria_g] [relleno]   (por defecto 62 g y d.RELLENO)
"""
import json
import os
import sys

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import r2_diseno as d  # noqa: E402
import r2_revisar as rv  # noqa: E402

G = 9.81
CABLES = 0.10           # masa oculta: 10 % de la electronica (cables, Dupont, estano, M2/M3), repartida en cada componente
MASAS = {"MG90S": 13.4, "MG92B": 13.8, "bateria": 62.0, "PCA9685": 5.0, "ESP32": 10.0, "XL4015": 14.0,
         "IMU": 2.0, "OLED": 3.0, "interruptor": 2.0}
TORQUE_STALL = {"MG90S": 0.216, "MG92B": 0.343}     # N m a 6 V (2.2 y 3.5 kgf cm, fichas TowerPro)


# =====================================================================
# SEGMENTO: CUERPOS (nombre, masa g, centro mm, tipo)
# =====================================================================
def tipos_servo():
    t = {f"servo_{k}_{l}": tp for s, l in ((1, "izq"), (-1, "der")) for k, (_, tp) in d.servos(s).items()}
    t.update({f"servo_{k}": tp for k, (_, tp) in d.servos_centro().items()})
    return t


def cuerpos(bateria=MASAS["bateria"], relleno=d.RELLENO):
    masas = dict(MASAS, bateria=bateria)
    out = []
    for n, prims in d.piezas().items():
        m = rv.malla_pieza(prims)
        out.append([n, m.volume() / 1000 * d.DENSIDAD_PLA * relleno, np.array(rv.a_trimesh(m).center_mass), "pla"])
    tipo = tipos_servo()
    for n, malla, _ in rv.mallas_componentes():
        out.append([n, masas[tipo.get(n, n)], np.array(malla.center_mass), "elec"])
    for n, _, p in d.EXTRAS:
        if n in masas:
            out.append([n, masas[n], np.array(p, float), "elec"])
    for c in out:
        if c[3] == "elec":
            c[1] *= 1 + CABLES
    return out


def cdm(cs):
    M = sum(c[1] for c in cs)
    return M, sum(c[1] * c[2] for c in cs) / M


# =====================================================================
# SEGMENTO: CASOS
# =====================================================================
BRAZO = ("R2_hombro", "R2_brazo", "R2_antebrazo", "servo_rolido_hombro", "servo_codo")
PIERNA_IZQ = ("cadera_izq", "muslo_izq", "muslo_link_izq", "rodilla_izq", "canilla_izq", "canilla_link_izq", "tobillo_izq")


def rot_x(p, piv, th):
    dy, dz = p[1] - piv[1], p[2] - piv[2]
    return np.array([p[0], piv[1] + dy * np.cos(th) - dz * np.sin(th), piv[2] + dy * np.sin(th) + dz * np.cos(th)])


def apoyo_simple(cs, th):
    """apoyo en el pie izquierdo: cadera y tobillo rolan th (paralelo), el torso queda derecho"""
    L = d.CADERA_Y - d.ROLIDO_TOBILLO_Y
    piv = np.array([d.CADERA_X, d.ROLIDO_TOBILLO_Y])
    out = []
    for n, m, p, k in cs:
        q = p.copy()
        if n.endswith(PIERNA_IZQ):
            dx, dy = p[0] - piv[0], p[1] - piv[1]
            q[0], q[1] = piv[0] + dx * np.cos(th) + dy * np.sin(th), piv[1] - dx * np.sin(th) + dy * np.cos(th)
        elif n != "R2_pie_izq":
            q[0] += L * np.sin(th)
            q[1] += L * (np.cos(th) - 1)
        out.append([n, m, q, k])
    return out


def analizar(bateria=MASAS["bateria"], relleno=d.RELLENO):
    cs = cuerpos(bateria, relleno)
    M, c = cdm(cs)
    suelo = d.SUELA_Y
    x0, x1, z0, z1 = d.PIE
    h = c[1] - suelo
    mrg = {"adelante": z1 - c[2], "atras": c[2] - z0, "lateral": x1 - abs(c[0])}
    r = {"bateria_g": bateria, "relleno": relleno, "total_g": round(M, 1),
         "pla_g": round(sum(x[1] for x in cs if x[3] == "pla"), 1),
         "electronica_con_cables_g": round(sum(x[1] for x in cs if x[3] == "elec"), 1),
         "cdm_mm": np.round(c, 1).tolist(), "altura_cdm_mm": round(h, 1),
         "margen_mm": {k: round(v, 1) for k, v in mrg.items()},
         "acel_vuelco_g": {k: round(v / h, 2) for k, v in mrg.items()}}
    # brazos al frente 90 grados
    piv = np.array([0, d.HOMBRO_Y, 0.0])
    cb = [[n, m, rot_x(p, piv, np.radians(-90)) if n.startswith(BRAZO) else p, k] for n, m, p, k in cs]
    _, c2 = cdm(cb)
    r["brazos_al_frente"] = {"cdm_mm": np.round(c2, 1).tolist(), "acel_vuelco_adelante_g": round((z1 - c2[2]) / (c2[1] - suelo), 2)}
    mb, cbz = cdm([x for x in cb if x[0].startswith(BRAZO) and x[0].endswith("izq")])
    r["torque_hombro_Nm"] = round(mb / 1000 * G * cbz[2] / 1000, 3)
    # apoyo simple: angulo de cadera para llevar el CdM al centro del pie y a 10 mm del borde interior
    r["apoyo_simple"] = {}
    for etiqueta, x_obj in (("centro_pie", (x0 + x1) / 2), ("borde_mas_10", x0 + 10)):
        lo, hi = 0.0, np.radians(40)
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if cdm(apoyo_simple(cs, mid))[1][0] < x_obj else (lo, mid)
        a = apoyo_simple(cs, lo)
        arriba = [x for x in a if x[0] != "R2_pie_izq" and not x[0].endswith(PIERNA_IZQ)]
        ms, csup = cdm(arriba)
        t = ms / 1000 * G * abs(csup[0] - (d.CADERA_X + (d.CADERA_Y - d.ROLIDO_TOBILLO_Y) * np.sin(lo))) / 1000
        r["apoyo_simple"][etiqueta] = {"cadera_deg": round(np.degrees(lo), 1), "torque_cadera_Nm": round(t, 3),
                                       "pct_stall_MG92B": round(100 * t / TORQUE_STALL["MG92B"])}
    # paralelogramos agachado 30 grados: T = W_soportado * L * sin(30) (el momento lo toman los eslabones)
    bajo = {"muslo": PIERNA_IZQ[1:], "canilla": ("canilla_izq", "canilla_link_izq", "tobillo_izq")}
    r["paralelogramo_30deg"] = {}
    for k, excl in bajo.items():
        w = sum(m for n, m, _, _ in cs if n != "R2_pie_izq" and not n.endswith(excl))
        t = w / 1000 * G * d.LARGO / 1000 * 0.5
        r["paralelogramo_30deg"][k] = {"torque_Nm": round(t, 3), "pct_stall_MG90S": round(100 * t / TORQUE_STALL["MG90S"])}
    return r, cs


if __name__ == "__main__":
    bat = float(sys.argv[1]) if len(sys.argv) > 1 else MASAS["bateria"]
    rel = float(sys.argv[2]) if len(sys.argv) > 2 else d.RELLENO
    print(json.dumps(analizar(bat, rel)[0], indent=1))
