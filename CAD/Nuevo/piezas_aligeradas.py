"""SEGMENTO: PIEZAS ALIGERADAS PARA EL ENSAMBLE
Convierte los STL aligerados de para_imprimir (los que figuran en fea/resultados.json) a .ipt de malla
en piezas_aligeradas/, para que torso_estudio.py --aligerado arme el robot con ellas.
"""
import json
import os

import pythoncom
import pywintypes
from win32com.client import dynamic, gencache

BASE = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(BASE, "piezas_aligeradas")


def main():
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    app.Documents.CloseAll(False)
    os.makedirs(SALIDA, exist_ok=True)
    resultados = json.load(open(os.path.join(BASE, "fea", "resultados.json"), encoding="utf-8"))
    for nombre, r in sorted(resultados.items()):
        stl = os.path.join(BASE, "para_imprimir", nombre + ".stl")
        if r.get("quitado_mm3", 0) <= 0 or not os.path.exists(stl):
            continue
        doc = dynamic.Dispatch(app.Documents.Open(stl, True)._oleobj_)
        ruta = os.path.join(SALIDA, nombre + ".ipt")
        if os.path.exists(ruta):
            os.remove(ruta)
        doc.SaveAs(ruta, False)
        doc.Close(True)
        print("ok", nombre)


if __name__ == "__main__":
    main()
