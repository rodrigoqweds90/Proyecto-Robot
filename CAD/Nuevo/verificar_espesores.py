"""SEGMENTO: ESPESORES DE PARED DE LAS PIEZAS A IMPRIMIR
Mide el espesor real del material en toda la pieza: la rellena de cubos de 0.3 mm y, con la transformada de
distancia, saca el espesor local (2 x la distancia al borde). Reporta cuanto material queda por debajo del
minimo sano para PLA en la A1 (3 perimetros de 0.42 = 1.26 mm) y donde esta lo mas fino.
Uso: python verificar_espesores.py [pieza ...]
"""
import glob
import os
import sys

import numpy as np
import trimesh
from scipy import ndimage

BASE = os.path.dirname(os.path.abspath(__file__))
PAQUETE = os.path.join(BASE, "imprimir_B")
PASO = 0.3                  # mm por cubo
MINIMO = 1.26               # 3 perimetros de 0.42 mm
FINO = 0.9                  # por debajo de esto ya es frágil (2 perimetros)


def espesores(ruta):
    m = trimesh.load(ruta, force="mesh")
    vox = m.voxelized(pitch=PASO).fill()
    dentro = np.asarray(vox.matrix)
    if not dentro.any():
        return None
    d = ndimage.distance_transform_edt(dentro) * PASO      # distancia al borde de cada cubo interior
    espesor = 2 * d
    # el espesor de una zona es el de su eje central: para cada cubo, el maximo de su entorno
    local = ndimage.maximum_filter(espesor, size=5)
    local = np.where(dentro, local, np.nan)
    vol_cubo = PASO ** 3
    total = dentro.sum() * vol_cubo
    bajo_min = np.nansum(local < MINIMO) * vol_cubo
    bajo_fino = np.nansum(local < FINO) * vol_cubo
    idx = np.argwhere(dentro & (local < FINO))
    peor = None
    if len(idx):
        vals = local[tuple(idx.T)]
        p = idx[np.argmin(vals)]
        peor = (float(vals.min()), np.round(vox.indices_to_points(p.reshape(1, 3))[0] + m.bounds[0] * 0, 1))
    return total, bajo_min, bajo_fino, peor, m


def main(nombres):
    archivos = sorted(glob.glob(os.path.join(PAQUETE, "*.stl")))
    if nombres:
        archivos = [a for a in archivos if os.path.splitext(os.path.basename(a))[0] in nombres]
    print(f"{'pieza':22s} {'cm3':>6s} {'<1.26 mm':>10s} {'<0.9 mm':>9s}  lo mas fino")
    avisos = []
    for ruta in archivos:
        nombre = os.path.splitext(os.path.basename(ruta))[0]
        r = espesores(ruta)
        if r is None:
            print(f"{nombre:22s}  no se pudo medir")
            continue
        total, bajo_min, bajo_fino, peor, m = r
        txt = "todo por encima de 0.9 mm" if peor is None else f"{peor[0]:.2f} mm en {peor[1].tolist()}"
        print(f"{nombre:22s} {total / 1000:6.2f} {100 * bajo_min / total:9.1f}% {100 * bajo_fino / total:8.1f}%  {txt}")
        if bajo_fino / total > 0.02:
            avisos.append((nombre, 100 * bajo_fino / total, peor))
    print()
    if avisos:
        for nombre, pct, peor in avisos:
            print(f"OJO: {nombre} tiene {pct:.1f}% de material por debajo de 0.9 mm (lo mas fino: {peor[0]:.2f} mm)")
    else:
        print("ninguna pieza tiene una parte significativa por debajo de 0.9 mm")


if __name__ == "__main__":
    main(set(sys.argv[1:]))
