"""SEGMENTO: BOCETO DEL TORSO BLINDADO (hoja 1 de Gemini, estilo militar facetado)
Solo la forma de afuera, sin nada por dentro, para aprobar la silueta antes de modelar el torso real.
Forma = cuerpo (caja con biseles) unido al bloque del pecho (facetado, ancho y adelantado, borde de abajo en V).
Adentro del pecho va parado el XL4015 sobre la bateria (62 x 23.35 x 16.68).
Coordenadas del robot (X izquierda, Y arriba, Z adelante), en mm.
Salida: piezas_boceto/Boceto_cuerpo y Boceto_pecho (.stl + .ipt) y vistas_torso/boceto_*.png sobre el robot armado.
"""
import os
import sys

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(BASE, "piezas_boceto")

# --- cuerpo: caja del torso actual con biseles ---
CUERPO = (34.0, 1.0, 58.0, -27.0, 50.5)          # medio ancho, y0, y1, z atras, z adelante
# planos: (normal, punto por donde pasa); se queda lo que esta del lado contrario a la normal
BISELES_CUERPO = [
    ((1, 1.3, 0), (24.0, 58.0, 0)),                  # hombros: de (24, 58) a (34, 50)
    ((-1, 1.3, 0), (-24.0, 58.0, 0)),
    ((1, 0, -1), (34.0, 0, -23.0)),                  # aristas verticales de atras (4 mm)
    ((-1, 0, -1), (-34.0, 0, -23.0)),
    ((0, 1, -1), (0, 58.0, -24.0)),                  # arista de arriba atras (3 mm)
    ((0, -0.4, 1), (0, 1.0, 46.0)),                  # vientre: de (y 1, z 46) a (y 13.5, z 51)
    ((1, 0, 1), (34.0, 0, 48.0)),                    # aristas verticales de adelante (2 mm)
    ((-1, 0, 1), (-34.0, 0, 48.0)),
]
# --- armadura de arriba: envuelve toda la mitad de arriba (frente, costados y espalda), facetada ---
ARMADURA = (40.0, 20.0, 70.0, -27.0, 70.0)          # medio ancho, y0, y1, z atras, z adelante (caja que se recorta)
ARMADURA_PLANOS = [
    ((0.35, 0, 1), (0, 0, 64.0)),                    # quilla del pecho: z = 64 - 0.35|x|
    ((-0.35, 0, 1), (0, 0, 64.0)),
    ((1, 0, 1), (38.0, 0, 54.0)),                    # esquinas verticales de adelante
    ((-1, 0, 1), (-38.0, 0, 54.0)),
    ((1, 0, -1), (34.0, 0, -27.0)),                  # esquinas verticales de atras
    ((-1, 0, -1), (-34.0, 0, -27.0)),
    ((0.9, 1, 0), (26.0, 64.0, 0)),                  # hombros en pendiente
    ((-0.9, 1, 0), (-26.0, 64.0, 0)),
    ((0.45, -1, 0), (0, 16.0, 0)),                   # borde de abajo en V adelante
    ((-0.45, -1, 0), (-0.0, 16.0, 0)),
    ((0.45, -1, 0.9), (0, 16.0, 50.0)),              # cara de abajo del pecho inclinada
    ((-0.45, -1, 0.9), (0, 16.0, 50.0)),
    ((0, -1, -0.4), (0, 22.0, 0)),                   # borde de abajo atras sube un poco (y 22 + 0.4 * atras)
]
# el techo es un escalon: atras (ESP32, cuello) llega a y 58; el pecho sube a 68 sobre el XL4015
TECHO_ATRAS = [((0, 1, 0), (0, 58.0, 0))]
TECHO_PECHO = [((0, 0, -1), (0, 0, 30.0)),           # el pecho es solo de z 30 hacia adelante
               ((0, 1, 0), (0, 68.0, 0)),
               ((0, 1, 0.7), (0, 68.5, 52.0)),       # bisel de arriba hacia adelante
               ((0, 1, -1.25), (0, 58.0, 30.0))]     # bisel del cuello hacia atras
# huecos: hombros (el servo asoma por el costado) y cuello
HUECO_HOMBRO = (33.0, 50.0, 13.0, 49.0, 17.0, 33.5)  # x0, x1, y0, y1, z0, z1 (y espejo)
HUECO_CUELLO = (8.5, 57.0, 80.0, -2.0, 37.0)         # medio ancho, y0, y1, z0, z1

PARTES = ("Boceto_cuerpo", "Boceto_armadura")
COLORES = ("Gris oscuro", "Verde oliva")


def recortar(m, planos):
    for n, p in planos:
        n = np.asarray(n, float)
        n /= np.linalg.norm(n)
        m = m.trim_by_plane(tuple(-n), float(-n @ np.asarray(p, float)))
    return m


