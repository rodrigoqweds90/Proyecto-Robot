"""SEGMENTO: ARMADO DEL NX25 EN INVENTOR
Ubica cada pieza (STL convertido a .ipt) con una transformacion local -> mundo calculada
a partir de sus agujeros de pivote. Mundo: Y arriba, Z hacia adelante del robot,
X hacia la izquierda del robot. Medidas en mm (Inventor usa cm).
"""
import math
import os
import sys

import numpy as np
import pythoncom
import pywintypes
import win32com.client
from win32com.client import dynamic, gencache

BASE = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(BASE, "vistas_armado")
os.makedirs(SALIDA, exist_ok=True)

X = np.array([1.0, 0, 0]); Y = np.array([0, 1.0, 0]); Z = np.array([0, 0, 1.0])


def dyn(o):
    return dynamic.Dispatch(o._oleobj_) if hasattr(o, "_oleobj_") else o


# ---------------------------------------------------------------------------
# SEGMENTO: GEOMETRIA DE LA PIERNA (ver analisis de agujeros)
# ---------------------------------------------------------------------------
ALFA = math.radians(35.0)            # inclinacion de muslo y tibia (cadera->tobillo = 100 mm)
MUSLO = np.array([0, -math.cos(ALFA), math.sin(ALFA)])   # hacia abajo y adelante
TIBIA = np.array([0, math.cos(ALFA), math.sin(ALFA)])    # desde el tobillo: arriba y adelante
L = 28.7


# Toda la pierna (menos el pie) 3.6 mm hacia adelante: asi la cara de atras del
# soporte de cadera y de tobillo queda al ras de la oreja del pivote (pelvis y pie)
# y la punta del eje del servo llega justo al rebaje del horn.
DZ = 3.6


def pierna(lado):
    """lado = +1 izquierda del robot (X+), -1 derecha."""
    s = lado
    piezas = []
    # Cadera (Bracket01 izq / Bracket03 der): X local abajo, Y local hacia atras, Z local lateral.
    cadera = "Bracket01_B" if s > 0 else "Bracket03_B"
    piezas.append((cadera, [-Y, -Z, X], [6.7 * s, -25.0, 35.1 + DZ]))
    # Tobillo (Bracket03 izq / Bracket01 der), girado: X local arriba.
    tobillo = "Bracket03_B" if s > 0 else "Bracket01_B"
    piezas.append((tobillo, [Y, -Z, -X], [6.7 * s, -125.0, 35.1 + DZ]))
    # Pie
    pie = "Bracket04_B" if s > 0 else "Bracket05_B"
    piezas.append((pie, [-X, Y, -Z], [21.0 * s, -147.0, -0.3]))
    # Rodilla
    piezas.append(("Nee_B", [-X, Y, -Z], [(9.15 if s > 0 else -43.35), -75.0, 35.56 + DZ]))
    # Marco del muslo y de la tibia (Bracket02): Z local a lo largo de la barra, Y local lateral.
    yl = -X * s
    for zl, origen_yz in ((MUSLO, (-44.0, 14.1 + DZ)), (TIBIA, (-106.0, 14.1 + DZ))):
        xl = np.cross(yl, zl)
        t = np.array([42.85 * s, origen_yz[0], origen_yz[1]]) - zl * 12.0
        t[0] = 42.85 * s
        piezas.append(("Bracket02_W", [xl, yl, zl], list(t)))
    # Eslabones: la placa (X local) siempre hacia adelante en las dos piernas; por
    # simetria de sus agujeros se puede elegir el lado lateral libremente.
    for zl, origen_yz in ((MUSLO, (-38.5, 29.1 + DZ)), (TIBIA, (-111.5, 29.1 + DZ))):
        yl_e = yl.copy()
        xl = np.cross(yl_e, zl)
        if xl[2] < 0:
            xl, yl_e = -xl, -yl_e
        tx = 26.25 * s - yl_e[0] * 16.55
        piezas.append(("Link_W", [xl, yl_e, zl], [tx, origen_yz[0], origen_yz[1]]))
    return piezas


