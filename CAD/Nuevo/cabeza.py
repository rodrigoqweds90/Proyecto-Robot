"""SEGMENTO: CABEZA NUEVA (estilo robot clasico cuadrado)
(versiones anteriores en OldVersions/cabeza_robovie y OldVersions/cabeza_robosavvy)
  - caja casi recta (radios chicos), OLED adentro como siempre
  - cara: marco en relieve con visera rectangular que deja ver todo el OLED (23 x 12 visibles),
    rejilla de boca abajo y remaches en las esquinas
  - orejas: discos tipo tuerca a los costados
  - cuello: rebaje con la forma del horn de 1 brazo (holgura 0.4 por lado), pilotos ciegos para
    sus 2 tornillos y paso de O6 para el tornillo central del eje
  - OLED: 4 postes M2 en la cara interna del frente
Se construye como solido exterior menos solido interior (mas control que el vaciado).
Ejes locales: origen en el eje del cuello a la altura del techo, Y arriba, Z adelante.
Medidas en mm; Inventor trabaja en cm.
"""
import os

import pythoncom
import pywintypes
import win32com.client
from win32com.client import dynamic, gencache

import pelvis as pv
import torso as to

BASE = os.path.dirname(os.path.abspath(__file__))

# --- medidas principales (editables) ---
ANCHO = 46.0          # X  (46: la pantalla de 27.3 pasa entre los pilares M3)
PROFUNDO = 38.0       # Z
ALTO = 37.0           # Y  (37: por dentro quedan 29.2 mm para la pantalla de 27.3)
ADELANTE = 4.0        # cuanto se corre la cabeza hacia adelante del eje del cuello
PARED = 2.4
PISO = 5.4          # 2 mm se los come el rebaje del horn: queda 3.4 mm de material sano
# Tapa trasera: la cabeza se parte en vertical en Z_CORTE; atras queda la tapa redondeada
Z_CORTE = -6.0          # desde el eje del cuello; la tapa ocupa de -15 a -6
TORRE_DIAM = 6.0        # pilares del frente donde muerden los tornillos M3
TORRE_LARGO = 6.0
TORRE_EMPOTRADO = 0.6     # cuanto entra el pilar en la pared y el piso (tangente quedaba unido solo por una linea)
TORRE_AGUJERO = 2.6     # M3 autorroscante en PLA
PASO_M3 = 3.4
CABEZA_M3 = 6.0         # asiento plano para la cabeza del tornillo
LENGUETA_ANCHO = 12.0   # lengueta arriba que alinea la tapa
PASO_CABLES = (12.0,)   # ancho del paso de cables del OLED en el piso de la tapa (el largo va de pared a corte)
LENGUETA_ESPESOR = 1.2
LENGUETA_LARGO = 2.0
RADIO_LADOS = 3.0             # estilo cuadrado: esquinas apenas redondeadas
RADIO_TAPA = 2.5
# Cara: marco en relieve alrededor de la visera, centrado en el area visible del OLED (23 x 12 mm)
VENTANA_CENTRO_Y = -18.0      # desde el techo (y = 0) hacia abajo; centro de la pantalla apoyada en el piso
MARCO_EXTERIOR = (36.0, 21.0)
MARCO_INTERIOR = (28.0, 16.0)
MARCO_ALTO = 1.2
VISERA = (25.0, 13.5)         # pasante
REJILLA_Y = (-35.0, -31.0)    # boca: ranuras grabadas bajo el marco
REJILLA_X = (-8.0, -4.0, 0.0, 4.0, 8.0)
REJILLA_ANCHO = 1.6
REJILLA_FONDO = 0.8
REMACHES = [(sx * 19.5, y) for sx in (1, -1) for y in (-4.0, -33.0)]
REMACHE_DIAM = 2.4
REMACHE_ALTO = 0.7
# Orejas: disco con rebaje y botoncito al centro, en cada costado
OREJA_Y = -18.0
OREJA_Z = 4.0
OREJA_DIAM = 12.0
OREJA_ALTO = 2.0
OREJA_REBAJE = (7.0, 1.0)     # diametro, fondo
OREJA_BOTON = 3.0
# Cuello: horn de 1 brazo apuntando hacia adelante (datos medidos, ver pelvis.py)
EJE_DIAM = 6.0          # 5.0 quedo justo al imprimir
HOLGURA_HORN = 0.4      # por lado; con 0.15 (la de la pelvis) el horn no entro en la cabeza impresa
PILOTO_HONDO = 5.0       # desde abajo: 2.4 del rebaje + 2.6 para los tornillitos del horn
# Sujecion del OLED: 4 postes en la cara interna del frente, M2 directo (sin insertos). La placa (27.5 x 27)
# apoya en los postes con el vidrio hacia la visera; agujeros de la placa a ~2 mm de los bordes
OLED_AGUJEROS = (23.5, 23.0)   # entre centros: ancho (X), alto (Y) -- medir en la placa antes de imprimir
OLED_POSTE_DIAM = 3.6        # fino: los agujeros de la placa quedan casi pegados al borde del vidrio
OLED_POSTE_ALTO = 3.0          # vidrio 1.5 + 1.5 de aire hasta la pared
OLED_PILOTO = 1.7              # M2x6: placa 1.2 + 4.8 en el plastico
OLED_PILOTO_HONDO = 4.8        # poste 3.0 + 1.8 en la pared de 2.4: quedan 0.6 de piel en la cara


