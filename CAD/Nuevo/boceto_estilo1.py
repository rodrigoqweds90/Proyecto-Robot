"""SEGMENTO: BOCETO DEL ESTILO 1 (retro-industrial) SOBRE EL ROBOT B
Cubiertas facetadas simples (placa con bisel) pegadas a una sola pieza cada una, en el sistema de esa pieza,
para ver la forma y los colores antes de modelar el detalle. Gris claro las cubiertas, negro los soportes,
naranja los pernos (Pipe_M3).
Salida: piezas_boceto/Estilo1_*.stl, vistas_torso/estilo1_*.png (el ensamble no se guarda).
"""
import os
import sys

import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import barrido_movimiento as bm  # noqa: E402
import torso_estudio as te  # noqa: E402

SALIDA = os.path.join(BASE, "piezas_boceto")
VARIANTES = {
    "facetado": dict(esquina=("chaflan", 0.22), perfil=[(0.0, 0.0), (0.45, 1.0)]),
    "redondeado": dict(esquina=("redondo", 0.25), perfil=[(0.0, 0.0), (0.12, 0.45), (0.3, 0.8), (0.55, 1.0)]),
    "mezcla": dict(esquina=("redondo", 0.15), perfil=[(0.0, 0.0), (0.35, 1.0)]),
}
VARIANTE = VARIANTES["facetado"]


def placa_puntos(u0, u1, v0, v1, h0, h1):
    """puntos (u, v, h) de una placa con la esquina y el perfil de la VARIANTE (retiro relativo al alto)."""
    from shapely.geometry import box
    ancho, alto = u1 - u0, v1 - v0
    tipo, medida = VARIANTE["esquina"]
    c = medida * min(ancho, alto)
    pts = []
    for retiro, f in VARIANTE["perfil"]:
        r = retiro * abs(h1 - h0) * 1.6
        q = box(u0 + r, v0 + r, u1 - r, v1 - r)
        if tipo == "chaflan":
            cc = max(c - r * 0.4, 0.5)
            x0, y0, x1, y1 = q.bounds
            anillo = [(x0 + cc, y0), (x1 - cc, y0), (x1, y0 + cc), (x1, y1 - cc), (x1 - cc, y1), (x0 + cc, y1), (x0, y1 - cc), (x0, y0 + cc)]
        else:
            rr = max(c - r * 0.3, 0.5)
            anillo = list(q.buffer(-rr).buffer(rr, 8).exterior.coords)[:-1]
        h = h0 + f * (h1 - h0)
        pts += [(u, v, h) for u, v in anillo]
    return np.array(pts, float)
# (pieza, direccion del mundo de la cara que se cubre, margenes (a, b) del rectangulo, espesor, bisel,
#  recorte opcional del rectangulo en el mundo: (eje, min, max))
CUBIERTAS = [
    ("Link_W", (0, 0, 1), (1.5, 3.0), 2.0, 1.5, None),          # frente de muslo y canilla (eslabon delantero)
    ("Nee_B", (0, 0, 1), (0.5, 1.0), 3.0, 2.0, None),           # rodillera
    ("Bracket07_B", "afuera", (2.0, 2.0), 3.0, 2.5, None),      # hombrera
    ("Bracket11_B", "afuera", (2.0, 2.0), 2.5, 2.0, ("y", -14.0, 4.0)),   # antebrazo
    ("Pelvis", (0, 0, 1), (8.0, 4.0), 2.5, 2.0, None),          # placa de la cadera
]


