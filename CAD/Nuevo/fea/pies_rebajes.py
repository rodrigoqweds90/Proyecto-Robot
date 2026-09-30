"""SEGMENTO: REBAJES CIEGOS EN LA SUELA DE LOS PIES
La suela (placa de ~6 mm) es casi todo el peso del pie y no admite ventanas pasantes (es la cara que pisa).
Se rebaja por arriba dejando PISO mm de fondo, con nervios en cuadricula, solo donde el esfuerzo es bajo
y lejos de horn/perno. Se verifica con el mismo calculo (factor de seguridad >= 3).
Uso: python pies_rebajes.py Bracket04_B Bracket05_B
"""
import json
import os
import sys
import time
import traceback

import numpy as np
import trimesh

import fea_pieza as fp
import todas

PISO = 2.0              # mm de suela que quedan bajo el rebaje
PARED = 2.0             # mm de pared minima al borde de la suela
UMBRALES = (3.0, 2.0, 1.5)     # de mas a menos material quitado; el primero que cumple gana
MARGEN = 3.0            # mm lejos de horn / perno


def espesor_suela(vox):
    """Altura (en Y) de la placa: primer voxel vacio subiendo desde el piso, mediana de las columnas."""
    dentro = vox.dentro
    llenas = dentro[:, 0, :]
    alturas = np.argmin(dentro, axis=1)[llenas]
    return float(np.median(alturas)) * vox.paso


def rebajes(vox, vm_ok, y_top):
    """Mascara 2D (X, Z) donde se puede rebajar la capa y in [PISO, y_top] con la tapa abierta arriba."""
    y = vox.ejes[1]
    capa = (y > PISO) & (y < y_top)
    k_arriba = int(np.searchsorted(y, y_top + vox.paso / 2))
    mask = (vox.dentro[:, capa, :] & vm_ok[:, capa, :]).all(axis=1)
    if k_arriba < len(y):
        mask &= ~vox.dentro[:, k_arriba, :]
    return mask, [vox.ejes[0], vox.ejes[2]]


def cortar(tri, poligonos, y_top):
    herramientas = []
    for p in poligonos:
        ex = trimesh.creation.extrude_polygon(p, y_top + 1.0 - PISO)
        M = np.zeros((4, 4))
        M[0, 0] = 1          # u -> X
        M[2, 1] = 1          # v -> Z
        M[1, 2] = 1          # altura -> Y
        M[1, 3] = PISO
        M[3, 3] = 1
        ex.apply_transform(M)
        if ex.is_volume:
            herramientas.append(ex)
    if not herramientas:
        return tri
    return trimesh.boolean.difference([tri, trimesh.boolean.union(herramientas, engine="manifold")], engine="manifold")


def calcular(stl, lista, casos, h):
    m = fp.mallar(stl, h, 0.3)
    its = fp.interfaces_desde_agujeros(m, lista)
    vm, det = fp.resolver_casos(m, its, casos)
    fs = min(20.0 / fp.esfuerzo_util(m, v, n)[1] for v, n in det.values())
    return m, its, vm, fs


def pie(nombre):
    stl = todas.fuente(nombre)
    tri = trimesh.load(stl, force="mesh")
    lista, servos, horns = todas.interfaces_nx25(nombre)
    casos = todas.casos_nx25(nombre, lista, servos, horns)
    h = 1.0
    m, its, vm, fs_ini = calcular(stl, lista, casos, h)
    fp.mapa(nombre, m, vm, None, os.path.join(fp.AQUI, f"{nombre}_esfuerzo.png"))
    # distancia solo a horn/perno: la suela entera esta "fija" y no debe bloquear el rebaje
    nodos = np.unique(np.concatenate([it["nodos"] for it in its if it["nombre"] != "suela"]))
    vox = fp.Voxeles(tri, m, vm, nodos)
    y_top = espesor_suela(vox)
    print(f"{nombre}: suela {y_top:.1f} mm, FS inicial {fs_ini:.2f}", flush=True)
    res = dict(pieza=nombre, volumen=float(tri.volume), fs_inicial=float(fs_ini), quitado_mm3=0.0, fs_final=float(fs_ini),
               ventanas=0, metodo="rebajes suela")
    for umbral in UMBRALES:
        vm_ok = (vox.vm < umbral) & (vox.dist > MARGEN)
        mask, coords = rebajes(vox, vm_ok, y_top)
        pols = fp.ventanas_en_mascara(mask, coords)
        # pared minima al borde: encoger lo que falte sobre el BORDE que ya deja ventanas_en_mascara
        pols = [q for p in pols for q in _partes(p.buffer(-(PARED - fp.BORDE), join_style=2)) if q.area >= fp.VENTANA_AREA_MIN]
        if not pols:
            print(f"  umbral {umbral}: sin rebajes", flush=True)
            continue
        nueva = cortar(tri, pols, y_top)
        if not nueva.is_watertight or nueva.volume >= tri.volume - 1:
            print(f"  umbral {umbral}: corte invalido", flush=True)
            continue
        tmp = os.path.join(fp.AQUI, f"tmp_pie_{os.getpid()}.stl")
        nueva.export(tmp)
        m2, its2, vm2, fs = calcular(tmp, lista, casos, h)
        quita = tri.volume - nueva.volume
        print(f"  umbral {umbral}: {len(pols)} rebajes, -{quita:.0f} mm3 ({100 * quita / tri.volume:.1f}%), FS {fs:.2f}", flush=True)
        if fs >= min(3.0, 0.95 * fs_ini) and quita > res["quitado_mm3"]:
            res.update(quitado_mm3=float(quita), fs_final=float(fs), ventanas=len(pols), umbral=umbral)
            nueva.export(os.path.join(todas.SALIDA, f"{nombre}.stl"))
            fp.mapa(nombre + " aligerada", m2, vm2, None, os.path.join(fp.AQUI, f"{nombre}_aligerada_esfuerzo.png"))
            break
    return res


def _partes(g):
    if g.is_empty:
        return []
    return [g] if g.geom_type == "Polygon" else list(g.geoms)


def main(nombres):
    for nombre in nombres:
        t0 = time.time()
        try:
            r = pie(nombre)
        except Exception as e:
            r = dict(pieza=nombre, error=str(e), traza=traceback.format_exc()[-800:])
        r["segundos"] = round(time.time() - t0)
        resultados = json.load(open(todas.RESULTADOS, encoding="utf-8")) if os.path.exists(todas.RESULTADOS) else {}
        resultados[nombre] = r
        json.dump(resultados, open(todas.RESULTADOS, "w", encoding="utf-8"), indent=1)
        print(json.dumps({k: v for k, v in r.items() if k != "traza"}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