def boceto():
    import manifold3d as mf
    import trimesh
    x, y0, y1, z0, z1 = CUERPO
    cuerpo = recortar(mf.Manifold.cube((2 * x, y1 - y0, z1 - z0)).translate((-x, y0, z0)), BISELES_CUERPO)
    ax, ay0, ay1, az0, az1 = ARMADURA
    caja = recortar(mf.Manifold.cube((2 * ax, ay1 - ay0, az1 - az0)).translate((-ax, ay0, az0)), ARMADURA_PLANOS)
    arm = recortar(caja, TECHO_ATRAS) + recortar(caja, TECHO_PECHO)
    x0, x1, hy0, hy1, hz0, hz1 = HUECO_HOMBRO
    for sx in (1, -1):
        a_, b_ = sorted((sx * x0, sx * x1))
        arm = arm - mf.Manifold.cube((b_ - a_, hy1 - hy0, hz1 - hz0)).translate((a_, hy0, hz0))
    cx, cy0, cy1, cz0, cz1 = HUECO_CUELLO
    arm = arm - mf.Manifold.cube((2 * cx, cy1 - cy0, cz1 - cz0)).translate((-cx, cy0, cz0))
    pecho = arm
    return [trimesh.Trimesh(q.to_mesh().vert_properties[:, :3], q.to_mesh().tri_verts) for q in (cuerpo, pecho)]


def vistas():
    """inserta el boceto en el robot armado (sin las piezas del torso) y saca vistas."""
    import pythoncom
    import pywintypes
    from win32com.client import dynamic, gencache
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    app.Documents.CloseAll(False)
    ipts = []
    for nombre in PARTES:
        doc = dynamic.Dispatch(app.Documents.Open(os.path.join(SALIDA, nombre + ".stl"), True)._oleobj_)
        ipt = os.path.join(SALIDA, nombre + ".ipt")
        if os.path.exists(ipt):
            os.remove(ipt)
        doc.SaveAs(ipt, False)
        doc.Close(True)
        ipts.append(ipt)
    asm = dynamic.Dispatch(app.Documents.Open(os.path.join(BASE, "Robot_armado.iam"), True)._oleobj_)
    occs = asm.ComponentDefinition.Occurrences
    for i in range(1, occs.Count + 1):
        o = dynamic.Dispatch(occs.Item(i)._oleobj_)
        if o.Name.startswith(("Torso_cuerpo", "Torso_pecho", "Torso_espalda", "Torso_barra", "UBEC")):
            o.Visible = False
    tg = app.TransientGeometry
    lib = next(dynamic.Dispatch(app.AssetLibraries.Item(i)._oleobj_) for i in range(1, app.AssetLibraries.Count + 1)
               if dynamic.Dispatch(app.AssetLibraries.Item(i)._oleobj_).DisplayName == "Biblioteca de materiales de Inventor")
    aspectos = {dynamic.Dispatch(lib.AppearanceAssets.Item(j)._oleobj_).DisplayName: lib.AppearanceAssets.Item(j)
                for j in range(1, lib.AppearanceAssets.Count + 1)}
    for ipt, color in zip(ipts, COLORES):
        o = dynamic.Dispatch(occs.Add(ipt, tg.CreateMatrix())._oleobj_)
        o.Appearance = dynamic.Dispatch(aspectos[color]._oleobj_).CopyTo(asm)
    v = app.ActiveView
    for nombre, ojo, ancho in (("boceto_frente", (170.0, 120.0, 230.0), 150.0), ("boceto_costado", (300.0, 30.0, 10.0), 140.0),
                               ("boceto_atras", (-160.0, 150.0, -200.0), 150.0), ("boceto_robot", (300.0, 150.0, 420.0), 330.0)):
        cam = v.Camera
        cam.Eye = tg.CreatePoint(ojo[0] / 10, ojo[1] / 10, ojo[2] / 10)
        cam.Target = tg.CreatePoint(0.0, (2.5 if ancho < 200 else -4.0), 1.0)
        cam.UpVector = tg.CreateUnitVector(0, 1, 0)
        cam.SetExtents(ancho / 10, ancho / 10)
        cam.Apply()
        v.SaveAsBitmap(os.path.join(BASE, "vistas_torso", nombre + ".png"), 800, 800)
    asm.Close(True)                                      # sin guardar: el ensamble queda como estaba


def main():
    os.makedirs(SALIDA, exist_ok=True)
    for nombre, m in zip(PARTES, boceto()):
        m.export(os.path.join(SALIDA, nombre + ".stl"))
        print(f"{nombre}: valido {m.is_volume} | caja {np.round(m.bounds, 1).tolist()}")
    if "--vistas" in sys.argv:
        vistas()


if __name__ == "__main__":
    main()
