"""SEGMENTO: BOCETOS DE MANO (alternativas a la pinza de dos dedos, para elegir antes de modelar el detalle)
Todas ocupan la misma caja que la pinza actual bajo la palma (x -17.5..-1, y 0..24, z -8..8 en coordenadas de
Bracket11), asi no cambian los choques con el cuerpo. Se conserva todo lo de arriba (codo, horn, perno, palma) y el
panel con remaches del antebrazo.
Orientacion de Bracket11 en el robot: -x abajo, -y adelante, -z afuera, +z hacia el cuerpo (palma).
  - puno:  bloque redondeado con 3 ranuras de nudillos al frente
  - miton: paleta de 4 dedos (ranuras pasantes abajo) + pulgar inclinado hacia adelante
  - garra: 3 dedos separados que se curvan hacia la palma
Salida: piezas_boceto/Mano_*.stl y vistas_torso/mano_bocetos_*.png (con --vistas, Inventor abierto).
"""
import os
import sys

import manifold3d as mf
import numpy as np
import trimesh
from shapely.geometry import LineString

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import estilo_clasico as ec  # noqa: E402
import mano  # noqa: E402

SALIDA = os.path.join(BASE, "piezas_boceto")
X_ABAJO = mano.PALMA[0] - mano.DEDO_LARGO       # -17.5, igual que la pinza
Y0, Y1 = 0.0, 24.0
Z0, Z1 = -8.0, 8.0


# ================================================================== BASE: CODO + PALMA (sin la pinza)

def base():
    original = trimesh.load(os.path.join(mano.ORIGEN, "Bracket11_B.stl"), force="mesh")
    lo, hi = original.bounds
    arriba = trimesh.boolean.intersection([original, trimesh.creation.box(
        bounds=[[mano.X_CORTE, lo[1] - 1, lo[2] - 1], [hi[0] + 1, hi[1] + 1, hi[2] + 1]])], engine="manifold")
    caja, _ = mano.contorno_caja(original)
    a_x = np.array([[0, 0, 1, 0], [0, 1, 0, 0], [1, 0, 0, 0], [0, 0, 0, 1]], float)
    palma = mano.extruir(caja, mano.PALMA[0], mano.X_CORTE + 1.0, a_x)
    return ec.a_manifold(trimesh.boolean.union([arriba, palma], engine="manifold"))


# ================================================================== FORMAS

def puntos_caja_r(x0, x1, y0, y1, z0, z1, r):
    """vertices de 8 esferas en las esquinas: su casco es una caja con aristas redondeadas."""
    s = mf.Manifold.sphere(r, 16).to_mesh().vert_properties[:, :3]
    return np.vstack([s + (x, y, z) for x in (x0 + r, x1 - r) for y in (y0 + r, y1 - r) for z in (z0 + r, z1 - r)])


def caja_r(*a):
    return mf.Manifold.hull_points(puntos_caja_r(*a))


def falange(p, q, ancho_y, grueso_z, r):
    """tramo de dedo entre dos centros (x, y, z): casco de dos cajas redondeadas."""
    def pts(c):
        x, y, z = c
        return puntos_caja_r(x - r, x + r, y - ancho_y / 2, y + ancho_y / 2, z - grueso_z / 2, z + grueso_z / 2, r)
    return mf.Manifold.hull_points(np.vstack([pts(p), pts(q)]))


def ranura(p0, p1, ancho, eje_normal, h0, h1):
    """ranura de puntas redondas: segmento en el plano de los otros dos ejes, extruida sobre eje_normal."""
    poly = LineString([p0, p1]).buffer(ancho / 2, 8)
    return ec.solido_2d(poly, eje_normal, h0, h1)


def puno():
    m = caja_r(X_ABAJO, 0.0, Y0, Y1, Z0, Z1, 3.0)
    # nudillos: 3 ranuras horizontales (a lo ancho, z) en la cara de adelante (y 0); plano libre (x, z)
    for x in (-5.8, -9.8, -13.8):
        m = m - ranura((x, Z0 + 2.5), (x, Z1 - 2.5), 1.2, "y", Y0 - 1.0, Y0 + 0.8)
    return m