# ---------------------------------------------------------------------------
# SEGMENTO: TORSO, CABEZA Y BRAZOS
# El marco va con sus ejes iguales al mundo. Tapas: +25 Y, +18.7 Z respecto al
# marco (sus 4 torretas de tornillo coinciden). Aro Spacer01 dado vuelta bajo el
# marco, centrado en el eje del servo de cintura (Z marco 23.3 = Z mundo 25.2).
# ---------------------------------------------------------------------------
T_MARCO = np.array([0.0, 9.0, 1.9])
Y_HOMBRO = 27.2        # eje del servo de hombro en el marco
X_BASE_HOMBRO = 43.1   # cara de la base del soporte de hombro: horn en la punta del eje del servo


def espejo(pieza, nombre_espejo, s_local):
    """Pieza del lado derecho: refleja el mundo en X y la pieza en su eje propio."""
    nombre, ejes, t = pieza
    m = np.column_stack([np.asarray(e, float) for e in ejes])
    mw = np.diag([-1.0, 1, 1])
    r = mw @ m @ np.diag(s_local)
    return (nombre_espejo, [r[:, 0], r[:, 1], r[:, 2]], list(mw @ np.asarray(t, float)))


def torso():
    # Sin pecho ni espalda (UpperCover_*): la electronica del robot propio es otra.
    piezas = [
        ("Frame01_W", [X, Y, Z], list(T_MARCO)),
        ("Spacer01_W", [X, -Y, -Z], list(T_MARCO + [0, -5.0, 23.3])),
        ("Head_W", [X, Y, Z], [0.0, 50.7, T_MARCO[2] + 12.1 + 38.3]),
        # PCA9685 (modelo Adafruit 815): atornillado bajo los 4 postes del fondo de
        # atras del marco (55.5 x 19.0 mm vs 55.9 x 19.05 de la placa). Los postes
        # miden 1.5 mm, justo para las patitas soldadas: placa con componentes abajo.
        (PCA9685, [X, Z, -Y], list(T_MARCO + [-29.21, 22.2, -19.7])),
    ]
    return piezas


def brazo_izquierdo():
    y_hombro = T_MARCO[1] + Y_HOMBRO                 # 36.2
    z_hombro = T_MARCO[2] + 23.3                     # 25.2
    eje_rol = np.array([X_BASE_HOMBRO + 24.1, y_hombro - 6.0, z_hombro])
    piezas = [
        # Soporte de hombro: base (horn del hombro) hacia el torso, orejas hacia afuera.
        ("Bracket07_B", [X, Y, Z], [X_BASE_HOMBRO, y_hombro - 12.0, z_hombro]),
        # Brazo: el servo de arriba (eje Y local, en z 12) va vertical colgando del
        # eje de la oreja del hombro, con el horn hacia atras; el de abajo (eje X
        # local, en z 43.2) queda horizontal en la cajita y mueve el codo hacia afuera.
        # X local = adentro, Y local = atras, Z local = abajo.
        ("Bracket09_W", [-X, -Z, -Y], [eje_rol[0], eje_rol[1] + 12.0, eje_rol[2] + 17.35]),
    ]
    codo_y = eje_rol[1] + 12.0 - 43.2
    codo_z = eje_rol[2] + 17.35 - 12.0
    # Mano: orejas arriba en el codo, horn hacia afuera, puno colgando. Oreja del
    # pivote al ras de la cara de atras del servo del codo (+4 mm hacia afuera).
    piezas.append(("Bracket11_B", [Y, -Z, -X], [eje_rol[0] - 5.05 + 1.55 + 4.0, codo_y - 24.1, codo_z + 6.0]))
    return piezas


def brazos():
    izq = brazo_izquierdo()
    espejos = {"Bracket07_B": ("Bracket08_B", [1, 1, -1]),
               "Bracket09_W": ("Bracket10_W", [1, -1, 1]),
               "Bracket11_B": ("Bracket12_B", [1, -1, 1])}
    der = [espejo(p, *espejos[p[0]]) for p in izq]
    return izq + der


