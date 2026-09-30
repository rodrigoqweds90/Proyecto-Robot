"""SEGMENTO: PELVIS NUEVA (reemplaza Bracket06 del NX25)
Modelada en coordenadas del robot (X izquierda, Y arriba, Z adelante), mm.
Cambios funcionales:
  - horn de un brazo MG90S (7 agujeros) en rebaje con su forma exacta: el giro lo
    transmiten las paredes, no los tornillos -> sin juego en cadera y cintura
  - collar del horn en agujero de O6.6 (antes el cubo bailaba en O8)
  - el horn asienta sobre el bloque de arriba del servo (eje 3 mm afuera): la placa conserva
    el espesor del NX25 (queda a 0.1 mm del bloque) y el rebaje se forma con un borde elevado
    hacia afuera + 0.8 mm hundido en la placa
  - pernos de cadera: Pipe_M3 (ver m3_pernos.py) con M3; agujero O6.3 y rebaje O8.6 cuyo fondo queda
    0.2 mm debajo de la cabeza del pipe (el pipe apoya en el Bracket01/03 y la pelvis gira libre)
  - lobulos hexagonales y bordes biselados (otra forma, mismo espacio que el NX25)
Horn MG90S (STEP de GitHub, medido): brazo 2.0 de espesor, cubo O6.7, collar O6.3 x 2.8,
punta O4.0 a 15.95 del centro, agujeros O1.0 cada 1.97 desde 4.15.
"""
import json
import os

import numpy as np
import pythoncom
import pywintypes
import win32com.client
from win32com.client import dynamic, gencache

BASE = os.path.dirname(os.path.abspath(__file__))

# --- horn MG90S de un brazo ---
HORN_CUBO = 6.7
HORN_PUNTA = 4.0
HORN_LARGO = 15.95
HORN_ESPESOR = 2.0
HORN_COLLAR = 6.8                  # O6.3 en el de un brazo, O6.8 en el de cruz: el agujero sirve para los dos
HOLGURA = 0.15                     # por lado
TORNILLOS_HORN = (8.08, 12.02)     # agujeros del horn usados para retener (a lo largo del brazo)
PILOTO_TORNILLO = 1.2

# --- ejes (del ensamble del NX25) ---
CADERA_X = 21.0
CADERA_Y = -25.0
CINTURA_Z = 25.4
ARMA_CADERA = np.array([-0.865, 0.501])   # brazo del horn izquierdo, hacia el centro y arriba

# --- placas ---
Z_HORNS = (-1.0, 2.5)              # placa de los horns de cadera (cara de afuera en z -1), como el NX25
Z_BRAZO_CADERA = -2.2              # cara de afuera del brazo del horn asentado (punta del eje en z -0.4)
Z_PERNOS = (39.0, 43.2)            # placa de los pernos de cadera (cara de afuera en z 43.2)
Y_ARRIBA = (-7.2, -3.0)            # placa de arriba (como el NX25: cara de abajo = horn en cruz)
# disco elevado donde apoya y gira el aro espaciador del torso (O36 x 3), con rebaje central O21 x 2
DISCO = dict(diam=36.0, y=(-3.0, 0.0))
REBAJE_CENTRAL = dict(diam=21.0, hondo=2.0)
BANDA_CINTURA = dict(x=6.5, y=Y_ARRIBA[0])   # y: cara de abajo del horn en cruz asentado (anillo del cubo)
# --- horn en cruz MG90S (CAD-Arm, "4 spork"), cintura ---
CRUZ_ALTO_BRAZO = 2.3              # del anillo (0.2) al fondo del brazo
CRUZ_LARGO = (18.2, 8.2)           # punta del brazo largo (el de 7 agujeros, a los dos lados) y del corto
CRUZ_ANCHO_RAIZ = 6.8
CRUZ_PUNTA = 3.6
CRUZ_CORTO_ANCHO = 3.6
CRUZ_TORNILLOS = (8.24, 12.08)     # agujeros usados en los brazos largos
# torre redonda del MG90S alrededor del eje (O11.8, 5.5 de alto; el modelo de GrabCAD la dibuja
# como bloque rectangular, pero en el servo real es redonda: el NX25 le deja O11.9 en los hombros)
TORRE_DIAM = 11.8
TORRE_ARRIBA_CINTURA = -2.5        # tope de la torre del servo de cintura (y del mundo)
JUEGO_TORRE = 0.3                  # por lado -> agujero O12.4
# bultito del eje del engranaje intermedio, al lado de la torre (visto en foto del servo real y en
# los agujeros O5 a +-7 mm del NX25): lobulos a los dos lados para montar el servo en cualquier sentido
BULTO_DIAM = 5.0
BULTO_DIST = 7.0
# cara de arriba de la pelvis: ahi apoya y gira el aro espaciador -> sin agujeros pasantes de tornillos
PILOTO_HONDO = 3.0
M3_GIRA = 6.3                      # agujero para el cuerpo O6 del Pipe_M3 (v5)
M3_CABEZA = (10.3, 3.125)          # rebaje de la cabeza del pipe v7: fondo en z 40.075 (cara del Bracket01 38.675 + 1.6 - 0.2)
LOBULO_R = 7.5                     # hexagono alrededor de cada eje de cadera
ANCHO = 27.0
BISEL = 3.0

