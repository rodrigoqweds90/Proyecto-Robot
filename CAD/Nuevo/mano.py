"""SEGMENTO: MANO NUEVA (pinza simple, corta, estilo clasico cuadrado: panel con remaches y puntas redondeadas)
La mano del NX25 (Bracket11/12) baja 61 mm desde el eje del codo con una caja hueca que termina en punta.
Se conservan exactas las orejas del codo (rebaje del horn, perno M3 y lo que ya tenian de piezas_m3) y
todo lo de abajo se cambia por: palma que cierra la caja + pinza en C de dos dedos.
Coordenadas locales de Bracket11: eje del codo en (24.1, 6, z), X hacia la muneca es -X, Z a lo ancho.
Bracket12 es el espejo exacto en Y de Bracket11.
Salida: piezas_rediseno/Bracket11_B.stl y Bracket12_B.stl (+ .ipt si Inventor esta abierto) y para_imprimir.
"""
import os
import sys

import numpy as np
import trimesh
from shapely.geometry import box
from shapely.ops import unary_union

BASE = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(BASE, "piezas_rediseno")
ORIGEN = os.path.join(BASE, "piezas_m3")

EJE_CODO = np.array([24.1, 6.0])     # (x, y) local
X_CORTE = 1.0                        # se conserva la pieza original por encima de esta x
PALMA = (-1.5, 1.5)                  # x de la placa que cierra la caja (22.6 mm bajo el eje: el servo gira libre)
# pinza vista de costado (plano x-y): dos dedos que bajan de la palma y se cierran en punta
DEDO_LARGO = 16.0                    # bajo la palma
DEDO_GRUESO = 4.0
PUNTA_ALTO = 4.0
ABERTURA = 7.0                       # luz entre las puntas
PINZA_ANCHO = 16.0                   # a lo ancho (z)
REDONDEO = 1.8                       # puntas de los dedos redondeadas (estilo clasico cuadrado; el dedo mide 4)
# estilo clasico cuadrado (estilo_clasico.py): panel rebajado con 4 remaches en la cara de afuera del antebrazo
# (z -21.1, plana entre la muneca y el codo; se evita la salida de cable en y 3.5-8.5)
ESTILO_MANO = [("panel", (0.5, 10.5), (9.5, 20.0)),
               ("remaches", [(2.4, 11.4), (8.6, 11.4), (2.4, 18.1), (8.6, 18.1)])]


def contorno_caja(malla):
    """Contorno exterior de la caja justo bajo las orejas (plano y-z), para la palma."""
    s = malla.section(plane_origin=[X_CORTE + 1.5, 0, 0], plane_normal=[1, 0, 0])
    T = np.array([[0, 0, 1, 0], [0, 1, 0, 0], [1, 0, 0, -(X_CORTE + 1.5)], [0, 0, 0, 1]])
    plano, _ = s.to_planar(to_2D=T)
    return unary_union([p.convex_hull for p in plano.polygons_full]).convex_hull, np.linalg.inv(T)


def extruir(poligono, desde, hasta, a_mundo):
    """Extruye un poligono del plano (u, v) entre dos alturas y lo lleva a local con a_mundo (4x4)."""
    m = trimesh.creation.extrude_polygon(poligono, hasta - desde)
    m.apply_translation([0, 0, desde])
    m.apply_transform(a_mundo)
    return m


