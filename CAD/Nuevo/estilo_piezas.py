"""SEGMENTO: ESTILO 1 FACETADO EN LAS PIEZAS (relieve incorporado, sin cubiertas sueltas)
A cada pieza se le suma un relieve facetado (placa con esquinas cortadas y bisel de 45 grados + remaches) en su
cara de afuera; se imprime ya con esa forma. Se parte de la pieza con pernos M3 (piezas_m3) o rediseñada
(piezas_rediseno) y el relieve se funde 0.5 mm en ella. Todo en coordenadas locales de la pieza.
  - Link_W: frente del eslabon delantero de muslo y canilla, entre los dos nudillos (no pasa del eje).
  - Nee_B: rodillera al frente, entre los pernos de los eslabones.
  - Bracket04_B / Bracket05_B: puntera sobre la parte de adelante del pie.
Salida: piezas_estilo/*.stl (el ensamble las toma antes que las demas) y .ipt con --ipt.
"""
import os
import sys

import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

SALIDA = os.path.join(BASE, "piezas_estilo")
FUSION = 0.5                # cuanto entra el relieve en la pieza
REMACHE = (0.9, 1.6)        # radio, distancia desde la esquina de la cara de arriba (adentro del chaflan)
CHAFLAN = 0.22              # esquinas cortadas: fraccion del lado corto
BISEL = 0.9                 # retiro de la cara de arriba respecto del alto del relieve (45 grados ~ 1)

# pieza: (origen, [(eje de la cara, signo, rango en el primer eje libre, rango en el segundo, alto del relieve)])
# los ejes libres van en orden (x, y, z) sin el eje de la cara; la cara es la de la caja de la pieza
RELIEVES = {
    "Link_W": ("piezas_m3", [("x", +1, (1.5, 31.6), (2.5, 26.2), 2.8)]),
    "Nee_B": ("piezas_m3", [("z", -1, (-33.0, -1.5), (-8.0, 8.0), 2.8)]),
}
PUNTERAS = {"Bracket04_B": ("piezas_m3", 18.0, 2.8), "Bracket05_B": ("piezas_m3", 18.0, 2.8)}   # largo (z), alto


def superficie(pieza, eje, signo, ra, rb):
    """altura real de la cara (no el bounding box: si la pieza no es plana ahi, lo[k]/hi[k] da un
    valor de otro lado de la pieza y el relieve queda flotando, sin tocar el solido de verdad)."""
    k = "xyz".index(eje)
    otros = [i for i in range(3) if i != k]
    lo, hi = pieza.bounds
    origen = [0.0, 0.0, 0.0]
    origen[otros[0]], origen[otros[1]] = (ra[0] + ra[1]) / 2, (rb[0] + rb[1]) / 2
    origen[k] = hi[k] + 5 if signo > 0 else lo[k] - 5
    direccion = [0.0, 0.0, 0.0]
    direccion[k] = -1.0 if signo > 0 else 1.0
    locs, _, _ = pieza.ray.intersects_location([origen], [direccion], multiple_hits=False)
    return locs[0][k]


