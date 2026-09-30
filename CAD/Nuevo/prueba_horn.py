"""SEGMENTO: PIEZA DE PRUEBA DEL HORN (sin calibrador)
Placa para imprimir y probar el horn de un brazo del MG90S:
  - fila de arriba: agujeros para el cubo, de O6.6 a O7.4 (pasantes)
  - fila de abajo: ranuras para el ancho del brazo junto al cubo, de 4.4 a 6.4 (2 mm de hondo)
Cada hueco lleva puntitos marcados (1 = el mas chico). El que entra justo, sin juego y sin
forzar, da la medida para el rebaje de la pelvis nueva. Imprimir con la misma impresora,
boquilla y orientacion (acostada) que la pelvis.
"""
import os

import pythoncom
import pywintypes
import win32com.client
from win32com.client import dynamic, gencache

BASE = os.path.dirname(os.path.abspath(__file__))
CUBOS = (6.6, 6.8, 7.0, 7.2, 7.4)
BRAZOS = (4.4, 4.8, 5.2, 5.6, 6.0, 6.4)
PLACA = (78.0, 36.0, 3.0)          # largo, alto, espesor (ranuras de y 2.8 a 19.2, cubos en y 24)
RANURA_LARGO = 10.0
RANURA_HONDO = 2.0
PUNTO_DIAM = 1.0
PUNTO_HONDO = 0.6


def main():
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    k = win32com.client.constants
    tg = app.TransientGeometry
    cm = lambda v: v / 10
    ruta = os.path.join(BASE, "Prueba_horn.ipt")
    for i in range(app.Documents.Count, 0, -1):
        d = dynamic.Dispatch(app.Documents.Item(i)._oleobj_)
        if os.path.normcase(d.FullFileName) == os.path.normcase(ruta):
            d.Close(True)
    doc = dynamic.Dispatch(app.Documents.Add(k.kPartDocumentObject, app.FileManager.GetTemplateFile(k.kPartDocumentObject, k.kMetricSystemOfMeasure), True)._oleobj_)
    cd = doc.ComponentDefinition
    xy = cd.WorkPlanes.Item(3)
    arriba = cd.WorkPlanes.AddByPlaneAndOffset(xy, cm(PLACA[2]))
    arriba.Visible = False

    def extruir(sk, largo, direccion, op):
        return cd.Features.ExtrudeFeatures.AddByDistanceExtent(sk.Profiles.AddForSolid(), cm(largo), direccion, op)

    # placa
    sk = cd.Sketches.Add(xy)
    sk.SketchLines.AddAsTwoPointRectangle(tg.CreatePoint2d(0, 0), tg.CreatePoint2d(cm(PLACA[0]), cm(PLACA[1])))
    extruir(sk, PLACA[2], k.kPositiveExtentDirection, k.kJoinOperation)

    def puntos(sk, x, y, n):
        for j in range(n):
            sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(cm(x + (j - (n - 1) / 2) * 2.0), cm(y)), cm(PUNTO_DIAM / 2))

    # cubos: agujeros pasantes
    paso = PLACA[0] / len(CUBOS)
    sk = cd.Sketches.Add(xy)
    for j, diam in enumerate(CUBOS):
        sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(cm(paso * (j + 0.5)), cm(24.0)), cm(diam / 2))
    extruir(sk, PLACA[2] + 1, k.kPositiveExtentDirection, k.kCutOperation)
    sk = cd.Sketches.Add(arriba)
    for j in range(len(CUBOS)):
        puntos(sk, paso * (j + 0.5), 32.5, j + 1)
    extruir(sk, PUNTO_HONDO, k.kNegativeExtentDirection, k.kCutOperation)

    # brazos: ranuras de 2 mm de hondo con extremos redondeados
    paso = PLACA[0] / len(BRAZOS)
    sk = cd.Sketches.Add(arriba)
    for j, ancho in enumerate(BRAZOS):
        cx = paso * (j + 0.5)
        # ranura = rectangulo + dos circulos en los extremos
        sk.SketchLines.AddAsTwoPointRectangle(tg.CreatePoint2d(cm(cx - ancho / 2), cm(6.0)),
                                              tg.CreatePoint2d(cm(cx + ancho / 2), cm(6.0 + RANURA_LARGO)))
        for yy in (6.0, 6.0 + RANURA_LARGO):
            sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(cm(cx), cm(yy)), cm(ancho / 2))
    extruir(sk, RANURA_HONDO, k.kNegativeExtentDirection, k.kCutOperation)
    sk = cd.Sketches.Add(arriba)
    for j in range(len(BRAZOS)):
        puntos(sk, paso * (j + 0.5), 1.4, j + 1)
    extruir(sk, PUNTO_HONDO, k.kNegativeExtentDirection, k.kCutOperation)

    doc.SaveAs(ruta, False)
    doc.SaveAs(os.path.join(BASE, "para_imprimir", "Prueba_horn.stl"), True)
    print("guardado", ruta, "| volumen", round(cd.MassProperties.Volume * 1000), "mm3")


if __name__ == "__main__":
    main()
