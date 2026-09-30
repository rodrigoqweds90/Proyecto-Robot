"""SEGMENTO: VERIFICACION DE LOS SOPORTES DE ARMADO (los moldes)
Con la pierna recta (servos en 90) revisa, para cada molde:
  1. entra: no choca con la pierna y el juego real que queda
  2. sujeta: cuanto se puede desviar cada articulacion antes de que el molde la frene (ahi esta la precision)
  3. deja trabajar: desde el horn de cada servo, hacia arriba (o hacia atras en el de parado), no hay molde
     en el disco de 13 mm donde van el tornillo central y los del horn
  4. soporte de parado: juego de los pies dentro del cerco y distancia de la pelvis a la pared
Uso: ROBOT_VARIANTE=B python verificar_soportes.py
"""
import os
import sys

import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import barrido_movimiento as bm  # noqa: E402
import poses_marcha as pm  # noqa: E402
import soportes_armado as sa  # noqa: E402

DESVIOS = (0.5, 1.0, 2.0, 3.0, 5.0, 8.0)        # grados a probar en cada sentido
CHOQUE = 1.0                                    # mm3 para considerar que el molde la frena
RADIO_HORN = 13.0                               # disco que tiene que quedar libre sobre cada horn
MUESTRAS = 400


def moldes():
    return {n: trimesh.load(os.path.join(sa.SALIDA, n + ".stl"), force="mesh")
            for n in ("Soporte_pierna_izq", "Soporte_pierna_der", "Soporte_parado")}


def volumen(a, b):
    if not bm.cajas_se_tocan(a.bounds, b.bounds):
        return 0.0
    return (bm.a_manifold(a) ^ bm.a_manifold(b)).volume()


def juego(molde, pierna, sobre=None):
    """distancia de los puntos de la pieza a la superficie del molde (sobre: solo por encima de esa altura y)."""
    pts = pierna.sample(4000)
    if sobre is not None:
        pts = pts[pts[:, 1] > sobre]
    d = trimesh.proximity.closest_point(molde, pts)[1]
    cerca = d[d < 3.0]
    return (cerca.min(), np.median(cerca)) if len(cerca) else (np.nan, np.nan)


def sujeta(info, grupos, n, piezas, idx, molde, claves):
    """desvio minimo (en grados) de cada articulacion con el que el molde ya la frena."""
    salida = {}
    for a in info:
        if not any(k in a["nombre"] for k in claves):
            continue
        tope = {}
        for signo in (1, -1):
            tope[signo] = None
            for d in DESVIOS:
                ang = {b["nombre"]: 0.0 for b in info if any(k in b["nombre"] for k in claves)}
                ang[a["nombre"]] = signo * d
                T = pm.pose(info, grupos, ang, n)
                v = 0.0
                for i in idx:
                    q = piezas[i].copy()
                    q.apply_transform(T[i])
                    v += volumen(molde, q)
                    if v > CHOQUE:
                        break
                if v > CHOQUE:
                    tope[signo] = d
                    break
        salida[a["nombre"]] = (tope[-1], tope[1])
    return salida


def horns(T, grupos, info, molde, direccion, claves):
    """desde el centro del horn en la pose recta, hacia 'direccion', que no haya molde en un disco de RADIO_HORN."""
    salida = []
    for a in info:
        if not any(k in a["nombre"] for k in claves):
            continue
        art = a["art"]
        c = np.asarray(art["u"]["c"], float)
        eje = np.asarray(art["u"]["d"], float)
        i = next(iter(bm.transformaciones(art, grupos, 1.0)))       # pieza que gira con ese horn
        c = T[i][:3, :3] @ c + T[i][:3, 3]                          # el molde esta en la pose recta
        eje = T[i][:3, :3] @ eje
        eje = eje / np.linalg.norm(eje)
        d = np.asarray(direccion, float)
        if eje @ d < 0:
            eje = -eje
        u = np.cross(eje, [0, 0, 1.0])
        u = u / np.linalg.norm(u) if np.linalg.norm(u) > 0.1 else np.array([1.0, 0, 0])
        w = np.cross(eje, u)
        ang = np.random.default_rng(0).uniform(0, 2 * np.pi, MUESTRAS)
        rad = RADIO_HORN * np.sqrt(np.random.default_rng(1).uniform(0, 1, MUESTRAS))
        pts = c + np.outer(rad * np.cos(ang), u) + np.outer(rad * np.sin(ang), w) + eje * 0.5
        hits = molde.ray.intersects_any(pts, np.tile(eje, (MUESTRAS, 1)))
        salida.append((a["nombre"], 100.0 * hits.mean()))
    return salida


