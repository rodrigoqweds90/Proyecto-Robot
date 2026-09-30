"""SEGMENTO: ESTILO "CLASICO CUADRADO" EN CADERA Y PIERNAS (mismo lenguaje que la cabeza y el pecho)
Detalles sutiles sobre las caras que ya existen, en coordenadas locales de cada pieza:
  - panel rebajado 0.8 mm (rectangulo con esquinas R1.5)
  - rejilla: ranuras paralelas con puntas redondas (grabadas 0.8 mm o pasantes)
  - remaches: domitos de 2.4 mm x 0.7 mm en las esquinas del panel
Piezas:
  - Pelvis: panel con 3 ranuras grabadas y 4 remaches en el centro de la cara de adelante (entre los pernos)
  - Bracket04_B / Bracket05_B (pies): panel rebajado en la punta con 4 remaches
La cara exacta se mide con un rayo en el centro del rectangulo.
Salida: piezas_estilo/*.stl (+ .ipt con --ipt); el ensamble y los analisis las toman antes que las demas.
"""
import os
import sys

import manifold3d as mf
import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(BASE, "piezas_estilo")
REMACHE = (1.2, 0.7)            # radio de la esfera, alto del domo (base de ~2.2 mm)
PANEL_FONDO = 0.8
PANEL_RADIO = 1.5

# pieza: (origen, cara (eje, signo), lista de detalles). Rectangulos en los dos ejes libres (orden x, y, z).
DETALLES = {
    # cara de adelante de la pelvis: plana en z 43.2 entre x -13..13 y y -19..-4 (abajo tiene la muesca en V)
    "Pelvis": ("stl", ("z", +1), [
        ("panel", (-13.0, 13.0), (-18.5, -4.5)),
        ("ranuras_grabadas", (-8.5, 8.5), [-15.0, -11.5, -8.0], 2.0),
        ("remaches", [(-10.9, -16.4), (10.9, -16.4), (-10.9, -6.6), (10.9, -6.6)]),
    ]),
    # punta del pie: suela plana en y 6 hasta z -49 (despues empieza el bloque del tobillo); Bracket05 es espejo en x
    "Bracket04_B": ("piezas_m3", ("y", +1), [
        ("panel", (-30.0, 8.5), (-59.5, -50.5)),
        ("remaches", [(-27.4, -57.4), (5.9, -57.4), (-27.4, -52.6), (5.9, -52.6)]),
    ]),
    "Bracket05_B": ("piezas_m3", ("y", +1), [
        ("panel", (-8.5, 30.0), (-59.5, -50.5)),
        ("remaches", [(-5.9, -57.4), (27.4, -57.4), (-5.9, -52.6), (27.4, -52.6)]),
    ]),
}
# (la rodilla Nee_B queda sin remaches: su cara de adelante es la que apoya en la cama al imprimir)
# (el soporte del servo Bracket02_W es un marco en C: la cara grande negra es el propio MG90S, no lleva rejilla)


def a_manifold(m):
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32), tri_verts=np.asarray(m.faces, np.uint32)))


def ejes_libres(eje):
    k = "xyz".index(eje)
    return k, [i for i in range(3) if i != k]


def a_pieza(puntos_uvh, eje):
    """(u, v, h) -> coordenadas de la pieza (u, v en los ejes libres en orden, h en el eje de la cara)."""
    k, (a, b) = ejes_libres(eje)
    P = np.zeros((len(puntos_uvh), 3))
    P[:, a], P[:, b], P[:, k] = puntos_uvh[:, 0], puntos_uvh[:, 1], puntos_uvh[:, 2]
    return P


def solido_2d(poligono, eje, h0, h1):
    """extruye un poligono (shapely, en u-v) entre h0 y h1 sobre el eje de la cara."""
    pts = []
    anillo = np.asarray(poligono.exterior.coords)[:-1]
    for h in (h0, h1):
        pts.append(np.c_[anillo, np.full(len(anillo), h)])
    uvh = np.vstack(pts)
    # convexo (rectangulos redondeados y ranuras lo son): casco
    return mf.Manifold.hull_points(a_pieza(uvh, eje))


def cara(pieza, eje, signo, u, v):
    """altura de la cara (sobre el eje) en el punto (u, v) medida con un rayo desde afuera."""
    k, (a, b) = ejes_libres(eje)
    o = np.zeros(3)
    o[a], o[b] = u, v
    o[k] = (pieza.bounds[1][k] + 20) if signo > 0 else (pieza.bounds[0][k] - 20)
    d = np.zeros(3)
    d[k] = -signo
    locs, _, _ = pieza.ray.intersects_location([o], [d], multiple_hits=False)
    return locs[0][k]


def aplicar(pieza, eje, signo, detalles):
    from shapely.geometry import LineString, box
    m = a_manifold(pieza)
    for det in detalles:
        tipo = det[0]
        if tipo == "panel":
            (u0, u1), (v0, v1) = det[1], det[2]
            h = cara(pieza, eje, signo, (u0 + u1) / 2, (v0 + v1) / 2)
            poly = box(u0, v0, u1, v1).buffer(-PANEL_RADIO).buffer(PANEL_RADIO, 8)
            m = m - solido_2d(poly, eje, h - signo * PANEL_FONDO, h + signo * 5)
        elif tipo in ("ranuras_grabadas", "ranuras_pasantes"):
            (u0, u1), vs, alto = det[1], det[2], det[3]
            for v in vs:
                h = cara(pieza, eje, signo, (u0 + u1) / 2, v)
                poly = LineString([(u0 + alto / 2, v), (u1 - alto / 2, v)]).buffer(alto / 2, 8)
                fondo = h - signo * (PANEL_FONDO if tipo == "ranuras_grabadas" else 12.0)
                m = m - solido_2d(poly, eje, fondo, h + signo * 5)
        elif tipo == "remaches":
            for u, v in det[1]:
                h = cara(pieza, eje, signo, u, v)
                c = np.array([[u, v, h + signo * (REMACHE[1] - REMACHE[0])]])
                m = m + mf.Manifold.sphere(REMACHE[0], 20).translate(tuple(a_pieza(c, eje)[0]))
    r = m.to_mesh()
    return trimesh.Trimesh(r.vert_properties[:, :3], r.tri_verts)


def main():
    os.makedirs(SALIDA, exist_ok=True)
    for nombre, (origen, (eje, signo), detalles) in DETALLES.items():
        pieza = trimesh.load(os.path.join(BASE, origen, nombre + ".stl"), force="mesh")
        nueva = aplicar(pieza, eje, signo, detalles)
        nueva.export(os.path.join(SALIDA, nombre + ".stl"))
        print(f"{nombre}: valido {nueva.is_volume} | {pieza.volume / 1000:.2f} -> {nueva.volume / 1000:.2f} cm3")
    if "--ipt" in sys.argv:
        import pythoncom
        import pywintypes
        from win32com.client import dynamic, gencache
        app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
        gencache.GetModuleForProgID("Inventor.Application")
        app.Documents.CloseAll(False)
        for nombre in DETALLES:
            d = dynamic.Dispatch(app.Documents.Open(os.path.join(SALIDA, nombre + ".stl"), False)._oleobj_)
            ruta = os.path.join(SALIDA, nombre + ".ipt")
            if os.path.exists(ruta):
                os.remove(ruta)
            d.SaveAs(ruta, False)
            d.Close(True)


if __name__ == "__main__":
    main()
