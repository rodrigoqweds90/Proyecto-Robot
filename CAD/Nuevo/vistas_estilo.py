"""SEGMENTO: VISTAS CON LOS COLORES DE IMPRESION DEL ESTILO 1
Abre Robot_armado(_B).iam sin guardarlo, pinta cada pieza con el color en que se imprime y saca vistas.
Estilo clasico cuadrado: gris la carroceria (cabeza, torso, pecho, cadera, manos), negro los soportes."""
import os
import sys

import pythoncom
import pywintypes
from win32com.client import dynamic, gencache

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import torso as to  # noqa: E402

GRIS = ("Torso_", "Cabeza", "Pelvis", "Spacer01", "Bracket11_B", "Bracket12_B")   # carroceria (manos incluidas)
NARANJA = ()
VISTAS = {"robot": ((300.0, 150.0, 420.0), (0.0, -4.0, 1.0), 330.0), "piernas": ((170.0, -20.0, 260.0), (0.0, -8.0, 1.0), 190.0),
          "torso": ((170.0, 120.0, 230.0), (0.0, 2.5, 1.0), 160.0), "atras": ((-250.0, 120.0, -330.0), (0.0, -4.0, 1.0), 330.0)}


def main(prefijo="estilo"):
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    app.Documents.CloseAll(False)
    asm = dynamic.Dispatch(app.Documents.Open(os.path.join(BASE, f"Robot_armado{to.SUF}.iam"), True)._oleobj_)
    lib = next(dynamic.Dispatch(app.AssetLibraries.Item(i)._oleobj_) for i in range(1, app.AssetLibraries.Count + 1)
               if dynamic.Dispatch(app.AssetLibraries.Item(i)._oleobj_).DisplayName == "Biblioteca de materiales de Inventor")
    nombres = [dynamic.Dispatch(lib.AppearanceAssets.Item(j)._oleobj_).DisplayName for j in range(1, lib.AppearanceAssets.Count + 1)]
    aspecto = lambda n: dynamic.Dispatch(dynamic.Dispatch(lib.AppearanceAssets.Item(nombres.index(n) + 1)._oleobj_).CopyTo(asm)._oleobj_)
    gris, naranja = aspecto("Suave - Gris medio"), aspecto("Naranja")
    occs = asm.ComponentDefinition.Occurrences
    for i in range(1, occs.Count + 1):
        o = dynamic.Dispatch(occs.Item(i)._oleobj_)
        if NARANJA and o.Name.startswith(NARANJA):
            o.Appearance = naranja
        elif o.Name.startswith(GRIS):
            o.Appearance = gris
    asm.SelectSet.Clear()
    tg, v = app.TransientGeometry, app.ActiveView
    for nombre, (ojo, mira, ancho) in VISTAS.items():
        cam = v.Camera
        cam.Eye = tg.CreatePoint(*(c / 10 for c in ojo))
        cam.Target = tg.CreatePoint(*mira)
        cam.UpVector = tg.CreateUnitVector(0, 1, 0)
        cam.SetExtents(ancho / 10, ancho / 10)
        cam.Apply()
        v.SaveAsBitmap(os.path.join(BASE, "vistas_torso", f"{prefijo}_{nombre}.png"), 800, 800)
    asm.Close(True)


if __name__ == "__main__":
    main(*(sys.argv[1:2] or ["estilo"]))
