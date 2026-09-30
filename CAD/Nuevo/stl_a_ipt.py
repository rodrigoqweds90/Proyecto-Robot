"""SEGMENTO: PASAR LOS STL DE UNA CARPETA A .ipt DE MALLA
El ensamble de Inventor usa .ipt, no STL. Convierte los que falten o esten viejos.
Uso: python stl_a_ipt.py piezas_m3 [otra_carpeta ...]
"""
import os
import sys

import pythoncom
import pywintypes
from win32com.client import dynamic, gencache

BASE = os.path.dirname(os.path.abspath(__file__))


def main(carpetas):
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    app.Documents.CloseAll(False)
    for carpeta in carpetas:
        ruta = os.path.join(BASE, carpeta)
        for f in sorted(os.listdir(ruta)):
            if not f.endswith(".stl"):
                continue
            stl = os.path.join(ruta, f)
            ipt = stl[:-4] + ".ipt"
            if os.path.exists(ipt) and os.path.getmtime(ipt) >= os.path.getmtime(stl):
                continue
            d = dynamic.Dispatch(app.Documents.Open(stl, False)._oleobj_)
            if os.path.exists(ipt):
                os.remove(ipt)
            d.SaveAs(ipt, False)
            d.Close(True)
            print("ok", os.path.relpath(ipt, BASE))


if __name__ == "__main__":
    main(sys.argv[1:] or ["piezas_m3"])