def miton():
    m = caja_r(X_ABAJO, 0.0, 7.0, Y1, -4.5, 4.5, 2.5)
    # 4 dedos: 3 ranuras pasantes desde abajo (plano libre x, y; atraviesan en z)
    for y in (11.35, 15.65, 19.95):
        m = m - ranura((X_ABAJO - 2.0, y), (-10.0, y), 1.2, "z", -6.0, 6.0)
    # pulgar inclinado hacia adelante y hacia la palma
    m = m + falange((-2.0, 6.0, 1.0), (-10.0, 3.2, 2.5), 5.0, 5.0, 2.0)
    return m


def garra():
    m = None
    for y0, y1 in ((0.0, 6.4), (8.8, 15.2), (17.6, 24.0)):
        yc, w = (y0 + y1) / 2, y1 - y0
        d = falange((-1.0, yc, -1.0), (-12.0, yc, -2.0), w, 6.0, 2.2) + \
            falange((-12.0, yc, -2.0), (-15.3, yc, 3.0), w, 6.0, 2.2)
        m = d if m is None else m + d
    return m


BOCETOS = {"puno": puno, "miton": miton, "garra": garra}


# ================================================================== SALIDA Y VISTAS

def a_trimesh(m):
    r = m.to_mesh()
    return trimesh.Trimesh(r.vert_properties[:, :3], r.tri_verts)


def main():
    os.makedirs(SALIDA, exist_ok=True)
    b = base()
    actual = trimesh.load(os.path.join(mano.SALIDA, "Bracket11_B.stl"), force="mesh")
    print(f"actual (pinza): {actual.volume / 1000:.2f} cm3 | caja {np.round(actual.bounds, 1).tolist()}")
    for nombre, f in BOCETOS.items():
        t = a_trimesh(b + f())
        t = ec.aplicar(t, "z", -1, mano.ESTILO_MANO)
        t.export(os.path.join(SALIDA, f"Mano_{nombre}.stl"))
        print(f"{nombre}: {t.volume / 1000:.2f} cm3 | valido {t.is_volume} | caja {np.round(t.bounds, 1).tolist()}")
    if "--vistas" in sys.argv:
        vistas()
    if "--robot" in sys.argv:
        vistas_robot()