def mano_nueva():
    original = trimesh.load(os.path.join(ORIGEN, "Bracket11_B.stl"), force="mesh")
    lo, hi = original.bounds
    arriba = trimesh.boolean.intersection([original, trimesh.creation.box(
        bounds=[[X_CORTE, lo[1] - 1, lo[2] - 1], [hi[0] + 1, hi[1] + 1, hi[2] + 1]])], engine="manifold")

    # palma: contorno de la caja (u = z, v = y), extruida a lo largo de x
    caja, _ = contorno_caja(original)
    a_x = np.array([[0, 0, 1, 0], [0, 1, 0, 0], [1, 0, 0, 0], [0, 0, 0, 1]], float)   # (u, v, w) -> (x=w, y=v, z=u)
    palma = extruir(caja, PALMA[0], PALMA[1] + (X_CORTE - PALMA[1]) + 1.0, a_x)

    # pinza: perfil en (u = y, v = x), extruido a lo ancho en z
    y0, y1 = caja.bounds[1], caja.bounds[3]
    yc = (y0 + y1) / 2
    x_arriba, x_abajo = PALMA[0] + 0.5, PALMA[0] - DEDO_LARGO
    piezas = [box(y0, x_arriba - DEDO_GRUESO, y1, x_arriba)]   # franja pegada a la palma que une los dedos
    for s in (-1, 1):
        borde = y0 if s < 0 else y1
        dedo_int = borde - s * DEDO_GRUESO
        piezas.append(box(min(borde, dedo_int), x_abajo, max(borde, dedo_int), x_arriba))
        punta_int = yc + s * ABERTURA / 2
        piezas.append(box(min(borde, punta_int), x_abajo, max(borde, punta_int), x_abajo + PUNTA_ALTO))
    perfil = unary_union(piezas).buffer(-REDONDEO, join_style=1).buffer(REDONDEO, join_style=1)
    a_z = np.array([[0, 1, 0, 0], [1, 0, 0, 0], [0, 0, -1, 0], [0, 0, 0, 1]], float)  # (u, v, w) -> (x=v, y=u, z=-w)
    pinza = extruir(perfil, -PINZA_ANCHO / 2, PINZA_ANCHO / 2, a_z)

    nueva = trimesh.boolean.union([arriba, palma, pinza], engine="manifold")
    import estilo_clasico
    nueva = estilo_clasico.aplicar(nueva, "z", -1, ESTILO_MANO)
    return original, nueva


def espejo_12(nueva):
    o11 = trimesh.load(os.path.join(ORIGEN, "Bracket11_B.stl"), force="mesh")
    o12 = trimesh.load(os.path.join(ORIGEN, "Bracket12_B.stl"), force="mesh")
    M = np.eye(4); M[1, 1] = -1
    ro = o11.copy(); ro.apply_transform(M)
    T = o12.bounds.mean(0) - ro.bounds.mean(0)
    b = nueva.copy(); b.apply_transform(M); b.apply_translation(T)
    return b


def main():
    os.makedirs(SALIDA, exist_ok=True)
    original, nueva = mano_nueva()
    b12 = espejo_12(nueva)
    for nombre, m in (("Bracket11_B", nueva), ("Bracket12_B", b12)):
        m.export(os.path.join(SALIDA, nombre + ".stl"))
        m.export(os.path.join(BASE, "para_imprimir", nombre + ".stl"))
        cuerpos = len(m.split(only_watertight=False))
        print(f"{nombre}: volumen {m.volume:.0f} mm3 (antes {original.volume:.0f}), largo bajo el codo "
              f"{EJE_CODO[0] - m.bounds[0][0]:.1f} mm (antes {EJE_CODO[0] - original.bounds[0][0]:.1f}), "
              f"caja {np.round(m.extents, 1).tolist()}, cuerpos {cuerpos}, volumen valido {m.is_volume}")
    if "--ipt" in sys.argv:
        import pythoncom, pywintypes
        from win32com.client import dynamic, gencache
        app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
        gencache.GetModuleForProgID("Inventor.Application")
        app.Documents.CloseAll(False)
        for nombre in ("Bracket11_B", "Bracket12_B"):
            doc = dynamic.Dispatch(app.Documents.Open(os.path.join(SALIDA, nombre + ".stl"), True)._oleobj_)
            ruta = os.path.join(SALIDA, nombre + ".ipt")
            if os.path.exists(ruta):
                os.remove(ruta)
            doc.SaveAs(ruta, False)
            doc.Close(True)


if __name__ == "__main__":
    main()