def cubierta(malla_local, M, t, direccion, margen, espesor, bisel, recorte):
    """placa facetada sobre la cara de la caja de la pieza que mira hacia 'direccion' (mundo)."""
    import manifold3d as mf
    d_local = M.T @ np.asarray(direccion, float)
    k = int(np.argmax(np.abs(d_local)))
    s = np.sign(d_local[k])
    lo, hi = malla_local.bounds
    otros = [a for a in range(3) if a != k]
    a0, a1 = lo[otros[0]] + margen[0], hi[otros[0]] - margen[0]
    b0, b1 = lo[otros[1]] + margen[1], hi[otros[1]] - margen[1]
    if recorte:
        eje = "xyz".index(recorte[0])
        # recorte en el mundo: se pasa a local por los extremos del rectangulo
        w = np.zeros(3)
        w[eje] = 1.0
        wl = M.T @ w
        kk = int(np.argmax(np.abs(wl)))
        lim = sorted(((recorte[1] - t[eje]) * np.sign(wl[kk]), (recorte[2] - t[eje]) * np.sign(wl[kk])))
        if kk == otros[0]:
            a0, a1 = max(a0, lim[0]), min(a1, lim[1])
        elif kk == otros[1]:
            b0, b1 = max(b0, lim[0]), min(b1, lim[1])
    base = hi[k] + 0.3 if s > 0 else lo[k] - 0.3
    uvh = placa_puntos(a0, a1, b0, b1, base, base + s * (espesor + bisel))
    pts = np.zeros((len(uvh), 3))
    pts[:, otros[0]], pts[:, otros[1]], pts[:, k] = uvh[:, 0], uvh[:, 1], uvh[:, 2]
    m = mf.Manifold.hull_points(pts)
    r = m.to_mesh()
    q = trimesh.Trimesh(r.vert_properties[:, :3], r.tri_verts)
    T = np.eye(4)
    T[:3, :3], T[:3, 3] = M, t
    q.apply_transform(T)
    return q


def placa_mundo(x0, x1, y0, y1, h0, h1, eje="z"):
    """placa con la forma de la VARIANTE; eje: 'z' (plano xy, sale en z) o 'y' (plano xz, sale en y)."""
    import manifold3d as mf
    uvh = placa_puntos(x0, x1, y0, y1, h0, h1)
    pts = uvh if eje == "z" else uvh[:, [0, 2, 1]]
    r = mf.Manifold.hull_points(pts).to_mesh()
    return trimesh.Trimesh(r.vert_properties[:, :3], r.tri_verts)


def extras(P, rutas):
    """cubiertas en el mundo: bloque del pecho, placa del vientre, rejilla del costado de la cabeza, punteras."""
    import carcasa as ca
    z_pecho = ca.PECHO_Z[1]
    fuera = [placa_mundo(-32.0, 32.0, 22.0, 57.5, z_pecho - 0.2, 60.5),          # pecho alto (tapa el XL4015)
             placa_mundo(-22.0, 22.0, 6.0, 20.0, z_pecho - 0.2, z_pecho + 2.5)]   # vientre
    for i, p in enumerate(P):
        if p["nombre"] in ("Bracket04_B", "Bracket05_B"):                          # punteras de los pies
            m = bm.malla_local(rutas[i])
            T = np.eye(4)
            T[:3, :3], T[:3, 3] = p["M"], p["t"]
            m.apply_transform(T)
            (x0, y0, z0), (x1, y1, z1) = m.bounds
            locs, _, _ = m.ray.intersects_location([[(x0 + x1) / 2, y1 + 20, z1 - 8]], [[0, -1.0, 0]], multiple_hits=False)
            ytop = locs[0][1] if len(locs) else y0 + 3
            fuera.append(placa_mundo(x0 + 2.0, x1 - 2.0, z1 - 21.0, z1 - 1.0, ytop + 0.2, ytop + 3.5, eje="y"))
    return fuera


