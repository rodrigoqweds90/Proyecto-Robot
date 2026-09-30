"""SEGMENTO: VERIFICACION DE LOS PIPE_M3 EN CADA UNION
Pone el pipe en su lugar (piezas_m3/pipes_m3.json) y revisa contra las piezas modificadas:
  - no choca con la pieza que gira ni con la que sujeta
  - apoya en la que sujeta (corrido 0.1 mm hacia ella, la toca)
  - la cabeza no toca la que gira con 0.15 mm hacia afuera (juego axial 0.2)
  - juego radial: corrido 0.12 mm de costado no toca la que gira (0.15 por lado)
"""
import collections
import json
import os

import numpy as np
import trimesh

import cables_salida as cs
import m3_pernos as mp

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    nx = cs.nx
    cs.te.ensamble = nx.ensamble
    uniones = mp.emparejar()
    P = [(n, e, t) for n, e, t in nx.ensamble() if not os.path.isabs(n)]
    tipos = {t: trimesh.load(os.path.join(BASE, "piezas_m3", f"Pipe_M3{'_alto' if t == 'alto' else ''}.stl"), force="mesh")
             for t in ("normal", "alto")}
    pipes = json.load(open(os.path.join(BASE, "piezas_m3", "pipes_m3.json"), encoding="utf-8"))
    cache = {}

    def en_mundo(n, inst):
        if n not in cache:
            cache[n] = trimesh.load(os.path.join(BASE, "piezas_m3", n + ".stl"), force="mesh")
        _, e, t = P[inst]
        M = np.eye(4)
        M[:3, :3] = np.column_stack([np.asarray(x, float) for x in e])
        M[:3, 3] = t
        m = cache[n].copy()
        m.apply_transform(M)
        return m

    def choque(a, b):
        return trimesh.boolean.intersection([a, b], engine="manifold").volume

    res = collections.Counter()
    for u, p in zip(uniones, pipes):
        _, e, tt = P[u["agarra"]["inst"]]
        M = np.column_stack([np.asarray(x, float) for x in e])
        o = M @ np.array(p["origen"]) + np.asarray(tt, float)
        d = M @ np.array(p["eje"])
        aux = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
        xl = np.cross(aux, d)
        xl /= np.linalg.norm(xl)
        T = np.eye(4)
        T[:3, :3] = np.column_stack([xl, d, np.cross(xl, d)])
        T[:3, 3] = o
        pm = tipos[p.get("tipo", "normal")].copy()
        pm.apply_transform(T)
        gira = en_mundo(u["gira"]["pieza"], u["gira"]["inst"])
        agarra = en_mundo(u["agarra"]["pieza"], u["agarra"]["inst"])

        def movido(v):
            q = pm.copy()
            q.apply_translation(v)
            return q
        fila = (u["gira"]["pieza"], u["agarra"]["pieza"], round(choque(pm, gira), 2), round(choque(pm, agarra), 2),
                choque(movido(-d * 0.1), agarra) > 0.01, choque(movido(d * 0.15), gira) < 0.01, choque(movido(xl * 0.12), gira) < 0.01)
        res[fila] += 1
    print("n | gira | agarra | choque gira mm3 | choque agarra mm3 | apoya | cabeza libre | juego radial")
    for k, n in sorted(res.items(), key=str):
        print(n, *k)


if __name__ == "__main__":
    main()