# ---------------------------------------------------------------------------
# SEGMENTO: SERVOS (modelo MG90S) EN CADA SOPORTE
# Por soporte, en coordenadas locales: agujero de pestana cercano al eje, el lejano,
# y la direccion en que asoma el eje. El modelo tiene el punto medio de las pestanas
# en (0, 18.25, 0) y el eje en x = -5.5 apuntando a +Y.
# ---------------------------------------------------------------------------
# Los puntos de los agujeros guia van sobre la CARA donde apoyan las pestanas: la
# del lado hacia donde asoma el eje. El servo queda encima de esa cara, no hundido
# en el medio de su espesor.
SERVOS_EN = {
    "Bracket01_B": [((0, 24.6, 5.7), (0, 24.6, 33.4), (0, 1, 0))],
    "Bracket03_B": [((0, 24.6, -5.7), (0, 24.6, -33.4), (0, 1, 0))],
    "Bracket02_W": [((0, 22.0, 3.5), (0, 22.0, 31.2), (0, 1, 0))],
    "Bracket09_W": [((-6.0, 3.5, 43.2), (-6.0, 31.2, 43.2), (-1, 0, 0)),
                    ((0, 22.1, 3.5), (0, 22.1, 31.2), (0, 1, 0))],
    "Bracket10_W": [((-6.0, -3.5, 43.2), (-6.0, -31.2, 43.2), (-1, 0, 0)),
                    ((0, -22.1, 3.5), (0, -22.1, 31.2), (0, -1, 0))],
    "Frame01_W": [((0, 0.0, 31.8), (0, 0.0, 4.1), (0, -1, 0)),         # cintura
                  ((0, 48.7, 3.6), (0, 48.7, 31.3), (0, 1, 0)),        # cabeza
                  ((30.0, 35.7, 23.3), (30.0, 8, 23.3), (1, 0, 0)),    # hombro izquierdo (cara exterior de la pared)
                  ((-30.0, 35.7, 23.3), (-30.0, 8, 23.3), (-1, 0, 0))],# hombro derecho
}
Y_PESTANA_ABAJO = 17.0   # cara de abajo de las pestanas en el modelo del MG90S (espesor 2.5)
SERVO = os.path.join(os.path.dirname(BASE), "Componentes", "MG90S_grabcad_mg90s9.ipt")
PCA9685 = os.path.join(os.path.dirname(BASE), "Componentes", "PCA9685_adafruit_815.iam")


def servos(piezas):
    salida = []
    for nombre, ejes, t in piezas:
        if nombre not in SERVOS_EN:
            continue
        m = np.column_stack([np.asarray(e, float) for e in ejes])
        t = np.asarray(t, float)
        for cerca, lejos, eje in SERVOS_EN[nombre]:
            cerca_w = m @ np.asarray(cerca, float) + t
            lejos_w = m @ np.asarray(lejos, float) + t
            xs = lejos_w - cerca_w
            xs /= np.linalg.norm(xs)
            ys = m @ np.asarray(eje, float)
            zs = np.cross(xs, ys)
            medio = (cerca_w + lejos_w) / 2
            salida.append((SERVO, [xs, ys, zs], list(medio - ys * Y_PESTANA_ABAJO)))
    return salida


# ---------------------------------------------------------------------------
# SEGMENTO: PERNOS Pipe_B EN CADA PIVOTE
# Por pieza: (punto sobre el eje en la cara exterior del rebaje de O9, direccion
# hacia afuera). El perno entra con el reborde en el rebaje y la espiga en el O5.5.
# ---------------------------------------------------------------------------
PIPES_EN = {
    "Bracket06_W": [((21, -25, -43.2), (0, 0, -1)), ((-21, -25, -43.2), (0, 0, -1))],
    "Bracket01_B": [((19, 21, 40.1), (0, 0, 1)), ((13.5, 6, 40.1), (0, 0, 1)), ((13.5, 6, -1.0), (0, 0, -1))],
    "Bracket03_B": [((19, 21, -40.1), (0, 0, -1)), ((13.5, 6, -40.1), (0, 0, -1)), ((13.5, 6, 1.0), (0, 0, 1))],
    "Bracket04_B": [((0, 22, -45.9), (0, 0, -1))],
    "Bracket05_B": [((0, 22, -45.9), (0, 0, -1))],
    "Bracket07_B": [((24.1, 6, 21.1), (0, 0, 1))],
    "Bracket08_B": [((24.1, 6, -21.1), (0, 0, -1))],
    "Bracket11_B": [((24.1, 6, 21.1), (0, 0, 1))],
    "Bracket12_B": [((24.1, -6, 21.1), (0, 0, 1))],
    "Nee_B": [((3.5, yy, zz), (1, 0, 0)) for yy, zz in ((7.5, 5), (-7.5, 5), (13, -10), (-13, -10))] +
             [((-37.7, yy, zz), (-1, 0, 0)) for yy, zz in ((7.5, 5), (-7.5, 5), (13, -10), (-13, -10))],
}


