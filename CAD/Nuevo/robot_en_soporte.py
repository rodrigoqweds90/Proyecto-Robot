"""SEGMENTO: EL ROBOT ERGUIDO EN EL SOPORTE DE PARADO (y, con --todos, los 3 moldes en uso)
Todas las piezas van en la pose recta (servos en 90: piernas rectas, brazos colgando). Los soportes van en
naranja. Con --todos agrega, a los costados, cada pierna acostada dentro de su molde, girada como queda
apoyada en la mesa (el hueco hacia arriba). Deja el ensamble abierto en Inventor.
Uso: ROBOT_VARIANTE=B python robot_en_soporte.py [--todos]
"""
import os
import sys

import numpy as np
import pythoncom
import pywintypes
from win32com.client import dynamic, gencache

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import barrido_movimiento as bm  # noqa: E402
import soportes_armado as sa  # noqa: E402
import torso_estudio as te  # noqa: E402

ENSAMBLE, METRICO = 12291, 8195
APARTE = 210.0      # cuanto se corre a cada costado la escena de cada molde de pierna
GRIS = ("Torso_", "Cabeza", "Pelvis", "Spacer01", "Bracket11_B", "Bracket12_B")


def ipt_soporte(app, nombre):
    """el .ipt de malla del soporte, al dia con su STL."""
    stl = os.path.join(sa.SALIDA, nombre + ".stl")
    ipt = os.path.join(sa.SALIDA, nombre + ".ipt")
    if not os.path.exists(ipt) or os.path.getmtime(ipt) < os.path.getmtime(stl):
        d = dynamic.Dispatch(app.Documents.Open(stl, False)._oleobj_)
        if os.path.exists(ipt):
            os.remove(ipt)
        d.SaveAs(ipt, False)
        d.Close(True)
    return ipt


def colocar(occs, tg, ruta, M, aspecto=None):
    m = tg.CreateMatrix()
    m.SetCoordinateSystem(tg.CreatePoint(*(M[:3, 3] / 10)), tg.CreateVector(*M[:3, 0]), tg.CreateVector(*M[:3, 1]), tg.CreateVector(*M[:3, 2]))
    o = dynamic.Dispatch(occs.Add(ruta, m)._oleobj_)
    o.Grounded = True
    if aspecto is not None:
        o.Appearance = aspecto
    return o


def main():
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    app.Visible = True
    app.Documents.CloseAll(False)
    P, rectas, T, piernas, pelvis = sa.pose_recta()
    rutas = [n for n, _, _ in te.ensamble()]
    soporte_ipt = ipt_soporte(app, "Soporte_parado")
    tg = app.TransientGeometry
    asm = dynamic.Dispatch(app.Documents.Add(ENSAMBLE, app.FileManager.GetTemplateFile(ENSAMBLE, METRICO), True)._oleobj_)
    occs = asm.ComponentDefinition.Occurrences
    lib = next(dynamic.Dispatch(app.AssetLibraries.Item(i)._oleobj_) for i in range(1, app.AssetLibraries.Count + 1)
               if dynamic.Dispatch(app.AssetLibraries.Item(i)._oleobj_).DisplayName == "Biblioteca de materiales de Inventor")
    nombres = [dynamic.Dispatch(lib.AppearanceAssets.Item(j)._oleobj_).DisplayName for j in range(1, lib.AppearanceAssets.Count + 1)]
    aspecto = lambda n: dynamic.Dispatch(dynamic.Dispatch(lib.AppearanceAssets.Item(nombres.index(n) + 1)._oleobj_).CopyTo(asm)._oleobj_)
    gris, naranja = aspecto("Suave - Gris medio"), aspecto("Naranja")
    for i, p in enumerate(P):
        M = T[i] @ np.block([[np.asarray(p["M"], float), np.asarray(p["t"], float)[:, None]], [np.zeros((1, 3)), np.ones((1, 1))]])
        m = tg.CreateMatrix()
        m.SetCoordinateSystem(tg.CreatePoint(*(M[:3, 3] / 10)), tg.CreateVector(*M[:3, 0]), tg.CreateVector(*M[:3, 1]), tg.CreateVector(*M[:3, 2]))
        o = dynamic.Dispatch(occs.Add(bm.ruta_ipt(rutas[i]), m)._oleobj_)
        o.Grounded = True
        if p["nombre"].startswith(GRIS):
            o.Appearance = gris
    o = dynamic.Dispatch(occs.Add(soporte_ipt, tg.CreateMatrix())._oleobj_)
    o.Grounded = True
    o.Appearance = naranja
    if "--todos" in sys.argv:
        for lado, sufijo in ((1, "izq"), (-1, "der")):
            ipt = ipt_soporte(app, f"Soporte_pierna_{sufijo}")
            # el molde se acuesta en la mesa con el hueco hacia arriba: giro de -90 (izq) o +90 (der) en Y... en Z
            giro = np.array([[0.0, lado, 0.0], [-lado, 0.0, 0.0], [0.0, 0.0, 1.0]])
            mover = np.array([lado * APARTE, 95.0, 0.0])
            for i in piernas[lado]:
                M = T[i] @ np.block([[np.asarray(P[i]["M"], float), np.asarray(P[i]["t"], float)[:, None]], [np.zeros((1, 3)), np.ones((1, 1))]])
                M = np.block([[giro, mover[:, None]], [np.zeros((1, 3)), np.ones((1, 1))]]) @ M
                colocar(occs, tg, bm.ruta_ipt(rutas[i]), M, gris if P[i]["nombre"].startswith(GRIS) else None)
            M = np.block([[giro, mover[:, None]], [np.zeros((1, 3)), np.ones((1, 1))]])
            colocar(occs, tg, ipt, M, naranja)
    asm.SelectSet.Clear()
    ruta = os.path.join(BASE, "Moldes_armado.iam" if "--todos" in sys.argv else "Robot_en_soporte.iam")
    if os.path.exists(ruta):
        os.remove(ruta)
    asm.SaveAs(ruta, False)
    cam = app.ActiveView.Camera
    cam.Eye = tg.CreatePoint(28.0, 6.0, 38.0) if "--todos" not in sys.argv else tg.CreatePoint(10.0, 40.0, 55.0)
    cam.Target = tg.CreatePoint(0.0, -7.0, 0.0)
    cam.UpVector = tg.CreateUnitVector(0, 1, 0)
    cam.Fit()
    cam.Apply()
    nombre_png = "moldes_armado" if "--todos" in sys.argv else "robot_en_soporte"
    app.ActiveView.SaveAsBitmap(os.path.join(BASE, "vistas_torso", nombre_png + ".png"), 1100, 800)
    print("abierto:", ruta, "| piezas", occs.Count)


if __name__ == "__main__":
    main()