def dyn(o):
    return dynamic.Dispatch(o._oleobj_) if hasattr(o, "_oleobj_") else o


def construir(app, parte):
    k = win32com.client.constants
    tg = app.TransientGeometry
    cm = lambda v: v / 10.0
    os.makedirs(BASE, exist_ok=True)
    ruta = os.path.join(BASE, "Cabeza_frente.ipt" if parte == "frente" else "Cabeza_tapa.ipt")
    for i in range(app.Documents.Count, 0, -1):
        d = dyn(app.Documents.Item(i))
        if os.path.normcase(d.FullFileName) == os.path.normcase(ruta):
            d.Close(True)

    doc = dyn(app.Documents.Add(k.kPartDocumentObject, app.FileManager.GetTemplateFile(k.kPartDocumentObject, k.kMetricSystemOfMeasure), True))
    comp = doc.ComponentDefinition
    xz = comp.WorkPlanes.Item(2)

    def rectangulo(ancho, profundo, centro_z):
        sk = comp.Sketches.Add(xz)
        sk.SketchLines.AddAsTwoPointRectangle(tg.CreatePoint2d(cm(-ancho / 2), cm(centro_z - profundo / 2)),
                                              tg.CreatePoint2d(cm(ancho / 2), cm(centro_z + profundo / 2)))
        return sk

    def extruir(sk, largo, operacion, desde=None):
        perfil = sk.Profiles.AddForSolid()
        return comp.Features.ExtrudeFeatures.AddByDistanceExtent(perfil, cm(largo), k.kNegativeExtentDirection, operacion)

    def redondear(filtro, radio, cuerpo=None):
        cuerpo = cuerpo or comp.SurfaceBodies.Item(1)
        col = app.TransientObjects.CreateEdgeCollection()
        for j in range(1, cuerpo.Edges.Count + 1):
            e = cuerpo.Edges.Item(j)
            if filtro(e):
                col.Add(e)
        if col.Count == 0:
            return
        defi = dyn(comp.Features.FilletFeatures.CreateFilletDefinition())
        defi.AddConstantRadiusEdgeSet(col, cm(radio))
        return comp.Features.FilletFeatures.Add(defi)

    # 1) caja exterior
    extruir(rectangulo(ANCHO, PROFUNDO, ADELANTE), ALTO, k.kJoinOperation)
    # esquinas verticales
    redondear(lambda e: e.GeometryType == k.kLineSegmentCurve and abs(abs(e.Geometry.Direction.Y) - 1) < 1e-6, RADIO_LADOS)
    # techo
    redondear(lambda e: abs(e.Evaluator.RangeBox.MaxPoint.Y) < 1e-6 and abs(e.Evaluator.RangeBox.MinPoint.Y) < 1e-6, RADIO_TAPA)

    # 2) hueco interior: un solido aparte con los mismos redondeos menos la pared, restado al final.
    #    (una caja recta asoma por los redondeos de afuera y abre rendijas en las esquinas)
    plano_interior = comp.WorkPlanes.AddByPlaneAndOffset(xz, cm(-PARED))
    plano_interior.Visible = False
    sk = comp.Sketches.Add(plano_interior)
    sk.SketchLines.AddAsTwoPointRectangle(
        tg.CreatePoint2d(cm(-(ANCHO - 2 * PARED) / 2), cm(ADELANTE - (PROFUNDO - 2 * PARED) / 2)),
        tg.CreatePoint2d(cm((ANCHO - 2 * PARED) / 2), cm(ADELANTE + (PROFUNDO - 2 * PARED) / 2)))
    ext = comp.Features.ExtrudeFeatures.AddByDistanceExtent(sk.Profiles.AddForSolid(), cm(ALTO - PARED - PISO),
                                                           k.kNegativeExtentDirection, k.kNewBodyOperation)
    hueco = ext.SurfaceBodies.Item(1)
    if RADIO_LADOS - PARED > 0.3:
        redondear(lambda e: e.GeometryType == k.kLineSegmentCurve and abs(abs(e.Geometry.Direction.Y) - 1) < 1e-6,
                  RADIO_LADOS - PARED, cuerpo=hueco)
    hueco = comp.SurfaceBodies.Item(2)
    if RADIO_TAPA - PARED > 0.3:
        redondear(lambda e: abs(e.Evaluator.RangeBox.MaxPoint.Y * 10 + PARED) < 1e-4 and abs(e.Evaluator.RangeBox.MinPoint.Y * 10 + PARED) < 1e-4,
                  RADIO_TAPA - PARED, cuerpo=hueco)
    herramientas = app.TransientObjects.CreateObjectCollection()
    herramientas.Add(comp.SurfaceBodies.Item(2))
    comp.Features.CombineFeatures.Add(comp.SurfaceBodies.Item(1), herramientas, k.kCutOperation, False)

    # 3) cara: marco en relieve, visera pasante, rejilla de boca y remaches
    z_frente = ADELANTE + PROFUNDO / 2
    plano_cara = comp.WorkPlanes.AddByPlaneAndOffset(comp.WorkPlanes.Item(3), cm(z_frente))
    plano_cara.Visible = False

    def rect_centro(sk, ancho, alto, cy):
        sk.SketchLines.AddAsTwoPointRectangle(tg.CreatePoint2d(cm(-ancho / 2), cm(cy - alto / 2)),
                                              tg.CreatePoint2d(cm(ancho / 2), cm(cy + alto / 2)))

    def en_cara(dibujar, largo, direccion, operacion):
        sk = comp.Sketches.Add(plano_cara)
        dibujar(sk)
        return comp.Features.ExtrudeFeatures.AddByDistanceExtent(sk.Profiles.AddForSolid(), cm(largo), direccion, operacion)

    def marco(sk):
        rect_centro(sk, *MARCO_EXTERIOR, VENTANA_CENTRO_Y)
        rect_centro(sk, *MARCO_INTERIOR, VENTANA_CENTRO_Y)
    en_cara(marco, MARCO_ALTO, k.kPositiveExtentDirection, k.kJoinOperation)
    en_cara(lambda sk: rect_centro(sk, *VISERA, VENTANA_CENTRO_Y), PARED + 1, k.kNegativeExtentDirection, k.kCutOperation)

    def rejilla(sk):
        for x in REJILLA_X:
            sk.SketchLines.AddAsTwoPointRectangle(tg.CreatePoint2d(cm(x - REJILLA_ANCHO / 2), cm(REJILLA_Y[0])),
                                                  tg.CreatePoint2d(cm(x + REJILLA_ANCHO / 2), cm(REJILLA_Y[1])))
    en_cara(rejilla, REJILLA_FONDO, k.kNegativeExtentDirection, k.kCutOperation)

    def remaches(sk):
        for x, y in REMACHES:
            sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(cm(x), cm(y)), cm(REMACHE_DIAM / 2))
    en_cara(remaches, REMACHE_ALTO, k.kPositiveExtentDirection, k.kJoinOperation)

    # 4) cuello, en la cara de abajo (el piso de la cabeza)
    plano_piso = comp.WorkPlanes.AddByPlaneAndOffset(xz, cm(-ALTO))
    plano_piso.Visible = False
    # paso del tornillo central del eje: atraviesa el piso
    sk_h = comp.Sketches.Add(plano_piso)
    sk_h.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(0, 0), cm(EJE_DIAM / 2))
    comp.Features.ExtrudeFeatures.AddByDistanceExtent(sk_h.Profiles.AddForSolid(), cm(PISO + 1),
                                                     k.kPositiveExtentDirection, k.kCutOperation)
    # rebaje con la forma del horn de 1 brazo (hacia adelante), HOLGURA_HORN por lado
    sk_p = comp.Sketches.Add(plano_piso)
    puntos = [tg.CreatePoint2d(cm(x), cm(y)) for x, y in pv.contorno_horn((0.0, 1.0), holgura=HOLGURA_HORN)]
    lineas = [sk_p.SketchLines.AddByTwoPoints(puntos[0], puntos[1])]
    for p in puntos[2:]:
        lineas.append(sk_p.SketchLines.AddByTwoPoints(lineas[-1].EndSketchPoint, p))
    sk_p.SketchLines.AddByTwoPoints(lineas[-1].EndSketchPoint, lineas[0].StartSketchPoint)
    comp.Features.ExtrudeFeatures.AddByDistanceExtent(sk_p.Profiles.AddForSolid(), cm(pv.HORN_ESPESOR + HOLGURA_HORN),
                                                     k.kPositiveExtentDirection, k.kCutOperation)
    # pilotos ciegos de los 2 tornillitos del horn (se atornilla el horn a la cabeza antes de montarla)
    sk_t = comp.Sketches.Add(plano_piso)
    for d in pv.TORNILLOS_HORN:
        sk_t.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(0, cm(d)), cm(pv.PILOTO_TORNILLO / 2))
    comp.Features.ExtrudeFeatures.AddByDistanceExtent(sk_t.Profiles.AddForSolid(), cm(PILOTO_HONDO),
                                                     k.kPositiveExtentDirection, k.kCutOperation)

    # 4b) orejas: disco en cada costado (plano YZ: x->Y, y->Z)
    yz = comp.WorkPlanes.Item(1)
    for s in (1, -1):
        afuera = k.kPositiveExtentDirection if s > 0 else k.kNegativeExtentDirection
        adentro = k.kNegativeExtentDirection if s > 0 else k.kPositiveExtentDirection
        pl = comp.WorkPlanes.AddByPlaneAndOffset(yz, cm(s * ANCHO / 2))
        pl.Visible = False
        sk = comp.Sketches.Add(pl)
        sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(cm(OREJA_Y), cm(OREJA_Z)), cm(OREJA_DIAM / 2))
        comp.Features.ExtrudeFeatures.AddByDistanceExtent(sk.Profiles.AddForSolid(), cm(OREJA_ALTO), afuera, k.kJoinOperation)
        pl2 = comp.WorkPlanes.AddByPlaneAndOffset(yz, cm(s * (ANCHO / 2 + OREJA_ALTO)))
        pl2.Visible = False
        sk = comp.Sketches.Add(pl2)
        sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(cm(OREJA_Y), cm(OREJA_Z)), cm(OREJA_REBAJE[0] / 2))
        sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(cm(OREJA_Y), cm(OREJA_Z)), cm(OREJA_BOTON / 2))
        comp.Features.ExtrudeFeatures.AddByDistanceExtent(sk.Profiles.AddForSolid(), cm(OREJA_REBAJE[1]), adentro, k.kCutOperation)

    # 5) partir en vertical: el frente se queda con z > Z_CORTE y la tapa con el resto
    xy = comp.WorkPlanes.Item(3)

    def plano_z(z):
        pl = comp.WorkPlanes.AddByPlaneAndOffset(xy, cm(z))
        pl.Visible = False
        return pl

    def extruir_en_z(z, dibujar, largo, direccion, operacion):
        sk = comp.Sketches.Add(plano_z(z))
        dibujar(sk)
        return comp.Features.ExtrudeFeatures.AddByDistanceExtent(sk.Profiles.AddForSolid(), cm(largo), direccion, operacion)

    def circulos(diam, puntos):
        return lambda sk: [sk.SketchCircles.AddByCenterRadius(tg.CreatePoint2d(cm(x), cm(y)), cm(diam / 2)) for x, y in puntos]

    def rect(x0, y0, x1, y1):
        return lambda sk: sk.SketchLines.AddAsTwoPointRectangle(tg.CreatePoint2d(cm(x0), cm(y0)), tg.CreatePoint2d(cm(x1), cm(y1)))

    x_torre = ANCHO / 2 - PARED - TORRE_DIAM / 2 + TORRE_EMPOTRADO
    y_torre = -ALTO + PISO + TORRE_DIAM / 2 - TORRE_EMPOTRADO
    torres = [(x_torre, y_torre), (-x_torre, y_torre)]
    grande = rect(-ANCHO, -2 * ALTO, ANCHO, ALTO)
    if parte == "frente":
        extruir_en_z(Z_CORTE, grande, PROFUNDO, k.kNegativeExtentDirection, k.kCutOperation)
        # pilares pegados a la pared y al piso, con agujero para M3
        extruir_en_z(Z_CORTE, circulos(TORRE_DIAM, torres), TORRE_LARGO, k.kPositiveExtentDirection, k.kJoinOperation)
        extruir_en_z(Z_CORTE, circulos(TORRE_AGUJERO, torres), TORRE_LARGO, k.kPositiveExtentDirection, k.kCutOperation)
        # lengueta bajo el techo que entra en la tapa y la centra; el nervio la une al techo del frente
        extruir_en_z(Z_CORTE, rect(-LENGUETA_ANCHO / 2, -PARED - 1.6, LENGUETA_ANCHO / 2, -PARED),
                     4.0, k.kPositiveExtentDirection, k.kJoinOperation)
        y_lengueta = -PARED - 1.6
        extruir_en_z(Z_CORTE + 4.0, rect(-LENGUETA_ANCHO / 2, y_lengueta - LENGUETA_ESPESOR, LENGUETA_ANCHO / 2, y_lengueta),
                     4.0 + LENGUETA_LARGO, k.kNegativeExtentDirection, k.kJoinOperation)
        # postes del OLED en la cara interna del frente, centrados en la visera
        z_pared = ADELANTE + PROFUNDO / 2 - PARED
        postes = [(sx * OLED_AGUJEROS[0] / 2, VENTANA_CENTRO_Y + sy * OLED_AGUJEROS[1] / 2) for sx in (1, -1) for sy in (1, -1)]
        extruir_en_z(z_pared, circulos(OLED_POSTE_DIAM, postes), OLED_POSTE_ALTO, k.kNegativeExtentDirection, k.kJoinOperation)
        extruir_en_z(z_pared - OLED_POSTE_ALTO, circulos(OLED_PILOTO, postes), OLED_PILOTO_HONDO,
                     k.kPositiveExtentDirection, k.kCutOperation)
    else:
        extruir_en_z(Z_CORTE, grande, PROFUNDO, k.kPositiveExtentDirection, k.kCutOperation)
        # bosses que llegan hasta los pilares del frente, paso M3 y asiento plano para la cabeza del tornillo
        z_atras = ADELANTE - PROFUNDO / 2
        extruir_en_z(Z_CORTE, circulos(TORRE_DIAM, torres), 5.5, k.kNegativeExtentDirection, k.kJoinOperation)
        extruir_en_z(z_atras - 1, circulos(PASO_M3, torres), PROFUNDO, k.kPositiveExtentDirection, k.kCutOperation)
        extruir_en_z(z_atras - 1, circulos(CABEZA_M3, torres), 4.0, k.kPositiveExtentDirection, k.kCutOperation)
        # paso de los 4 cables del OLED por el piso: justo encima de la fila de fichas del ESP32 y cerca del eje
        # del cuello (la cabeza gira: cuanto mas cerca del eje, menos se mueve el cable). Entra el conector
        # Dupont de 4 pines ya armado (10.2 x 2.5)
        x0, x1 = -PASO_CABLES[0] / 2, PASO_CABLES[0] / 2
        z0, z1 = z_atras + PARED + 0.6, Z_CORTE - 0.3
        sk_c = comp.Sketches.Add(plano_piso)
        sk_c.SketchLines.AddAsTwoPointRectangle(tg.CreatePoint2d(cm(x0), cm(z0)), tg.CreatePoint2d(cm(x1), cm(z1)))
        comp.Features.ExtrudeFeatures.AddByDistanceExtent(sk_c.Profiles.AddForSolid(), cm(PISO + 1),
                                                         k.kPositiveExtentDirection, k.kCutOperation)

    return guardar(doc, ruta, parte)


def guardar(doc, ruta, parte):
    comp = doc.ComponentDefinition
    doc.SaveAs(ruta, False)
    nombre = os.path.splitext(os.path.basename(ruta))[0]
    for carpeta in ("stl", "para_imprimir"):
        to.exportar_stl(doc, os.path.join(BASE, carpeta, nombre + ".stl"))
    masa = comp.MassProperties
    caja = [round((getattr(comp.RangeBox.MaxPoint, a) - getattr(comp.RangeBox.MinPoint, a)) * 10, 1) for a in "XYZ"]
    print(parte, "->", os.path.basename(ruta), "| caja:", caja, "mm | volumen:", round(masa.Volume * 1000, 1),
          "mm3 | PLA aprox:", round(masa.Volume * 1.24 * 0.75, 1), "g | cuerpos:", comp.SurfaceBodies.Count)
    return doc


def main():
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    app.Documents.CloseAll(False)      # Robot_armado.iam bloquea los .ipt de la cabeza si queda abierto
    tapa = construir(app, "tapa")
    tapa.Close(True)
    construir(app, "frente")


if __name__ == "__main__":
    main()