def pipes(piezas):
    salida = []
    for nombre, ejes, t in piezas:
        m = np.column_stack([np.asarray(e, float) for e in ejes])
        for p, afuera in PIPES_EN.get(nombre, []):
            ys = m @ np.asarray(afuera, float)
            aux = X if abs(ys[0]) < 0.9 else Y
            xs = np.cross(aux, ys)
            xs /= np.linalg.norm(xs)
            zs = np.cross(xs, ys)
            cara = m @ np.asarray(p, float) + np.asarray(t, float)
            salida.append(("Pipe_B", [xs, ys, zs], list(cara - ys * 4.5)))
    return salida


def ensamble():
    piezas = [("Bracket06_W", [-X, Y, -Z], [0.0, 0.0, 0.0])]
    piezas += pierna(+1) + pierna(-1) + torso() + brazos()
    return piezas + servos(piezas) + pipes(piezas)


# ---------------------------------------------------------------------------
# SEGMENTO: CONSTRUCCION EN INVENTOR
# ---------------------------------------------------------------------------
def main():
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    k = win32com.client.constants
    tg = app.TransientGeometry
    ruta_iam = os.path.join(BASE, "NX25_armado.iam")

    for i in range(app.Documents.Count, 0, -1):
        d = dyn(app.Documents.Item(i))
        if os.path.normcase(d.FullFileName) == os.path.normcase(ruta_iam):
            d.Close(True)
    plantilla = app.FileManager.GetTemplateFile(k.kAssemblyDocumentObject, k.kMetricSystemOfMeasure)
    doc = dyn(app.Documents.Add(k.kAssemblyDocumentObject, plantilla, True))
    occs = dyn(doc.ComponentDefinition).Occurrences

    for nombre, ejes, t in ensamble():
        xl, yl, zl = (np.asarray(e, float) for e in ejes)
        # comprobar que sea una rotacion valida (derecha, ortonormal)
        m = np.column_stack([xl, yl, zl])
        assert np.allclose(m.T @ m, np.eye(3), atol=1e-6) and np.isclose(np.linalg.det(m), 1.0), nombre
        mat = tg.CreateMatrix()
        mat.SetCoordinateSystem(tg.CreatePoint(t[0] / 10, t[1] / 10, t[2] / 10),
                                tg.CreateVector(*xl), tg.CreateVector(*yl), tg.CreateVector(*zl))
        ruta_pieza = nombre if os.path.isabs(nombre) else os.path.join(BASE, nombre + ".ipt")
        occs.Add(ruta_pieza, mat)

    doc.SaveAs(ruta_iam, False)
    v = app.ActiveView
    for nombre, o in (("frente", k.kFrontViewOrientation), ("costado", k.kLeftViewOrientation),
                      ("atras", k.kBackViewOrientation), ("iso", k.kIsoTopRightViewOrientation)):
        cam = v.Camera
        cam.ViewOrientationType = o
        cam.Fit()
        cam.Apply()
        v.SaveAsBitmap(os.path.join(SALIDA, nombre + ".png"), 700, 700)
    # Vistas cercanas desde atras-arriba, como el render del GitHub
    cercanas = {
        "cerca_piernas_atras": ((-160.0, 60.0, -230.0), (0.0, -70.0, 20.0), 190.0),
        "cerca_brazo_atras": ((-170.0, 120.0, -200.0), (-45.0, 15.0, 25.0), 150.0),
        "cerca_cadera": ((-120.0, 40.0, -160.0), (-25.0, -35.0, 25.0), 90.0),
        "cerca_rodilla_tobillo": ((-140.0, -40.0, -170.0), (-25.0, -110.0, 25.0), 110.0),
        "cerca_torso_pca": ((-110.0, -30.0, -150.0), (0.0, 25.0, -5.0), 110.0),
    }
    for nombre, (ojo, mira, ancho) in cercanas.items():
        cam = v.Camera
        cam.Eye = tg.CreatePoint(ojo[0] / 10, ojo[1] / 10, ojo[2] / 10)
        cam.Target = tg.CreatePoint(mira[0] / 10, mira[1] / 10, mira[2] / 10)
        cam.UpVector = tg.CreateUnitVector(0, 1, 0)
        cam.SetExtents(ancho / 10, ancho / 10)
        cam.Apply()
        v.SaveAsBitmap(os.path.join(SALIDA, nombre + ".png"), 800, 800)
    print("Ensamble guardado:", ruta_iam, "| piezas:", occs.Count)


