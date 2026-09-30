"""SEGMENTO: VERIFICACION ANTES DE IMPRIMIR (modelo B)
1. Lista de piezas impresas del ensamble B, con el STL que usa el ensamble (misma prioridad que
   barrido_movimiento.malla_local) y la cantidad.
2. Malla de cada una: cerrada, un solo cuerpo, volumen, masa aproximada, entra en la cama de la A1 (256 mm).
3. Al dia: el STL es mas nuevo que los scripts y piezas de los que sale.
4. Material agregado por el estilo (remaches, bordes): la parte nueva de cada pieza (actual - version anterior)
   no tiene que tocar ninguna otra pieza en la pose de parado. El barrido de movimiento toma la pose de parado
   como referencia, asi que un roce que ya este ahi no lo ve.
Uso: ROBOT_VARIANTE=B python verificar_impresion.py
"""
import collections
import glob
import os
import sys

import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import barrido_movimiento as bm  # noqa: E402
import torso_estudio as te  # noqa: E402

CAMA = 256.0
DENSIDAD = 1.24 * 0.75          # g/cm3, PLA con paredes y relleno (la misma que torso_estudio)
IMPRESAS = ("Bracket", "Link_W", "Nee_B", "Pelvis", "Spacer01", "Pipe_M3", "Torso_", "Cabeza")
# de que depende cada salida (patron de archivo -> scripts y piezas de entrada)
DEPENDE = {
    "stl/Torso_cuerpo_B.stl": ["torso.py"],
    "stl/Torso_pecho.stl": ["carcasa.py", "torso.py"],
    "stl/Cabeza_*.stl": ["cabeza.py"],
    "stl/Pelvis.stl": ["pelvis.py"],
    "piezas_m3/[BLNP]*.stl": ["m3_pernos.py", "horns_exactos.py"],     # (Spacer01 salio antes, no lo generan)
    "piezas_estilo/*.stl": ["estilo_clasico.py", "stl/Pelvis.stl", "piezas_m3/Bracket04_B.stl"],
    "piezas_rediseno/*.stl": ["mano.py", "estilo_clasico.py", "piezas_m3/Bracket11_B.stl"],
    "piezas_soportes/*.stl": ["soportes_armado.py", "piezas_estilo/*.stl", "piezas_m3/*.stl", "stl/Pelvis.stl"],
}
# version anterior al estilo de cada pieza que lo recibio (para aislar lo agregado)
ANTES = {
    "Pelvis": "stl/Pelvis.stl", "Bracket04_B": "piezas_m3/Bracket04_B.stl", "Bracket05_B": "piezas_m3/Bracket05_B.stl",
    "Bracket11_B": "OldVersions/Bracket11_B_sin_estilo.stl",
    "Bracket12_B": "OldVersions/Bracket12_B_sin_estilo.stl",
}


def fuente(ruta):
    """el STL que carga barrido_movimiento.malla_local para esa ruta del ensamble."""
    base = os.path.splitext(os.path.basename(ruta))[0]
    carpeta = os.path.dirname(ruta)
    if os.path.isabs(ruta):
        cand = [os.path.join(BASE, "piezas_estilo", base + ".stl"), os.path.join(carpeta, base + ".stl"),
                os.path.join(carpeta, "stl", base + ".stl"), os.path.join(BASE, "stl", base + ".stl")]
    else:
        cand = [os.path.join(BASE, d, base + ".stl") for d in ("piezas_estilo", "piezas_rediseno", "piezas_m3")] + \
               [os.path.join(BASE, "piezas_canales", base + "_brida.stl"), os.path.join(te.nx.BASE, "stl", base + ".stl")]
    return next(c for c in cand if os.path.exists(c))


def lista_impresas():
    P = bm.un.piezas()
    rutas = [n for n, _, _ in te.ensamble()]
    cuenta, origen = collections.Counter(), {}
    for p, ruta in zip(P, rutas):
        if p["nombre"].startswith(IMPRESAS):
            cuenta[p["nombre"]] += 1
            origen[p["nombre"]] = fuente(ruta)
    return P, rutas, cuenta, origen


