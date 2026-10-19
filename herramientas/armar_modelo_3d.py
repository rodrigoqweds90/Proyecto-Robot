"""SEGMENTO: MODELO 3D PARA EL VISOR (se corre una vez, o cuando cambie el CAD)
Toma las piezas del ensamble Robot_en_soporte en su lugar (transformaciones guardadas desde Inventor en
datos_robot3d/pose_recta_inventor.json) y las agrupa por lo que mueve cada servo de pierna:
  cuerpo (pelvis, torso, cabeza, brazos) | cadera | muslo A / muslo B (las dos barras del paralelogramo) | rodilla |
  canilla A / canilla B | tobillo | pie        (cada grupo de pierna, izquierda y derecha)
Guarda las mallas en datos_robot3d/modelo.npz, en el marco del simulador: origen a la altura del eje de cadera y en
el plano de los ejes laterales, x = izquierda del robot, y = arriba, z = adelante (mm).
Uso: python armar_modelo_3d.py
"""
import json
import os

import numpy as np
import pyvista as pv
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(BASE, "datos_robot3d")
CAD = os.path.join(BASE, "..", "CAD", "Nuevo")
ORIGEN = np.array([0.0, -25.0, 17.7])     # eje de cadera en el CAD (y) y plano de los ejes laterales (z)
CARAS_MAX = {"cuerpo": 30000}            # caras por grupo (el resto 6000), para que el visor vaya fluido


def malla(p):
    stl = p.get("stl")
    if not stl or not str(stl).lower().endswith(".stl"):
        nombre = p["nombre"].split(":")[0]
        stl = os.path.join(CAD, "stl", nombre + ".stl")      # torso y cabeza: exportados desde su .ipt
    if not os.path.exists(stl):
        return None
    m = trimesh.load(stl, force="mesh")
    m.apply_transform(np.array(p["M"]))
    m.apply_translation(-ORIGEN)
    return m


def grupo(nombre, m):
    """(grupo, lado, es_servo) de una pieza, o None si no va"""
    if nombre.startswith("Soporte"):
        return None
    c = m.bounds.mean(axis=0)
    lado = "izq" if c[0] > 0 else "der"
    servo = nombre.startswith("MG90S")
    pierna = c[1] < -8 and abs(c[0]) < 50
    if not pierna:
        return ("cuerpo", "", servo)
    y = c[1]                                    # ya en el marco del simulador (0 = eje de cadera)
    if nombre.startswith(("Bracket04", "Bracket05")):
        return ("pie", lado, servo)
    if nombre.startswith("Nee"):
        return ("rodilla", lado, servo)
    if nombre.startswith("Link_W"):
        return ("muslo B" if y > -55 else "canilla B", lado, servo)
    if nombre.startswith("Bracket02_W") or (servo and -95 < y < -15):
        return ("muslo A" if y > -55 else "canilla A", lado, servo)
    if nombre.startswith("Pipe"):
        return ("cadera" if y > -30 else "rodilla" if y > -75 else "tobillo", lado, servo)
    return ("cadera" if y > -55 else "tobillo", lado, servo)


def main():
    piezas = json.load(open(os.path.join(DIR, "pose_recta_inventor.json"), encoding="utf-8"))
    grupos = {}
    for p in piezas:
        m = malla(p)
        if m is None:
            print("  sin malla:", p["nombre"])
            continue
        g = grupo(p["nombre"], m)
        if g is None:
            continue
        grupos.setdefault(g, []).append(m)
        print(f"  {p['nombre']:32s} -> {g[0]} {g[1]}{' (servo)' if g[2] else ''}")
    datos = {}
    for (g, lado, servo), ms in grupos.items():
        m = trimesh.util.concatenate(ms)
        pm = pv.wrap(m).triangulate()
        maximo = CARAS_MAX.get(g, 6000)
        if pm.n_cells > maximo:
            pm = pm.decimate(1 - maximo / pm.n_cells)
        clave = f"{g}|{lado}|{'servo' if servo else 'pieza'}"
        datos[clave + "|v"] = np.asarray(pm.points, dtype=np.float32)
        datos[clave + "|f"] = np.asarray(pm.faces.reshape(-1, 4)[:, 1:], dtype=np.int32)
        print(f"{clave:32s} {pm.n_cells:6d} caras")
    np.savez_compressed(os.path.join(DIR, "modelo.npz"), **datos)
    print("->", os.path.join(DIR, "modelo.npz"), f"{os.path.getsize(os.path.join(DIR, 'modelo.npz')) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