def main():
    os.makedirs(SALIDA, exist_ok=True)
    P = bm.un.piezas()
    rutas = [n for n, _, _ in te.ensamble()]
    locales = {}
    salida = []
    for nombre, direccion, margen, espesor, bisel, recorte in CUBIERTAS:
        for i, p in enumerate(P):
            if p["nombre"] != nombre:
                continue
            if nombre not in locales:
                locales[nombre] = bm.malla_local(rutas[i])
            d = direccion
            if d == "afuera":
                d = (np.sign(p["t"][0]) or 1.0, 0, 0)
            salida.append(cubierta(locales[nombre], p["M"], p["t"], d, margen, espesor, bisel, recorte))
    salida += extras(P, rutas)
    todo = trimesh.util.concatenate(salida)
    todo.export(os.path.join(SALIDA, f"Estilo1_{NOMBRE_VARIANTE}.stl"))
    print("cubiertas:", len(salida), "| volumen", round(todo.volume / 1000, 1), "cm3")
    if "--vistas" in sys.argv:
        vistas()


def vistas():
    import pythoncom
    import pywintypes
    from win32com.client import dynamic, gencache
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    app.Documents.CloseAll(False)
    d = dynamic.Dispatch(app.Documents.Open(os.path.join(SALIDA, f"Estilo1_{NOMBRE_VARIANTE}.stl"), False)._oleobj_)
    ipt = os.path.join(SALIDA, f"Estilo1_{NOMBRE_VARIANTE}.ipt")
    if os.path.exists(ipt):
        os.remove(ipt)
    d.SaveAs(ipt, False)
    d.Close(True)
    asm = dynamic.Dispatch(app.Documents.Open(os.path.join(BASE, f"Robot_armado{te.torso.SUF}.iam"), True)._oleobj_)
    occs = asm.ComponentDefinition.Occurrences
    lib = next(dynamic.Dispatch(app.AssetLibraries.Item(i)._oleobj_) for i in range(1, app.AssetLibraries.Count + 1)
               if dynamic.Dispatch(app.AssetLibraries.Item(i)._oleobj_).DisplayName == "Biblioteca de materiales de Inventor")
    nombres = [dynamic.Dispatch(lib.AppearanceAssets.Item(j)._oleobj_).DisplayName for j in range(1, lib.AppearanceAssets.Count + 1)]
    def aspecto(nombre):
        j = nombres.index(nombre) + 1
        return dynamic.Dispatch(dynamic.Dispatch(lib.AppearanceAssets.Item(j)._oleobj_).CopyTo(asm)._oleobj_)
    gris, naranja = aspecto("Suave - Gris medio"), aspecto("Naranja")
    for i in range(1, occs.Count + 1):
        o = dynamic.Dispatch(occs.Item(i)._oleobj_)
        if o.Name.startswith("Pipe_M3"):
            o.Appearance = naranja
        elif o.Name.startswith(("Torso_", "Cabeza")):
            o.Appearance = gris
    tg = app.TransientGeometry
    o = dynamic.Dispatch(occs.Add(ipt, tg.CreateMatrix())._oleobj_)
    o.Appearance = gris
    v = app.ActiveView
    for nombre, ojo, ancho in (("estilo1_robot", (300.0, 150.0, 420.0), 330.0), ("estilo1_piernas", (170.0, -20.0, 260.0), 190.0),
                               ("estilo1_torso", (170.0, 120.0, 230.0), 160.0)):
        cam = v.Camera
        cam.Eye = tg.CreatePoint(ojo[0] / 10, ojo[1] / 10, ojo[2] / 10)
        cam.Target = tg.CreatePoint(0.0, (-4.0 if ancho > 300 else (-8.0 if "piernas" in nombre else 2.5)), 1.0)
        cam.UpVector = tg.CreateUnitVector(0, 1, 0)
        cam.SetExtents(ancho / 10, ancho / 10)
        cam.Apply()
        v.SaveAsBitmap(os.path.join(BASE, "vistas_torso", f"{nombre}_{NOMBRE_VARIANTE}.png"), 800, 800)
    asm.Close(True)


NOMBRE_VARIANTE = next((a[2:] for a in sys.argv if a[2:] in VARIANTES), "facetado")
VARIANTE = VARIANTES[NOMBRE_VARIANTE]

if __name__ == "__main__":
    main()