def relieve(ejes, rango_a, rango_b, h0, h1):
    """placa facetada: rectangulo de la cara (chaflan en las esquinas) y cara de arriba retirada 45 grados."""
    import manifold3d as mf
    (a0, a1), (b0, b1) = rango_a, rango_b
    c = CHAFLAN * min(a1 - a0, b1 - b0)

    def anillo(r):
        x0, x1, y0, y1 = a0 + r, a1 - r, b0 + r, b1 - r
        cc = max(c - 0.4 * r, 0.6)
        return [(x0 + cc, y0), (x1 - cc, y0), (x1, y0 + cc), (x1, y1 - cc), (x1 - cc, y1), (x0 + cc, y1), (x0, y1 - cc), (x0, y0 + cc)]

    alto = abs(h1 - h0)
    pts = [(u, v, h0) for u, v in anillo(0.0)] + [(u, v, h1) for u, v in anillo(BISEL * alto)]
    arriba = anillo(BISEL * alto)
    m = mf.Manifold.hull_points(np.array(pts, float))
    # remaches en las 4 esquinas de la cara de arriba
    xs = [p[0] for p in arriba]
    ys = [p[1] for p in arriba]
    d = REMACHE[1] + c * 0.3
    for u in (min(xs) + d, max(xs) - d):
        for v in (min(ys) + d, max(ys) - d):
            esfera = mf.Manifold.sphere(REMACHE[0], 16).translate((u, v, h1 - 0.35))
            m = m + esfera
    r = m.to_mesh()
    q = trimesh.Trimesh(r.vert_properties[:, :3], r.tri_verts)
    # (u, v, h) -> ejes de la pieza
    k = "xyz".index(ejes[0])
    libres = [i for i in range(3) if i != k]
    V = np.zeros_like(q.vertices)
    V[:, libres[0]], V[:, libres[1]], V[:, k] = q.vertices[:, 0], q.vertices[:, 1], q.vertices[:, 2]
    q = trimesh.Trimesh(V, q.faces)
    if np.linalg.det(np.eye(3)[[libres[0], libres[1], k]]) < 0:
        q.invert()
    return q


def a_manifold(m):
    import manifold3d as mf
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32), tri_verts=np.asarray(m.faces, np.uint32)))


def unir(pieza, extras):
    m = a_manifold(pieza)
    for e in extras:
        m = m + a_manifold(e)
    r = m.to_mesh()
    return trimesh.Trimesh(r.vert_properties[:, :3], r.tri_verts)


def main():
    os.makedirs(SALIDA, exist_ok=True)
    for nombre, (origen, lista) in RELIEVES.items():
        pieza = trimesh.load(os.path.join(BASE, origen, nombre + ".stl"), force="mesh")
        extras = []
        for eje, signo, ra, rb, alto in lista:
            cara = superficie(pieza, eje, signo, ra, rb)
            extras.append(relieve((eje,), ra, rb, cara - signo * FUSION, cara + signo * alto))
        nueva = unir(pieza, extras)
        nueva.export(os.path.join(SALIDA, nombre + ".stl"))
        print(f"{nombre}: valido {nueva.is_volume} | {pieza.volume / 1000:.1f} -> {nueva.volume / 1000:.1f} cm3")
    for nombre, (origen, largo, alto) in PUNTERAS.items():
        pieza = trimesh.load(os.path.join(BASE, origen, nombre + ".stl"), force="mesh")
        lo, hi = pieza.bounds
        # la punta del pie esta en -z (frente); cara de arriba de la suela medida con un rayo
        z_centro = lo[2] + largo / 2 + 1.5
        locs, _, _ = pieza.ray.intersects_location([[(lo[0] + hi[0]) / 2, hi[1] + 20, z_centro]], [[0, -1.0, 0]], multiple_hits=False)
        y_suela = locs[0][1]
        extra = relieve(("y",), (lo[0] + 2.0, hi[0] - 2.0), (lo[2] + 1.5, lo[2] + 1.5 + largo), y_suela - FUSION, y_suela + alto)
        nueva = unir(pieza, [extra])
        nueva.export(os.path.join(SALIDA, nombre + ".stl"))
        print(f"{nombre}: valido {nueva.is_volume} | {pieza.volume / 1000:.1f} -> {nueva.volume / 1000:.1f} cm3 | suela en y {y_suela:.1f}")
    if "--ipt" in sys.argv:
        import pythoncom
        import pywintypes
        from win32com.client import dynamic, gencache
        app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
        gencache.GetModuleForProgID("Inventor.Application")
        app.Documents.CloseAll(False)
        for nombre in list(RELIEVES) + list(PUNTERAS):
            d = dynamic.Dispatch(app.Documents.Open(os.path.join(SALIDA, nombre + ".stl"), False)._oleobj_)
            ruta = os.path.join(SALIDA, nombre + ".ipt")
            if os.path.exists(ruta):
                os.remove(ruta)
            d.SaveAs(ruta, False)
            d.Close(True)


if __name__ == "__main__":
    main()
