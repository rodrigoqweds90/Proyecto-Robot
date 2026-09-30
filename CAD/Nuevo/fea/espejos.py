"""SEGMENTO: PIEZAS ESPEJO
Bracket05 = espejo X de Bracket04 y Bracket12 = espejo Y de Bracket11 (diferencia 0 mm3 entre originales):
se refleja la pieza aligerada ya verificada. Bracket10 es casi espejo Y de Bracket09 (112 mm3 de diferencia):
se le restan las ventanas de Bracket09 reflejadas y se verifica con el calculo.
"""
import json, os, sys
import numpy as np, trimesh
import fea_pieza as fp, todas


def espejo(m, k, destino):
    M = np.eye(4); M[k, k] = -1
    r = m.copy(); r.apply_transform(M)
    r.apply_translation(destino.bounds.mean(0) - r.bounds.mean(0))
    return r


def guardar(nombre, r):
    res = json.load(open(todas.RESULTADOS, encoding="utf-8"))
    res[nombre] = r
    json.dump(res, open(todas.RESULTADOS, "w", encoding="utf-8"), indent=1)
    print(json.dumps(r), flush=True)


def directo(origen, nombre, k):
    res = json.load(open(todas.RESULTADOS, encoding="utf-8"))
    base = trimesh.load(todas.fuente(nombre), force="mesh")
    orig_a = trimesh.load(todas.fuente(origen), force="mesh")
    a = trimesh.load(os.path.join(todas.SALIDA, origen + ".stl"), force="mesh")
    # misma traslacion que alinea los originales
    M = np.eye(4); M[k, k] = -1
    r = a.copy(); r.apply_transform(M)
    ro = orig_a.copy(); ro.apply_transform(M)
    r.apply_translation(base.bounds.mean(0) - ro.bounds.mean(0))
    r.export(os.path.join(todas.SALIDA, nombre + ".stl"))
    guardar(nombre, dict(res[origen], pieza=nombre, volumen=float(base.volume), quitado_mm3=float(base.volume - r.volume),
                         metodo=f"espejo {'XYZ'[k]} de {origen}", estanco=bool(r.is_watertight)))


def casi(origen, nombre, k):
    base = trimesh.load(todas.fuente(nombre), force="mesh")
    orig_a = trimesh.load(todas.fuente(origen), force="mesh")
    a = trimesh.load(os.path.join(todas.SALIDA, origen + ".stl"), force="mesh")
    # nueva = lo de la base dentro de la aligerada reflejada + lo propio de la base que no tenia el origen
    # (restar directamente el volumen quitado fallaba: "Not all meshes are volumes")
    M = np.eye(4); M[k, k] = -1
    ro = orig_a.copy(); ro.apply_transform(M)
    ra = a.copy(); ra.apply_transform(M)
    T = base.bounds.mean(0) - ro.bounds.mean(0)
    ro.apply_translation(T); ra.apply_translation(T)
    dentro = trimesh.boolean.intersection([base, ra], engine="manifold")
    propio = trimesh.boolean.difference([base, ro], engine="manifold")
    nueva = trimesh.boolean.union([dentro, propio], engine="manifold") if propio.volume > 0.01 else dentro
    lista, servos, horns = todas.interfaces_nx25(nombre)
    casos = todas.casos_nx25(nombre, lista, servos, horns)
    m = fp.mallar(todas.fuente(nombre), 0.8, 0.3)
    its = fp.interfaces_desde_agujeros(m, lista)
    vm, det = fp.resolver_casos(m, its, casos)
    fs_ini = min(20.0 / fp.esfuerzo_util(m, v, n)[1] for v, n in det.values())
    tmp = os.path.join(fp.AQUI, f"tmp_espejo_{os.getpid()}.stl")
    nueva.export(tmp)
    m2 = fp.mallar(tmp, 0.8, 0.3)
    its2 = fp.interfaces_desde_agujeros(m2, lista)
    vm2, det2 = fp.resolver_casos(m2, its2, casos)
    fs = min(20.0 / fp.esfuerzo_util(m2, v, n)[1] for v, n in det2.values())
    ok = len(its2) == len(its) and nueva.is_watertight and fs >= min(3.0, 0.95 * fs_ini)
    print(f"{nombre}: FS original {fs_ini:.2f}, con ventanas de {origen} {fs:.2f}, quita {base.volume - nueva.volume:.0f} mm3 -> {'OK' if ok else 'NO'}", flush=True)
    if ok:
        nueva.export(os.path.join(todas.SALIDA, nombre + ".stl"))
        fp.mapa(nombre + " aligerada", m2, vm2, None, os.path.join(fp.AQUI, f"{nombre}_aligerada_esfuerzo.png"))
        guardar(nombre, dict(pieza=nombre, volumen=float(base.volume), fs_inicial=float(fs_ini), quitado_mm3=float(base.volume - nueva.volume),
                             fs_final=float(fs), metodo=f"ventanas de {origen} en espejo {'XYZ'[k]}"))


if __name__ == "__main__":
    if "directo" in sys.argv:
        directo("Bracket04_B", "Bracket05_B", 0)
        directo("Bracket11_B", "Bracket12_B", 1)
    if "casi" in sys.argv:
        casi("Bracket09_W", "Bracket10_W", 1)