def revisar_mallas(cuenta, origen):
    print(f"{'pieza':22s} {'cant':>4s} {'fuente':34s} {'cerrada':>7s} {'cuerpos':>7s} {'cm3':>6s} {'g c/u':>6s} {'caja mm':>20s}")
    total, malas = 0.0, []
    for nombre in sorted(cuenta):
        m = trimesh.load(origen[nombre], force="mesh")
        cuerpos = len(m.split(only_watertight=False))
        g = m.volume / 1000 * DENSIDAD
        total += g * cuenta[nombre]
        ok = m.is_watertight and m.is_winding_consistent and cuerpos == 1 and max(m.extents) < CAMA
        if not ok:
            malas.append(nombre)
        caja = "x".join(f"{e:.0f}" for e in sorted(m.extents, reverse=True))
        print(f"{nombre:22s} {cuenta[nombre]:4d} {os.path.relpath(origen[nombre], BASE):34s} {str(m.is_watertight):>7s} "
              f"{cuerpos:7d} {m.volume / 1000:6.2f} {g:6.1f} {caja:>20s}")
    print(f"plastico del robot: {total:.0f} g (sin soportes de armado) | mallas con problemas: {malas or 'ninguna'}")
    return malas


def revisar_fechas():
    viejas = []
    for patron, deps in DEPENDE.items():
        salidas = glob.glob(os.path.join(BASE, patron))
        entradas = [f for d in deps for f in glob.glob(os.path.join(BASE, d))]
        for s in salidas:
            mas_nuevas = [os.path.relpath(e, BASE) for e in entradas if e != s and os.path.getmtime(e) > os.path.getmtime(s) + 1]
            if mas_nuevas:
                viejas.append((os.path.relpath(s, BASE), mas_nuevas))
    for s, e in viejas:
        print(f"  VIEJA: {s} es anterior a {', '.join(e)}")
    print(f"salidas al dia: {'si' if not viejas else f'no ({len(viejas)})'}")
    return viejas


def revisar_agregado(P, rutas):
    """lo que el estilo le agrego a cada pieza no toca a ninguna otra en la pose de parado."""
    _, piezas = bm.cargar()
    mallas = [bm.a_manifold(m) for m in piezas]
    cajas = [m.bounds for m in piezas]
    problemas = []
    for i, p in enumerate(P):
        if p["nombre"] not in ANTES:
            continue
        actual = trimesh.load(fuente(rutas[i]), force="mesh")
        antes = trimesh.load(os.path.join(BASE, ANTES[p["nombre"]]), force="mesh")
        agregado = bm.a_manifold(actual) - bm.a_manifold(antes)
        M = np.eye(4)
        M[:3, :3], M[:3, 3] = p["M"], p["t"]
        agregado = agregado.transform(M[:3, :4])
        if agregado.volume() < 0.01:
            continue
        caja = np.array(agregado.bounding_box()).reshape(2, 3)
        for j, m in enumerate(mallas):
            if j == i or not bm.cajas_se_tocan(caja, cajas[j]):
                continue
            v = (agregado ^ m).volume()
            if v > 0.05:
                problemas.append((p["nombre"], P[j]["nombre"], round(v, 2)))
        print(f"  {p['nombre']:12s} agregado {agregado.volume():6.1f} mm3 en {caja[0].round(0).tolist()}..{caja[1].round(0).tolist()}")
    for a, b, v in problemas:
        print(f"  TOCA: lo agregado a {a} entra {v} mm3 en {b}")
    print(f"material agregado sin roces: {'si' if not problemas else 'no'}")
    return problemas


def main():
    P, rutas, cuenta, origen = lista_impresas()
    print("== 1-2. piezas y mallas")
    revisar_mallas(cuenta, origen)
    print("\n== 3. fechas")
    revisar_fechas()
    print("\n== 4. material agregado por el estilo, pose de parado")
    revisar_agregado(P, rutas)


if __name__ == "__main__":
    main()
