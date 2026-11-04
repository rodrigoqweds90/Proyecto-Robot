"""ROBOT 2 - CONSTRUCCION EN INVENTOR
Arma cada pieza de r2_diseno como .ipt nativo (extrusiones editables, en su lugar de la pose parada) en
piezas/, exporta su STL y arma Robot2.iam con las piezas y los componentes (servos, bateria, electronica).
Uso: python r2_inventor.py [pieza ...]   (sin argumentos: todas)
"""
import os
import sys

import numpy as np
import pythoncom
import pywintypes
import win32com.client
from win32com.client import dynamic, gencache

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "..", "Nuevo"))
import r2_diseno as d  # noqa: E402
import torso as to  # noqa: E402   (clase Pieza: cajas y cilindros nativos; exportar_stl)

PIEZAS = os.path.join(BASE, "piezas")
ENSAMBLE = os.path.join(BASE, "Robot2.iam")


def dyn(o):
    return dynamic.Dispatch(o._oleobj_ if hasattr(o, "_oleobj_") else o)


def inventor():
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.EnsureDispatch("Inventor.Application")
    app.Visible = True
    return app


def cerrar_si_abierto(app, ruta):
    for i in range(app.Documents.Count, 0, -1):
        doc = dyn(app.Documents.Item(i))
        if os.path.normcase(doc.FullFileName) == os.path.normcase(ruta):
            doc.Close(True)


# =====================================================================
# SEGMENTO: PIEZAS NATIVAS
# =====================================================================
def construir_pieza(app, nombre, prims):
    ruta = os.path.join(PIEZAS, nombre + ".ipt")
    cerrar_si_abierto(app, ruta)
    p = to.Pieza(app, ruta)
    k = p.k
    fallas = []
    for i, pr in enumerate(prims):
        op = k.kJoinOperation if pr[0] == "J" else k.kCutOperation
        try:
            if pr[1] == "caja":
                x0, x1, y0, y1, z0, z1 = pr[2]
                p.caja(x0, x1, y0, y1, z0, z1, op)
            else:
                _, _, eje, (a, b), r, t0, t1 = pr
                if eje == "x":
                    p.cil_x([(a, b)], r, t0, t1, op)
                elif eje == "y":
                    p.cil_y([(a, b)], r, t0, t1, op)
                else:
                    p.cil_z([(a, b)], r, t0, t1, op)
        except Exception as e:          # p.ej. un corte que no toca material
            fallas.append((i, pr[0], pr[1], str(e)[:60]))
    p.doc.SaveAs(ruta, False)
    to.exportar_stl(p.doc, os.path.join(PIEZAS, nombre + ".stl"))
    cd = p.doc.ComponentDefinition
    vol = cd.MassProperties.Volume * 1000
    cuerpos = cd.SurfaceBodies.Count
    p.doc.Close(True)
    return vol, cuerpos, fallas


# =====================================================================
# SEGMENTO: ENSAMBLE
# =====================================================================
def matriz_inventor(tg, M):
    m = tg.CreateMatrix()
    m.SetCoordinateSystem(tg.CreatePoint(*(M[:3, 3] / 10.0)), tg.CreateVector(*M[:3, 0]),
                          tg.CreateVector(*M[:3, 1]), tg.CreateVector(*M[:3, 2]))
    return m


def armar(app, nombres):
    k = win32com.client.constants
    cerrar_si_abierto(app, ENSAMBLE)
    asm = dyn(app.Documents.Add(k.kAssemblyDocumentObject, app.FileManager.GetTemplateFile(k.kAssemblyDocumentObject, k.kMetricSystemOfMeasure), True))
    occs = asm.ComponentDefinition.Occurrences
    tg = app.TransientGeometry
    lib = dyn(app.AssetLibraries.Item(2)).AppearanceAssets
    blanco = next(dyn(lib.Item(i)) for i in range(1, lib.Count + 1) if dyn(lib.Item(i)).Name == "Plastic-016")
    blanco = dyn(blanco.CopyTo(asm))
    for n in nombres:
        o = dyn(occs.Add(os.path.join(PIEZAS, n + ".ipt"), tg.CreateMatrix()))
        o.Grounded = True
        o.Appearance = blanco
    for nombre, ruta, M, _ in d.componentes():
        o = dyn(occs.Add(os.path.abspath(ruta), matriz_inventor(tg, M)))
        o.Grounded = True
    app.SilentOperation = True          # sin esto Inventor abre un dialogo al guardar y el script queda esperando
    try:
        asm.SaveAs(ENSAMBLE, False)
    finally:
        app.SilentOperation = False
    v = dyn(app.ActiveView)
    cam = dyn(v.Camera)
    cam.Eye = tg.CreatePoint(30.0, 12.0, 40.0)
    cam.Target = tg.CreatePoint(0.0, -3.0, 0.0)
    cam.UpVector = tg.CreateUnitVector(0, 1, 0)
    cam.Fit()
    cam.Apply()
    v.SaveAsBitmap(os.path.join(BASE, "revision", "robot2_inventor.png"), 1400, 1100)
    return occs.Count


def main():
    os.makedirs(PIEZAS, exist_ok=True)
    app = inventor()
    todas = d.piezas()
    pedir = [a for a in sys.argv[1:] if not a.startswith("--")] or list(todas)
    for n in pedir:
        vol, cuerpos, fallas = construir_pieza(app, n, todas[n])
        aviso = "" if cuerpos == 1 else f"  <-- {cuerpos} cuerpos"
        print(f"{n:24s} {vol:8.0f} mm3{aviso}" + (f"  ({len(fallas)} operaciones sin efecto: {fallas[:2]})" if fallas else ""), flush=True)
    print("ensamble:", armar(app, list(todas)), "ocurrencias ->", ENSAMBLE, flush=True)


if __name__ == "__main__":
    main()
