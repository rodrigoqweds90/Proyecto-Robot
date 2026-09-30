"""SEGMENTO: PLACA DE IMPRESION EN INVENTOR (para mirar el paquete imprimir_B)
Pasa cada STL de imprimir_B a .ipt de malla y los acomoda en filas sobre la cama de la A1 (256 x 256),
en la misma orientacion en que se imprimen. Guarda Placa_impresion_B.iam y lo deja abierto.
Uso: python placa_impresion.py
"""
import os
import sys

import pythoncom
import pywintypes
import trimesh
from win32com.client import dynamic, gencache

BASE = os.path.dirname(os.path.abspath(__file__))
PAQUETE = os.path.join(BASE, "imprimir_B")
IPT = os.path.join(PAQUETE, "ipt")
CAMA = 256.0
HUECO = 6.0


def lugares(piezas):
    """las acomoda en camas de 256 x 256, una al lado de la otra: (nombre, placa, x, y) de cada esquina."""
    orden = sorted(piezas.items(), key=lambda kv: -kv[1][1])      # las mas profundas primero
    placa, x, y, fila = 0, 0.0, 0.0, 0.0
    for nombre, (ancho, fondo) in orden:
        if x + ancho > CAMA:
            x, y, fila = 0.0, y + fila + HUECO, 0.0
        if y + fondo > CAMA:
            placa, x, y, fila = placa + 1, 0.0, 0.0, 0.0
        yield nombre, placa, x, y
        x += ancho + HUECO
        fila = max(fila, fondo)


def main():
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    app.Visible = True
    app.Documents.CloseAll(False)
    os.makedirs(IPT, exist_ok=True)
    piezas = {}
    for f in sorted(os.listdir(PAQUETE)):
        if not f.endswith(".stl"):
            continue
        nombre = os.path.splitext(f)[0]
        m = trimesh.load(os.path.join(PAQUETE, f), force="mesh")
        piezas[nombre] = (m.extents[0], m.extents[1])
        ruta = os.path.join(IPT, nombre + ".ipt")
        if not os.path.exists(ruta) or os.path.getmtime(ruta) < os.path.getmtime(os.path.join(PAQUETE, f)):
            d = dynamic.Dispatch(app.Documents.Open(os.path.join(PAQUETE, f), False)._oleobj_)
            if os.path.exists(ruta):
                os.remove(ruta)
            d.SaveAs(ruta, False)
            d.Close(True)
            print("malla ->", nombre)
    ENSAMBLE, METRICO = 12291, 8195      # kAssemblyDocumentObject, kMetricSystemOfMeasure
    asm = dynamic.Dispatch(app.Documents.Add(ENSAMBLE, app.FileManager.GetTemplateFile(ENSAMBLE, METRICO), True)._oleobj_)
    tg = app.TransientGeometry
    occs = asm.ComponentDefinition.Occurrences
    for nombre, placa, x, y in lugares(piezas):
        M = tg.CreateMatrix()
        M.SetTranslation(tg.CreateVector((x + placa * (CAMA + 40.0)) / 10, y / 10, 0.0))
        o = dynamic.Dispatch(occs.Add(os.path.join(IPT, nombre + ".ipt"), M)._oleobj_)
        o.Grounded = True
        print(f"placa {placa + 1}: {nombre:20s} en x {x:6.1f}  y {y:6.1f}")
    ruta = os.path.join(BASE, "Placa_impresion_B.iam")
    if os.path.exists(ruta):
        os.remove(ruta)
    asm.SaveAs(ruta, False)
    cam = app.ActiveView.Camera
    cam.ViewOrientationType = 10758             # isometrica arriba-derecha-frente
    cam.Fit()
    cam.Apply()
    print("abierto:", ruta)


if __name__ == "__main__":
    main()