# ---------------------------------------------------------------------------
# SEGMENTO: VERIFICACION DE UNIONES SERVO -> HORN
# Horns en coordenadas locales: (punto sobre el eje en el centro del rebaje, eje).
# ---------------------------------------------------------------------------
HORNS_EN = {
    "Bracket06_W": [((0, -3.5, -25.2), (0, 1, 0)), ((21, -25, -0.8), (0, 0, 1)), ((-21, -25, -0.8), (0, 0, 1))],
    "Bracket01_B": [((19, 21, 0.8), (0, 0, 1))],
    "Bracket03_B": [((19, 21, -0.8), (0, 0, 1))],
    "Bracket04_B": [((0, 22, -1.2), (0, 0, 1))],
    "Bracket05_B": [((0, 22, -1.2), (0, 0, 1))],
    "Bracket07_B": [((24.1, 6, -19.1), (0, 0, 1)), ((1.4, 12, 0), (1, 0, 0))],
    "Bracket08_B": [((24.1, 6, 19.1), (0, 0, 1)), ((1.4, 12, 0), (1, 0, 0))],
    "Bracket11_B": [((24.1, 6, -19.1), (0, 0, 1))],
    "Bracket12_B": [((24.1, -6, -19.1), (0, 0, 1))],
    "Head_W": [((0, 21.5, -38.3), (0, 1, 0))],
}


def verificar():
    piezas = [("Bracket06_W", [-X, Y, -Z], [0.0, 0.0, 0.0])]
    piezas += pierna(+1) + pierna(-1) + torso() + brazos()
    horns = []
    for nombre, ejes, t in piezas:
        m = np.column_stack([np.asarray(e, float) for e in ejes])
        for p, e in HORNS_EN.get(nombre, []):
            horns.append((nombre, m @ np.asarray(p, float) + np.asarray(t, float), m @ np.asarray(e, float)))
    # servos con el soporte que los tiene
    for nombre, ejes, t in piezas:
        if nombre not in SERVOS_EN:
            continue
        for (_, (xs, ys, zs), o) in servos([(nombre, ejes, t)]):
            xs, ys, o = np.asarray(xs), np.asarray(ys), np.asarray(o)
            eje_p = o + xs * -5.5
            punta = eje_p + ys * 31.5
            mejor = None
            for hn, hp, he in horns:
                if abs(abs(np.dot(he, ys)) - 1) > 0.02:
                    continue
                d = hp - eje_p
                perp = np.linalg.norm(d - np.dot(d, ys) * ys)
                axial = np.dot(hp - punta, ys)
                # entre horns sobre la misma linea (izq/der) gana el mas cercano a la punta
                if mejor is None or perp < mejor[1] - 1.0 or (perp < mejor[1] + 1.0 and abs(axial) < abs(mejor[2])):
                    mejor = (hn, perp, axial)
            if mejor is None:
                print(f"{nombre:12s} servo en ({eje_p[0]:6.1f},{eje_p[1]:6.1f},{eje_p[2]:6.1f}) eje {np.round(ys,2)}: SIN horn paralelo")
            else:
                print(f"{nombre:12s} servo eje en ({eje_p[0]:6.1f},{eje_p[1]:6.1f},{eje_p[2]:6.1f}) dir {np.round(ys,2)} -> {mejor[0]:12s} "
                      f"desalineado {mejor[1]:5.1f} mm | horn a {mejor[2]:+5.1f} mm de la punta del eje")


if __name__ == "__main__":
    if "--verificar" in sys.argv:
        verificar()
    else:
        main()