def main():
    P, rectas, T, piernas, pelvis = sa.pose_recta()
    _, piezas = bm.cargar()
    host, giros, g, raiz, grupos, aristas = bm.estructura(P)
    arts = bm.articulaciones(P, g, raiz, aristas)
    info = pm.calibrar(P, piezas, arts, grupos)
    n = len(piezas)
    M = moldes()
    for lado, sufijo in ((1, "izq"), (-1, "der")):
        molde = M[f"Soporte_pierna_{sufijo}"]
        idx = piernas[lado]
        pierna = trimesh.util.concatenate([rectas[i] for i in idx])
        print(f"\n== Soporte_pierna_{sufijo}")
        print(f"  choque con la pierna recta: {sum(volumen(molde, rectas[i]) for i in idx):.2f} mm3")
        mn, med = juego(molde, pierna)
        print(f"  juego contra el molde: minimo {mn:.2f} mm, tipico {med:.2f} mm")
        claves = (f"muslo (cadera adelante-atras) {sufijo}", f"rodilla {sufijo}",
                  f"cadera (lateral) {sufijo}", f"tobillo (lateral) {sufijo}")
        for nombre, (neg, pos) in sujeta(info, grupos, n, piezas, idx, molde, claves).items():
            f = lambda v: f"{v:.1f} grados" if v else f"mas de {DESVIOS[-1]:.0f} grados (no la frena)"
            print(f"  {nombre:34s} topa a {f(neg):>28s} de un lado y {f(pos):>28s} del otro")
        for nombre, tapado in horns(T, grupos, info, molde, [-lado, 0, 0], claves[:2]):
            print(f"  acceso al horn de {nombre:30s}: {tapado:.0f}% del disco tapado por el molde")
    molde = M["Soporte_parado"]
    idx = [i for l in piernas for i in piernas[l]]
    print("\n== Soporte_parado")
    print(f"  choque con el robot: {sum(volumen(molde, rectas[i]) for i in idx + [pelvis]):.2f} mm3")
    pies = [i for i in idx if P[i]["nombre"] in ("Bracket04_B", "Bracket05_B")]
    y_suelo = min(rectas[i].bounds[0][1] for i in pies)
    for i in pies:
        mn, med = juego(molde, rectas[i], sobre=y_suelo + 0.8)
        print(f"  {P[i]['nombre']} dentro del cerco: juego lateral minimo {mn:.2f} mm")
    mn, _ = juego(molde, rectas[pelvis])
    print(f"  pelvis sobre la pared: {mn:.2f} mm (baja eso y apoya)")
    claves = tuple(f"{r} {s}" for r in ("cadera (lateral)", "tobillo (lateral)") for s in ("izq", "der"))
    for nombre, tapado in horns(T, grupos, info, molde, [0, 0, -1.0], claves):
        print(f"  acceso al horn de {nombre:30s}: {tapado:.0f}% del disco tapado por el molde")
    claves_todas = tuple(f"{r} {s}" for r in ("muslo (cadera adelante-atras)", "rodilla", "cadera (lateral)", "tobillo (lateral)") for s in ("izq", "der"))
    for nombre, (neg, pos) in sujeta(info, grupos, n, piezas, idx + [pelvis], molde, claves_todas).items():
        f = lambda v: f"{v:.1f} grados" if v else f"mas de {DESVIOS[-1]:.0f} grados (no la frena)"
        print(f"  {nombre:34s} topa a {f(neg):>28s} de un lado y {f(pos):>28s} del otro")


if __name__ == "__main__":
    main()
