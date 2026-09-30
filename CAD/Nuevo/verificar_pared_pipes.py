"""SEGMENTO: PARED QUE QUEDA ALREDEDOR DE CADA AGUJERO DEL PIPE
En la pieza que gira, el pipe v4 pide un agujero de 7.9 mm (antes 6.3, y el NX25 original 5.5). Este script
mide, en cada union, cuanto material queda entre ese agujero y el borde de la oreja: rayos desde el eje hacia
afuera, a varias alturas, buscando el primer material y la salida.
Uso: ROBOT_VARIANTE=B python verificar_pared_pipes.py
"""
import os
import sys

import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import barrido_movimiento as bm  # noqa: E402
import m3_pernos as mp  # noqa: E402

DIRECCIONES = 72
ALTURAS = np.arange(-18.0, 18.01, 0.5)
R_PIPE = mp.GIRA_PIPE / 2                   # 3.95
R_REBAJE = mp.REBAJE_DIAM / 2 + 0.15        # 4.65
ANTES = {"NX25 original": 5.5 / 2, "pipe v3": 6.3 / 2}      # agujeros de la pieza que gira en versiones previas


def marco(eje):
    u = np.cross(eje, [0, 0, 1.0])
    if np.linalg.norm(u) < 0.1:
        u = np.cross(eje, [1.0, 0, 0])
    u /= np.linalg.norm(u)
    return u, np.cross(eje, u)


def pared(malla, centro, eje, radios, tol=0.35):
    """para cada radio de agujero buscado, el mínimo de (radio de salida - radio del agujero) en toda su altura."""
    eje = np.asarray(eje, float) / np.linalg.norm(eje)
    u, w = marco(eje)
    ang = np.linspace(0, 2 * np.pi, DIRECCIONES, endpoint=False)
    dirs = np.cos(ang)[:, None] * u + np.sin(ang)[:, None] * w
    peor = {r: None for r in radios}
    for h in ALTURAS:
        o = np.asarray(centro, float) + eje * h
        origenes = np.tile(o, (DIRECCIONES, 1))
        locs, rayos, _ = malla.ray.intersects_location(origenes, dirs, multiple_hits=True)
        if not len(rayos):
            continue
        d = np.linalg.norm(locs - o, axis=1)
        for j in range(DIRECCIONES):
            dj = np.sort(d[rayos == j])
            dj = dj[dj > 0.5]
            if len(dj) < 2:
                continue
            for r in radios:
                if abs(dj[0] - r) > tol:            # ese rayo no sale de ese agujero
                    continue
                e = dj[1] - dj[0]
                if peor[r] is None or e < peor[r][0]:
                    peor[r] = (e, h)
    return peor


def main():
    P, piezas = bm.cargar()
    host, giros, g, raiz, grupos, aristas = bm.estructura(P)
    filas = []
    for u in giros:
        if u["tipo"] != "perno":
            continue
        c, d = np.asarray(u["c"], float), np.asarray(u["d"], float)
        for lado in ("a", "b"):
            i = u[lado]
            r = pared(piezas[i], c, d, (R_PIPE, R_REBAJE))
            if r[R_PIPE] is None and r[R_REBAJE] is None:
                continue
            cuerpo = r[R_PIPE][0] if r[R_PIPE] else np.nan
            rebaje = r[R_REBAJE][0] if r[R_REBAJE] else np.nan
            filas.append((np.nanmin([cuerpo, rebaje]), P[i]["nombre"], np.round(c, 1), cuerpo, rebaje))
    filas.sort(key=lambda f: f[0])
    print(f"{'pieza':14s} {'en el agujero':>13s} {'en el rebaje':>13s} {'con v3 (6.3)':>13s}   union")
    for _, nombre, c, cuerpo, rebaje in filas:
        print(f"{nombre:14s} {cuerpo:10.2f} mm {rebaje:10.2f} mm {cuerpo + (mp.GIRA_PIPE - 6.3) / 2:10.2f} mm   en {c.tolist()}")
    if filas:
        print(f"\npeor pared: {filas[0][0]:.2f} mm en {filas[0][1]} | con el pipe v3 seria {filas[0][0] + 0.8:.2f} mm")
        print(f"uniones medidas: {len(filas)}")


if __name__ == "__main__":
    main()