def vistas_robot():
    """cada boceto puesto en Robot_armado_B.iam (sin guardarlo): mano de cerca y robot entero, en una hoja."""
    import pythoncom
    import pywintypes
    from PIL import Image, ImageDraw
    from win32com.client import dynamic, gencache
    import vistas_estilo as ve
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    app.Documents.CloseAll(False)
    # ipt de las dos manos por boceto, con el nombre de siempre en una carpeta propia (la ocurrencia se sigue llamando igual)
    carpetas = {"actual (pinza)": mano.SALIDA}
    for n in BOCETOS:
        carpeta = os.path.join(SALIDA, f"mano_{n}")
        os.makedirs(carpeta, exist_ok=True)
        b11 = trimesh.load(os.path.join(SALIDA, f"Mano_{n}.stl"), force="mesh")
        for nombre, m in (("Bracket11_B", b11), ("Bracket12_B", mano.espejo_12(b11))):
            stl, ipt = os.path.join(carpeta, nombre + ".stl"), os.path.join(carpeta, nombre + ".ipt")
            m.export(stl)
            d = dynamic.Dispatch(app.Documents.Open(stl, False)._oleobj_)
            if os.path.exists(ipt):
                os.remove(ipt)
            d.SaveAs(ipt, False)
            d.Close(True)
        carpetas[n] = carpeta
    asm = dynamic.Dispatch(app.Documents.Open(os.path.join(BASE, "Robot_armado_B.iam"), True)._oleobj_)
    lib = next(dynamic.Dispatch(app.AssetLibraries.Item(i)._oleobj_) for i in range(1, app.AssetLibraries.Count + 1)
               if dynamic.Dispatch(app.AssetLibraries.Item(i)._oleobj_).DisplayName == "Biblioteca de materiales de Inventor")
    nombres = [dynamic.Dispatch(lib.AppearanceAssets.Item(j)._oleobj_).DisplayName for j in range(1, lib.AppearanceAssets.Count + 1)]
    gris = dynamic.Dispatch(dynamic.Dispatch(lib.AppearanceAssets.Item(nombres.index("Suave - Gris medio") + 1)._oleobj_).CopyTo(asm)._oleobj_)
    occs = asm.ComponentDefinition.Occurrences
    for i in range(1, occs.Count + 1):
        o = dynamic.Dispatch(occs.Item(i)._oleobj_)
        if o.Name.startswith(ve.GRIS):
            o.Appearance = gris
    tg, v = app.TransientGeometry, app.ActiveView
    # (ojo, mira, ancho) en mm del mundo: mano izquierda (x +71.7) de cerca, y robot de frente
    camaras = [((330.0, 20.0, 330.0), (62.0, -22.0, 36.0), 115.0), ((200.0, 120.0, 460.0), (0.0, -4.0, 10.0), 300.0)]
    tmp = os.path.join(SALIDA, "_vista.png")
    columnas = []
    for etiqueta, carpeta in carpetas.items():
        manos = [dynamic.Dispatch(occs.Item(i)._oleobj_) for i in range(1, occs.Count + 1)]
        for o in manos:
            nombre = o.Name.split(":")[0]
            if nombre in ("Bracket11_B", "Bracket12_B"):
                M = o.Transformation
                o.Delete()
                nueva = dynamic.Dispatch(occs.Add(os.path.join(carpeta, nombre + ".ipt"), M)._oleobj_)
                nueva.Appearance = gris
        asm.SelectSet.Clear()
        col = []
        for ojo, mira, ancho in camaras:
            cam = v.Camera
            cam.Eye = tg.CreatePoint(*(c / 10 for c in ojo))
            cam.Target = tg.CreatePoint(*(c / 10 for c in mira))
            cam.UpVector = tg.CreateUnitVector(0, 1, 0)
            cam.SetExtents(ancho / 10, ancho / 10)
            cam.Apply()
            v.SaveAsBitmap(tmp, 500, 500)
            img = Image.open(tmp).convert("RGB")
            ImageDraw.Draw(img).text((10, 10), etiqueta, fill=(255, 255, 255))
            col.append(img)
        columnas.append(col)
    asm.Close(True)
    hoja = Image.new("RGB", (500 * len(columnas), 1000))
    for i, col in enumerate(columnas):
        for j, img in enumerate(col):
            hoja.paste(img, (500 * i, 500 * j))
    hoja.save(os.path.join(BASE, "vistas_torso", "mano_bocetos_robot.png"))
    os.remove(tmp)


def vistas():
    import pythoncom
    import pywintypes
    from PIL import Image, ImageDraw
    from win32com.client import dynamic, gencache
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    app.Documents.CloseAll(False)
    tg = app.TransientGeometry
    lista = [("actual (pinza)", os.path.join(mano.SALIDA, "Bracket11_B.stl"))] + \
            [(n, os.path.join(SALIDA, f"Mano_{n}.stl")) for n in BOCETOS]
    # (nombre, ojo) en coordenadas locales (mm): afuera-adelante y adentro-adelante (palma)
    camaras = [("afuera", (25.0, -110.0, -150.0)), ("palma", (5.0, -120.0, 150.0))]
    tmp = os.path.join(SALIDA, "_vista.png")
    for cam_nombre, ojo in camaras:
        tiras = []
        for etiqueta, ruta in lista:
            d = dynamic.Dispatch(app.Documents.Open(ruta, True)._oleobj_)
            v = app.ActiveView
            cam = v.Camera
            cam.Eye = tg.CreatePoint(ojo[0] / 10, ojo[1] / 10, ojo[2] / 10)
            cam.Target = tg.CreatePoint(0.3, 1.2, 0.0)
            cam.UpVector = tg.CreateUnitVector(1, 0, 0)
            cam.SetExtents(6.5, 6.5)
            cam.Apply()
            v.SaveAsBitmap(tmp, 500, 500)
            d.Close(True)
            img = Image.open(tmp).convert("RGB")
            ImageDraw.Draw(img).text((10, 10), etiqueta, fill=(255, 255, 255))
            tiras.append(img)
        hoja = Image.new("RGB", (500 * len(tiras), 500))
        for i, img in enumerate(tiras):
            hoja.paste(img, (500 * i, 0))
        hoja.save(os.path.join(BASE, "vistas_torso", f"mano_bocetos_{cam_nombre}.png"))
    os.remove(tmp)


if __name__ == "__main__":
    main()
