"""SEGMENTO: ESPACIO LIBRE PARA REDISENAR EL ANTEBRAZO (Bracket11_B, en sus coordenadas locales)
Lo que ocupa el brazo de arriba (Bracket09_W, servo del codo, pernos) mientras el codo gira en su rango libre,
visto desde el antebrazo: el antebrazo nuevo tiene que quedar afuera de ese volumen (mas un margen).
Tambien las piezas vecinas quietas (cadera, torso) en la pose de parado.
Salida: piezas_boceto/espacio_codo.stl, espacio_vecinos.stl y cortes en consola.
Uso: ROBOT_VARIANTE=B python mano_espacio.py
"""
import os
import sys

import manifold3d as mf
import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import barrido_movimiento as bm  # noqa: E402

SALIDA = os.path.join(BASE, "piezas_boceto")
RANGO_CODO = (-55.0, 90.0)      # grados desde parado (servo 35 a 180, el rango libre que tiene hoy)
PASO = 3.0
RADIO_VECINOS = 70.0            # piezas quietas a menos de esto del eje del codo


def main():
    P, piezas = bm.cargar()
    host, giros, g, raiz, grupos, aristas = bm.estructura(P)
    arts = bm.articulaciones(P, g, raiz, aristas)
    mano = next(i for i, p in enumerate(P) if p["nombre"] == "Bracket11_B")
    codo = next(a for a in arts if a["tipo"] == "simple" and any(mano in grupos[x] for x in a["mueve"]) and
                bm.nombre_articulacion(P, g, a).startswith("codo"))
    mueve = {i for x in codo["mueve"] for i in grupos[x]}
    c, d = np.asarray(codo["u"]["c"], float), np.asarray(codo["u"]["d"], float)
    M, t = np.asarray(P[mano]["M"], float), np.asarray(P[mano]["t"], float)
    a_local = np.eye(4)
    a_local[:3, :3], a_local[:3, 3] = M.T, -M.T @ t
    print("se mueven con el codo:", sorted({P[i]["nombre"] for i in mueve}))
    cerca = [i for i in range(len(P)) if i not in mueve and
             np.linalg.norm(np.clip(c, *piezas[i].bounds) - c) < RADIO_VECINOS]
    arriba = [i for i in cerca if np.linalg.norm(np.clip(c, *piezas[i].bounds) - c) < 30.0]
    print("brazo de arriba (barre):", sorted({P[i]["nombre"] for i in arriba}))
    print("vecinos quietos:", sorted({P[i]["nombre"] for i in cerca if i not in arriba}))
    # barrido del brazo de arriba visto desde el antebrazo: gira -theta
    barrido = None
    base = [bm.a_manifold(piezas[i]) for i in arriba]
    for th in np.arange(RANGO_CODO[0], RANGO_CODO[1] + 1e-6, PASO):
        T = a_local @ bm.rotacion(d, -th, c)
        for m in base:
            q = m.transform(T[:3, :4])
            barrido = q if barrido is None else barrido + q
    vecinos = None
    for i in cerca:
        if i in arriba:
            continue
        q = bm.a_manifold(piezas[i]).transform(a_local[:3, :4])
        vecinos = q if vecinos is None else vecinos + q
    for nombre, m in (("espacio_codo", barrido), ("espacio_vecinos", vecinos)):
        r = m.to_mesh()
        tm = trimesh.Trimesh(r.vert_properties[:, :3], r.tri_verts)
        tm.export(os.path.join(SALIDA, nombre + ".stl"))
        print(f"{nombre}: caja local {np.round(tm.bounds, 1).tolist()}")
    eje_local = M.T @ (c - t)
    print("eje del codo en local:", np.round(eje_local, 1), "direccion", np.round(M.T @ d, 2))


if __name__ == "__main__":
    main()