# --- paso de brida en la placa de los horns (cables de las piernas) ---
BRIDA = dict(x=12.0, y=-9.0, sep=3.6, ranura=(3.0, 1.6))


def contorno_placa():
    """Contorno XY de las placas: techo biselado, costados, lobulos hexagonales, centro en V.
    Se arma el lado izquierdo (x > 0) y el derecho es su espejo."""
    arriba = Y_ARRIBA[1]
    izq = [(ANCHO - BISEL, arriba), (ANCHO, arriba - BISEL), (ANCHO, CADERA_Y + 4.0)]
    for ang in (-30, -90, -150):
        a = np.radians(ang)
        izq.append((CADERA_X + LOBULO_R * np.cos(a), CADERA_Y + LOBULO_R * np.sin(a)))
    izq.append((7.0, -21.0))
    der = [(-x, y) for x, y in reversed(izq)]
    return izq + der


def contorno_horn(direccion, holgura=HOLGURA, n=24):
    """Casco convexo de cubo y punta del horn (2D, centro en el origen)."""
    r1, r2 = HORN_CUBO / 2 + holgura, HORN_PUNTA / 2 + holgura
    d = np.asarray(direccion, float) / np.linalg.norm(direccion)
    pts = [(r1 * np.cos(a), r1 * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 2 * n, endpoint=False)]
    pts += [tuple(d * HORN_LARGO + (r2 * np.cos(a), r2 * np.sin(a))) for a in np.linspace(0, 2 * np.pi, n, endpoint=False)]
    pts = np.array(pts)
    # casco convexo (monotone chain)
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def cruz(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    abajo, arriba = [], []
    for q in pts:
        while len(abajo) >= 2 and cruz(abajo[-2], abajo[-1], q) <= 0:
            abajo.pop()
        abajo.append(tuple(q))
    for q in pts[::-1]:
        while len(arriba) >= 2 and cruz(arriba[-2], arriba[-1], q) <= 0:
            arriba.pop()
        arriba.append(tuple(q))
    return abajo[:-1] + arriba[:-1]


def contorno_cruz(holgura=HOLGURA):
    """Contorno del horn en cruz (2D, x = brazos largos, y = brazos cortos), con holgura."""
    from shapely.geometry import MultiPoint, Point
    from shapely.ops import unary_union
    cubo = Point(0, 0).buffer(HORN_CUBO / 2 + holgura, 48)
    partes = [cubo]
    for sx in (1, -1):
        punta = Point(sx * (CRUZ_LARGO[0] - CRUZ_PUNTA / 2), 0).buffer(CRUZ_PUNTA / 2 + holgura, 24)
        raiz = MultiPoint([(0, CRUZ_ANCHO_RAIZ / 2 + holgura), (0, -CRUZ_ANCHO_RAIZ / 2 - holgura)])
        partes.append(MultiPoint(list(punta.exterior.coords) + list(raiz.geoms)).convex_hull)
    for sy in (1, -1):
        punta = Point(0, sy * (CRUZ_LARGO[1] - CRUZ_PUNTA / 2)).buffer(CRUZ_CORTO_ANCHO / 2 + holgura, 24)
        partes.append(MultiPoint(list(punta.exterior.coords) + [(-CRUZ_CORTO_ANCHO / 2 - holgura, 0), (CRUZ_CORTO_ANCHO / 2 + holgura, 0)]).convex_hull)
    forma = unary_union(partes).simplify(0.02)
    return list(forma.exterior.coords)[:-1]


def main():
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    k = win32com.client.constants
    tg = app.TransientGeometry
    cm = lambda v: v / 10
    app.Documents.CloseAll(False)
    ruta = os.path.join(BASE, "Pelvis.ipt")
    doc = dynamic.Dispatch(app.Documents.Add(k.kPartDocumentObject, app.FileManager.GetTemplateFile(k.kPartDocumentObject, k.kMetricSystemOfMeasure), True)._oleobj_)
    cd = doc.ComponentDefinition
    J, C = k.kJoinOperation, k.kCutOperation

    def plano(indice, offset):
        pl = cd.WorkPlanes.AddByPlaneAndOffset(cd.WorkPlanes.Item(indice), cm(offset))
        pl.Visible = False
        return pl

    def poligono(sk, puntos, a_sketch):
        # puntos de boceto compartidos: si cada linea crea los suyos, el perfil queda abierto
        sp = [sk.SketchPoints.Add(tg.CreatePoint2d(*[cm(c) for c in a_sketch(q)]), False) for q in puntos]
        for i in range(len(sp)):
            sk.SketchLines.AddByTwoPoints(sp[i], sp[(i + 1) % len(sp)])

    def extruir(sk, largo, op):
        return cd.Features.ExtrudeFeatures.AddByDistanceExtent(sk.Profiles.AddForSolid(), cm(largo), k.kPositiveExtentDirection, op)

    xy = lambda q: (q[0], q[1])                 # plano XY: sketch x->X, y->Y, normal +Z
    xz = lambda q: (-q[0], q[1])                # plano XZ: sketch x->-X, y->Z, normal +Y  (q = (X, Z))

    # 1) placas de adelante y de atras con el mismo contorno
    for z0, z1 in (Z_HORNS, Z_PERNOS):
        sk = cd.Sketches.Add(plano(3, z0))
        poligono(sk, contorno_placa(), xy)
        extruir(sk, z1 - z0, J)
    # 2) placa de arriba (biselada en z) y banda de la cintura hasta la cara del brazo del horn
    sk = cd.Sketches.Add(plano(2, Y_ARRIBA[0]))
    zt = [(-ANCHO + BISEL, Z_HORNS[0]), (ANCHO - BISEL, Z_HORNS[0]), (ANCHO, Z_HORNS[0] + BISEL),
          (ANCHO, Z_PERNOS[1] - BISEL), (ANCHO - BISEL, Z_PERNOS[1]), (-ANCHO + BISEL, Z_PERNOS[1]),
          (-ANCHO, Z_PERNOS[1] - BISEL), (-ANCHO, Z_HORNS[0] + BISEL)]
    poligono(sk, zt, xz)
    extruir(sk, Y_ARRIBA[1] - Y_ARRIBA[0], J)
    # disco elevado y su rebaje central
    sk = cd.Sketches.Add(plano(2, DISCO["y"][0] - 0.01))
    sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(0, cm(CINTURA_Z)), cm(DISCO["diam"] / 2))
    extruir(sk, DISCO["y"][1] - DISCO["y"][0] + 0.01, J)
    sk = cd.Sketches.Add(plano(2, DISCO["y"][1] - REBAJE_CENTRAL["hondo"]))
    sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(0, cm(CINTURA_Z)), cm(REBAJE_CENTRAL["diam"] / 2))
    extruir(sk, REBAJE_CENTRAL["hondo"] + 0.1, C)

    # 3) caderas: borde elevado alrededor del horn, rebaje (0.8 en la placa) y collar pasante
    for s in (1, -1):
        cx = s * CADERA_X
        direc = ARMA_CADERA * np.array([s, 1])
        sk = cd.Sketches.Add(plano(3, Z_BRAZO_CADERA))
        poligono(sk, [(cx + x, CADERA_Y + y) for x, y in contorno_horn(direc, holgura=HOLGURA + 2.4)], xy)
        extruir(sk, Z_HORNS[0] - Z_BRAZO_CADERA + 0.5, J)
        sk = cd.Sketches.Add(plano(3, Z_BRAZO_CADERA - 0.01))
        poligono(sk, [(cx + x, CADERA_Y + y) for x, y in contorno_horn(direc)], xy)
        extruir(sk, HORN_ESPESOR + 0.02, C)
        sk = cd.Sketches.Add(plano(3, Z_BRAZO_CADERA + HORN_ESPESOR - 0.02))
        sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(cm(cx), cm(CADERA_Y)), cm(HORN_COLLAR / 2 + 0.15))
        for dist in TORNILLOS_HORN:
            q = np.array([cx, CADERA_Y]) + direc / np.linalg.norm(direc) * dist
            sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(cm(q[0]), cm(q[1])), cm(PILOTO_TORNILLO / 2))
        extruir(sk, Z_HORNS[1] - Z_BRAZO_CADERA, C)

    # 4) cintura: horn en cruz por abajo (brazos largos en x), collar hacia arriba y hueco del bloque
    sk = cd.Sketches.Add(plano(2, BANDA_CINTURA["y"] - 0.01))
    poligono(sk, [(x, CINTURA_Z + z) for x, z in contorno_cruz()], xz)
    extruir(sk, CRUZ_ALTO_BRAZO + 0.02, C)
    sk = cd.Sketches.Add(plano(2, BANDA_CINTURA["y"] + CRUZ_ALTO_BRAZO - 0.02))
    sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(0, cm(CINTURA_Z)), cm(HORN_COLLAR / 2 + 0.15))
    extruir(sk, 10.0, C)
    sk = cd.Sketches.Add(plano(2, BANDA_CINTURA["y"] + CRUZ_ALTO_BRAZO - 0.02))
    for sx in (1, -1):
        for dist in CRUZ_TORNILLOS:
            sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(cm(-sx * dist), cm(CINTURA_Z)), cm(PILOTO_TORNILLO / 2))
    extruir(sk, PILOTO_HONDO, C)                     # ciegos: no salen a la cara donde gira el aro
    # la torre del servo baja por el aro espaciador (O19 interior) y entra en la placa de arriba
    sk = cd.Sketches.Add(plano(2, TORRE_ARRIBA_CINTURA - JUEGO_TORRE))
    sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(0, cm(CINTURA_Z)), cm(TORRE_DIAM / 2 + JUEGO_TORRE))
    extruir(sk, 5.0, C)
    sk = cd.Sketches.Add(plano(2, TORRE_ARRIBA_CINTURA - JUEGO_TORRE))
    for sz in (1, -1):
        sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(0, cm(CINTURA_Z + sz * BULTO_DIST)), cm(BULTO_DIAM / 2 + JUEGO_TORRE))
    extruir(sk, 5.0, C)

    # 5) pernos M3 de cadera en la placa de adelante
    sk = cd.Sketches.Add(plano(3, Z_PERNOS[0] - 0.1))
    for s in (1, -1):
        sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(cm(s * CADERA_X), cm(CADERA_Y)), cm(M3_GIRA / 2))
    extruir(sk, Z_PERNOS[1] - Z_PERNOS[0] + 0.2, C)
    sk = cd.Sketches.Add(plano(3, Z_PERNOS[1] - M3_CABEZA[1]))
    for s in (1, -1):
        sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(cm(s * CADERA_X), cm(CADERA_Y)), cm(M3_CABEZA[0] / 2))
    extruir(sk, M3_CABEZA[1] + 0.1, C)

    # 6) pasos de brida para los cables de las piernas (placa de los horns)
    sk = cd.Sketches.Add(plano(3, Z_HORNS[0] - 0.1))
    for s in (1, -1):
        for dy in (-BRIDA["sep"], BRIDA["sep"]):
            cx, cy = s * BRIDA["x"], BRIDA["y"] + dy
            a, b = BRIDA["ranura"]
            sk.SketchLines.AddAsTwoPointRectangle(tg.CreatePoint2d(cm(cx - a / 2), cm(cy - b / 2)), tg.CreatePoint2d(cm(cx + a / 2), cm(cy + b / 2)))
    extruir(sk, Z_HORNS[1] - Z_HORNS[0] + 0.2, C)

    doc.SaveAs(ruta, False)
    import torso
    torso.exportar_stl(doc, os.path.join(BASE, "stl", "Pelvis.stl"))
    mp = cd.MassProperties
    cmass = mp.CenterOfMass
    with open(os.path.join(BASE, "pelvis_masa.json"), "w", encoding="utf-8") as f:
        json.dump([mp.Volume * 1.24 * 0.75, [cmass.X * 10, cmass.Y * 10, cmass.Z * 10]], f)
    print(f"Pelvis: {mp.Volume * 1000:.0f} mm3, PLA aprox {mp.Volume * 1.24 * 0.75:.1f} g, cuerpos {cd.SurfaceBodies.Count}")


if __name__ == "__main__":
    main()
