"""SEGMENTO: TORSO NUEVO (ESP32 atras arriba, PCA9685 atras abajo, bateria adelante)
Se modela directo en coordenadas del robot (X izquierda, Y arriba, Z adelante), asi
entra al ensamble sin moverlo. Medidas en mm; Inventor trabaja en cm.

Estructura calada (sin tapas): marco con ventanas en paredes, techo, piso y cubierta;
queda material donde apoyan servos, rieles del ESP32, postes del PCA y la bateria.

Piezas:
  - Torso_cuerpo.ipt        : estructura con los 4 soportes de servo, rieles del ESP32,
                              postes del PCA9685 y cuna de la bateria.
  - La bateria la traba el pecho (Torso_pecho, carcasa.py), del ancho del torso: 2 ganchos arriba en ranuras
    del techo y 2 M3 abajo en postes de la cara de adelante (antes era una barra en U con 2 M3 laterales).

Uniones:
  - Pestanas de servo: M2 directo en el plastico (agujero 1.7, sin insertos).
  - Barra de bateria y topes del ESP32: M3 autorroscante (agujero 2.6); el ESP32 lo traba
    la arandela de un M3 al final de cada riel.
  - PCA9685: tornillos chicos del servo (agujero 1.6) en postes. Sus cables I2C van
    soldados en los agujeros libres de un extremo (el conector en angulo se retira).
"""
import json
import os

import pythoncom
import pywintypes
import win32com.client
from win32com.client import dynamic, gencache

BASE = os.path.dirname(os.path.abspath(__file__))
# variante del torso (variable de entorno ROBOT_VARIANTE):
#   A: PCA9685 acostada abajo atras (fichas colgando bajo el piso) y ESP32 acostado encima, tapa de espalda
#   B: PCA9685 y ESP32 parados contra una pared de atras, con los pines hacia atras (fichas afuera), sin tapa
VARIANTE = os.environ.get("ROBOT_VARIANTE", "A")
SUF = "" if VARIANTE == "A" else "_" + VARIANTE     # sufijo de los archivos (Torso_cuerpo_B.ipt, ...)

# --- caja exterior ---
X_EXT = 34.0            # ancho 68: lo manda el PCA9685 (62.2) + 0.5 de juego + pared
Y_PISO = 4.0            # apoya sobre el aro Spacer01 (y 0..4)
Y_TECHO = 57.7          # cara donde apoyan las pestanas del servo del cuello
Z_ATRAS = -26.7 if VARIANTE == "A" else -5.9   # A: el borde de atras del ESP32 queda 0.5 mm adentro; B: pared de atras
Z_FRENTE = 49.2          # bateria real de 16.68 de fondo (desde z 32) + 0.5 de juego hasta el pecho
PARED = 2.4
R_EXT = 6.0
CHAFLAN_BORDE = 1.2     # chaflan de los bordes de arriba y abajo (estetica y primera capa)
TAPA = 0.0              # sin tapas
MARCO = 5.0             # ancho de las barras que quedan alrededor de las ventanas

# --- servos (centros de agujeros de pestana, del ensamble del NX25) ---
CINTURA_Y = 9.0                     # cara de arriba de las pestanas (el cuerpo sube)
CINTURA_Z = (6.0, 33.7)
CUELLO_Z = (5.5, 33.2)
HOMBRO_Y = (17.0, 44.7)
HOMBRO_Z = 25.2
CUERPO_MEDIO = 6.3                  # medio ancho del cuerpo del MG90S + juego
CUERPO_LARGO = 23.2
INSERTO_M2 = 1.7          # sin insertos a calor: el M2 rosca directo en el PLA (con 3.2 era para inserto)
TORRETA_INSERTO = 6.5
CUBIERTA = (CINTURA_Y, CINTURA_Y + 4.0)   # sostiene la cintura y es el piso de la bateria

# --- electronica ---
PCA_Z = -13.5                       # centro; placa de -26.2 a -0.8
PCA_AGUJEROS_X = 27.94
PCA_AGUJEROS_Z = (PCA_Z - 9.525, PCA_Z + 9.525)
PCA_Y_PLACA = 15.9                  # cara de abajo de la placa (componentes hacia abajo)
ESP_Z = (-26.2, 2.0)                # la fila de pines de adelante queda justo detras del servo del cuello
ESP_Y_PLACA = (30.45, 32.05)        # abajo del modulo 27.2: pasa sobre la punta del servo de cintura (26.7)
ESP_BORDE_X = 26.0                  # placa de 52 mm centrada
BAT = (-31.0, 31.0, CUBIERTA[1] + 0.5, CUBIERTA[1] + 0.5 + 23.35 + 0.4, 32.0, 32.0 + 16.68)   # LiPo real 62 x 23.35 x 16.68, delante de los hombros (z <= 31.3)
UBEC_Y = BAT[3] + 2.9               # repisa de 2.6 mm entre bateria y reductor (con 1.2 se rompia al armar)
# reductor XL4015 acostado sobre la repisa, disipador arriba; asoma por delante del torso y lo tapa un
# abultamiento del pecho. Atras llega hasta 0.5 mm de los servos de los hombros (z 31.3)
XL4015 = (52.3, 12.0, 23.5)                 # x, y, z (acostado; medido: 52.3 x 23.5 x 12 con disipador)
# hueco real del XL4015 en el torso editado a mano por el usuario: de la pared interior del tubo (-31.6) a su pared
# derecha (22.35). El modulo va corrido hacia un costado (pegado a la izquierda), no centrado
XL4015_HUECO_X = (-31.6, 22.35)
XL4015_ESQUINA = (XL4015_HUECO_X[0] + 0.2, UBEC_Y, 31.8)
RANURAS_TECHO_Z = (36.0, 40.0, 44.0)        # ventilacion del disipador en el techo
TOPE_XL4015 = 15.15                         # alto de la pared lateral del reductor, hasta y=55.3 (la altura que
                                             # el usuario eligio a mano en su boceto de Inventor)
CANAL_CABLE = (9.0, 5.0, 9.0)               # canal en cada extremo para los cables de la bateria (ancho, alto, fondo)
# (se probaron muescas en el borde por donde sale el cable del MG90S; el usuario las saco: dejaban paredes
# muy finas junto a los insertos y el servo entra igual metiendolo con paciencia)
# el servo del cuello colgaba del techo solo por sus 2 pestanas y no agarraba nada: se le agrega un colgante
# corto (3 mm) pegado al techo a los dos costados; una cuna profunda bloqueaba la bajada del PCA9685/ESP32

# --- variante B: placas paradas contra la pared de atras (z de -5.9 a -3.5), pines hacia atras ---
# PCA9685: modelo con x->-X, y->Y, z->-Z; placa de y 0.8 a 26.2, soldaduras adelante hasta z 3.5 (servo de cintura
# en 3.9); los 16 pines (y 1.0-8.6) y la bornera V+ atraviesan la pared por ventanas
PARED_ATRAS = (-5.9, -3.5)
# la PCA subio 21.7 mm respecto del diseno anterior: abajo sus pines chocaban con el piso del tubo (y 4-6.4) y
# sus postes con los postes de tornillo de la tapa (y 7.5-14.5 y 15.5-22.5). Ahora ocupa y 22.5 a 47.9, libre
PCA_SUBE = 6.2            # adentro y abajo: sube lo justo para que sus pines libren el piso (y 4-6.4)
PCA_B_T = (29.21, 7.3 + PCA_SUBE, 1.5)       # traslacion del modelo (x->-X, y->Y, z->-Z)
PCA_B_AGUJEROS = [(sx * 27.94, y + PCA_SUBE) for sx in (1, -1) for y in (3.975, 23.025)]   # (x, y)
PCA_B_CARA = PCA_B_T[2] - 1.6                # cara de atras de la placa (componentes hacia la pared)
# condensador electrolitico de la PCA: medido por el usuario en la placa real (calibre) - O8.03, 12.9 mm de
# alto, centro a 12.5 mm del borde izquierdo (el de GND/OE/SCL/SDA/VCC/V+) y 4.93 mm del borde de arriba (el
# del terminal V+/GND a tornillo). Pasado a coordenadas del robot con la transformacion de PCA_B_T (placa
# real: X -1.91..60.33, Y -6.48..18.92, medida en el modelo PCA9685_adafruit_815.iam de Inventor)
CONDENSADOR = 8.03                            # diametro
CONDENSADOR_XY = [(18.62, 21.29 + PCA_SUBE)]
VENTANAS_PARED_B = [(-25.6, 25.6, 0.5 + PCA_SUBE, 9.1 + PCA_SUBE),     # pines de los servos
                    (-5.6, 5.7, 18.2 + PCA_SUBE, 26.5 + PCA_SUBE)]     # bornera V+
# ESP32 RECTO (sin inclinar): horizontal, saliendo derecho hacia atras sobre una repisa que sale de la tapa.
# Pines hacia arriba. Queda por detras de la pared, asi que no le quita nada al interior (donde van los servos)
ESP_RECTO_EJES = [(0.0, 0.0, -1.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0)]   # x->-Z, y->X, z->-Y
# entra lo que se puede adentro: los servos de cintura y cuello ocupan la columna del medio (x +-6) en
# z 3.3 a 35.9, y la placa mide 52 mm de ancho, asi que no puede pasarlos. Solo queda libre z < 3.3:
# ~7 mm adentro del torso y el resto hacia atras, sobre la repisa de la tapa
ESP_RECTO_T = (-23.37, 44.25, 0.56)
ESP_RECTO_CAJA = (-25.8, 26.0, 41.0, 54.5, -26.0, 3.0)    # x0,x1,y0,y1,z0,z1 en el mundo
ESP_RECTO_REPISA = (27.0, 38.9, 40.5, -25.0, 3.0)         # medio ancho, y abajo, y arriba, z atras, z adelante
ESP_RECTO_AGUJEROS = [(sx * 23.2, z) for sx in (1, -1) for z in (0.46, -23.44)]   # (x, z)
ESP_PASO = (-27.0, 27.0, 40.3, 55.0)                      # abertura de la tapa por donde cruza la placa
ESP_RECTO_POSTE = (2.5, 42.88)                            # radio y cara de arriba (donde apoya la placa)
# fichas reales: la ficha Dupont y el enchufe del servo (14 mm) se apoyan en el plastico de los pines (2.5 mm
# de la placa) y cubren los pines; detras quedan 2 mm para doblar el cable
FICHA_LARGO, PLASTICO_PINES, CURVA_CABLE = 14.0, 2.5, 2.0
FICHAS_B_Z = {"pca": PCA_B_CARA - PLASTICO_PINES}   # donde empiezan (el ESP32 ya no tiene fichas en la pared)
# 2 tornillos (no 4: el PCA y el ESP32 ocupan casi toda la cara de la tapa, x hasta +-31.1 de 31.6 de tubo,
# y en alto solo dejan libres 8.6 mm entre los dos -y 32.4 a 41-, muy poco para 4 postes con margen sano).
# El marco se rebaja 2.4 mm en todo el borde de atras (ver el rebaje mas abajo en cuerpo()) para que la pared
# quede a ras; el aro del tubo solo tiene 2.4 mm ahi, muy poco para que un autorroscante agarre solo, asi que
# cada tornillo entra en un poste (POSTE_ATRAS_B) que cuelga del aro hacia adentro y lo engrosa localmente.
# y=36.7 centra el poste en ese hueco de 8.6 mm: 1.3 mm de margen contra el borde del PCA y del ESP32
TORNILLOS_ATRAS_B = [(30.5, 36.7), (-30.5, 36.7)]
POSTE_ATRAS_B = 3.0   # radio del poste (llega justo al borde exterior del tubo, X_EXT)

# --- interruptor de la bateria (tipo KCD11), en el costado derecho de atras, sobre el ESP32 ---
# (el techo de adelante quedo para el XL4015) corte de 13 (z) x 8.5 (y) en una placa que tapa parte de la
# ventana; el cuerpo entra 15 mm entre las dos filas de fichas del ESP32
INTERRUPTOR = (41.0, 49.5, -20.0, -7.0) if VARIANTE == "A" else (40.0, 48.5, 4.5, 17.5)   # y0, y1, z0, z1 del corte
INTERRUPTOR_PLACA = (38.5, 50.0, -23.0, -4.0) if VARIANTE == "A" else (37.5, 51.0, 2.0, 18.5)   # B: delante del ESP32

# --- aro espaciador (Spacer01 original del NX25, con M2: pasante 2.5 y rebaje 4.5 para la cabeza) ---
ESPACIADOR_AGUJERO = 1.7   # M2x8 desde abajo, rosca directo en el poste del piso
ESPACIADOR_MEDIO = 18.0
ESPACIADOR_Z = (7.2, 43.2)
TORNILLOS_ESPACIADOR = [(12.5, 32.2), (-12.5, 32.2), (10.0, 15.2), (-10.0, 15.2)]   # (x, z)

# --- tornillos M3 y topes del ESP32 ---
M3_AUTORROSCA = 2.6
M3_PASO = 3.4
BARRA_Y = (16.0, 26.0)                      # abajo de la ventana del costado de la bateria
# pecho: 2 postes abajo (bajo la bateria) y 2 ranuras en el techo para sus ganchos
POSTES_PECHO = [(sx * 12.5, 10.5) for sx in (1, -1)]
POSTE_PECHO = (2.8, 11.0)                   # radio, largo hacia atras desde la cara de adelante
RANURA_GANCHO = (19.5, 24.0, 44.0, 46.0)    # x0, x1 (y espejo), z0, z1: pasante en el techo
TOPE_ESP = (30.0, 31.3)                     # (x, y) del tornillo con arandela al final de cada riel

# --- refuerzo del piso de atras ---
# el calculo de esfuerzos marco el borde de las tiras del piso junto al PCA (x 25.5, atras) cuando el cuello o
# un hombro hacen fuerza: nervio de 3 mm bajo cada tira, por fuera de las fichas de los servos (x 25.4)
NERVIO_PISO = (26.0, X_EXT, Y_PISO - 3.0, -0.5)   # x0, x1, y de abajo, z de adelante (atras llega a Z_ATRAS)

# --- giroscopio MPU6050 (placa GY-521, 21.2 x 16.4) sobre la cubierta, al lado del servo de cintura ---
# placa horizontal a 3 mm de la cubierta; tira de pines en el borde de atras (mirando al ESP32), agujeros de
# O3 en el borde de adelante (M3 autorroscante en dos postes) y dos apoyos bajo el borde de los pines
IMU_PLACA = (7.0, 28.2, 4.0, 20.4)          # x0, x1, z0, z1
IMU_Y = CUBIERTA[1] + 3.0                   # cara de abajo de la placa
IMU_AGUJEROS = [(17.6 - 7.62, 17.9), (17.6 + 7.62, 17.9)]   # (x, z)
IMU_APOYOS = [(12.0, 7.0), (24.0, 7.0)]


def dyn(o):
    return dynamic.Dispatch(o._oleobj_) if hasattr(o, "_oleobj_") else o


class Pieza:
    def __init__(self, app, ruta):
        self.app, self.ruta = app, ruta
        self.k = win32com.client.constants
        self.tg = app.TransientGeometry
        for i in range(app.Documents.Count, 0, -1):
            d = dyn(app.Documents.Item(i))
            if os.path.normcase(d.FullFileName) == os.path.normcase(ruta):
                d.Close(True)
        self.doc = dyn(app.Documents.Add(self.k.kPartDocumentObject,
                                         app.FileManager.GetTemplateFile(self.k.kPartDocumentObject, self.k.kMetricSystemOfMeasure), True))
        self.cd = self.doc.ComponentDefinition

    def _plano(self, indice, offset):
        pl = self.cd.WorkPlanes.AddByPlaneAndOffset(self.cd.WorkPlanes.Item(indice), offset / 10)
        pl.Visible = False
        return pl

    def _extruir(self, sk, largo, op):
        return self.cd.Features.ExtrudeFeatures.AddByDistanceExtent(sk.Profiles.AddForSolid(), largo / 10,
                                                                   self.k.kPositiveExtentDirection, op)

    def caja(self, x0, x1, y0, y1, z0, z1, op):
        sk = self.cd.Sketches.Add(self._plano(3, z0))           # plano XY: x->X, y->Y, normal +Z
        sk.SketchLines.AddAsTwoPointRectangle(self.tg.CreatePoint2d(x0 / 10, y0 / 10), self.tg.CreatePoint2d(x1 / 10, y1 / 10))
        return self._extruir(sk, z1 - z0, op)

    def cil_y(self, puntos_xz, r, y0, y1, op):
        sk = self.cd.Sketches.Add(self._plano(2, y0))           # plano XZ: x->-X, y->Z, normal +Y
        for x, z in puntos_xz:
            sk.SketchCircles.AddByCenterRadius(self.tg.CreatePoint2d(-x / 10, z / 10), r / 10)
        return self._extruir(sk, y1 - y0, op)

    def cil_x(self, puntos_yz, r, x0, x1, op):
        sk = self.cd.Sketches.Add(self._plano(1, x0))           # plano YZ: x->Y, y->Z, normal +X
        for y, z in puntos_yz:
            sk.SketchCircles.AddByCenterRadius(self.tg.CreatePoint2d(y / 10, z / 10), r / 10)
        return self._extruir(sk, x1 - x0, op)

    def cil_z(self, puntos_xy, r, z0, z1, op):
        sk = self.cd.Sketches.Add(self._plano(3, z0))
        for x, y in puntos_xy:
            sk.SketchCircles.AddByCenterRadius(self.tg.CreatePoint2d(x / 10, y / 10), r / 10)
        return self._extruir(sk, z1 - z0, op)

    def redondear_aristas_z(self, cuerpo, radio):
        col = self.app.TransientObjects.CreateEdgeCollection()
        for j in range(1, cuerpo.Edges.Count + 1):
            e = cuerpo.Edges.Item(j)
            if e.GeometryType == self.k.kLineSegmentCurve and abs(abs(e.Geometry.Direction.Z) - 1) < 1e-6:
                col.Add(e)
        defi = dyn(self.cd.Features.FilletFeatures.CreateFilletDefinition())
        defi.AddConstantRadiusEdgeSet(col, radio / 10)
        self.cd.Features.FilletFeatures.Add(defi)

    def chaflan_borde(self, coord, ancho, eje="y"):
        """chaflan en el lazo exterior (el contorno de afuera, sin ventanas ni agujeros) de la cara PLANA
        perpendicular a 'eje' que esta en la posicion 'coord' (mm). Se ubica la cara por su altura en ese
        eje y se usa IsOuterEdgeLoop: mucho mas confiable que comparar posiciones de arista a mano, y sirve
        igual para el techo/piso del torso (eje y) que para la cara de afuera de una placa (eje z, x)."""
        idx = "xyz".index(eje)
        cuerpo = self.cd.SurfaceBodies.Item(1)
        for j in range(1, cuerpo.Faces.Count + 1):
            f = cuerpo.Faces.Item(j)
            caja = f.Evaluator.RangeBox
            mn, mx = (caja.MinPoint.X, caja.MaxPoint.X) if idx == 0 else                      (caja.MinPoint.Y, caja.MaxPoint.Y) if idx == 1 else (caja.MinPoint.Z, caja.MaxPoint.Z)
            if abs(mn - coord / 10) > 0.005 or abs(mx - coord / 10) > 0.005:
                continue
            lazo = next((dyn(f.EdgeLoops.Item(i)) for i in range(1, f.EdgeLoops.Count + 1)
                        if dyn(f.EdgeLoops.Item(i)).IsOuterEdgeLoop), None)
            if lazo is None:
                continue
            col = self.app.TransientObjects.CreateEdgeCollection()
            for i in range(1, lazo.Edges.Count + 1):
                col.Add(lazo.Edges.Item(i))
            try:
                self.cd.Features.ChamferFeatures.AddUsingDistance(col, ancho / 10)
                return col.Count
            except Exception:
                return 0   # el lazo exterior cambio de forma (ej. una abertura vecina) y el chaflan no entra
        return 0

    def placa_redondeada(self, x, y0, y1, z0, z1, radio):
        self.caja(-x, x, y0, y1, z0, z1, self.k.kJoinOperation)
        self.redondear_aristas_z(self.cd.SurfaceBodies.Item(1), radio)

    def guardar(self, nombre):
        self.doc.SaveAs(self.ruta, False)
        vol = self.cd.MassProperties.Volume * 1000
        print(f"{nombre}: volumen {vol:.0f} mm3 | PLA aprox {vol / 1000 * 1.24 * 0.75:.1f} g | cuerpos {self.cd.SurfaceBodies.Count}")


def chaflan_borde_libre(app, cd, coord, ancho, eje="y", cuerpo_idx=1):
    """version de chaflan_borde() que no depende de la clase Pieza: sirve para scripts que arman el solido
    a mano con la API cruda (cabeza.py, pelvis.py, mano.py). Mismo criterio: IsOuterEdgeLoop de la cara
    plana perpendicular a 'eje' en la posicion 'coord' (mm)."""
    idx = "xyz".index(eje)
    cuerpo = cd.SurfaceBodies.Item(cuerpo_idx)
    for j in range(1, cuerpo.Faces.Count + 1):
        f = cuerpo.Faces.Item(j)
        caja = f.Evaluator.RangeBox
        mn, mx = (caja.MinPoint.X, caja.MaxPoint.X) if idx == 0 else                  (caja.MinPoint.Y, caja.MaxPoint.Y) if idx == 1 else (caja.MinPoint.Z, caja.MaxPoint.Z)
        if abs(mn - coord / 10) > 0.005 or abs(mx - coord / 10) > 0.005:
            continue
        lazo = next((dynamic.Dispatch(f.EdgeLoops.Item(i)._oleobj_) for i in range(1, f.EdgeLoops.Count + 1)
                    if dynamic.Dispatch(f.EdgeLoops.Item(i)._oleobj_).IsOuterEdgeLoop), None)
        if lazo is None:
            continue
        col = app.TransientObjects.CreateEdgeCollection()
        for i in range(1, lazo.Edges.Count + 1):
            col.Add(lazo.Edges.Item(i))
        cd.Features.ChamferFeatures.AddUsingDistance(col, ancho / 10)
        return col.Count
    return 0


def exportar_stl(doc, ruta):
    """STL en resolucion alta. doc.SaveAs(.stl) usa la resolucion que quedo guardada en Inventor (una
    'personalizada' gruesa): circulos de pocos lados, agujeros y encastres mas chicos, y mallas abiertas."""
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    tr = next(dyn(app.ApplicationAddIns.Item(i)) for i in range(1, app.ApplicationAddIns.Count + 1)
              if dyn(app.ApplicationAddIns.Item(i)).ClassIdString == "{533E9A98-FC3B-11D4-8E7E-0010B541CD80}")
    ctx = app.TransientObjects.CreateTranslationContext()
    ctx.Type = 13059                    # kFileBrowseIOMechanism
    opciones = app.TransientObjects.CreateNameValueMap()
    tr.HasSaveCopyAsOptions(doc, ctx, opciones)
    opciones.Remove("Resolution")
    opciones.Add("Resolution", 0)       # alta
    medio = app.TransientObjects.CreateDataMedium()
    medio.FileName = ruta
    tr.SaveCopyAs(doc, ctx, opciones, medio)


def cuerpo(app):
    p = Pieza(app, os.path.join(BASE, "Torso_cuerpo" + SUF + ".ipt"))
    k = p.k
    J, C = k.kJoinOperation, k.kCutOperation
    xi, y0i, y1i = X_EXT - PARED, Y_PISO + PARED, Y_TECHO - PARED
    zi_atras, zi_frente = Z_ATRAS + TAPA, Z_FRENTE - TAPA

    # 1) tubo: exterior redondeado menos interior redondeado
    p.placa_redondeada(X_EXT, Y_PISO, Y_TECHO, Z_ATRAS, Z_FRENTE, R_EXT)
    p.caja(-xi, xi, y0i, y1i, Z_ATRAS - 1, Z_FRENTE + 1, k.kNewBodyOperation)
    p.redondear_aristas_z(p.cd.SurfaceBodies.Item(2), R_EXT - PARED)
    herr = app.TransientObjects.CreateObjectCollection()
    herr.Add(p.cd.SurfaceBodies.Item(2))
    p.cd.Features.CombineFeatures.Add(p.cd.SurfaceBodies.Item(1), herr, C, False)

    # 2) cubierta: las pestanas de la cintura apoyan desde abajo en y = 9; encima va la bateria
    p.caja(-xi, xi, CUBIERTA[0], CUBIERTA[1], ESP_Z[1] if VARIANTE == "A" else PCA_B_T[2] + 2.1, zi_frente, J)

    # 3) torretas: cuello (bajo el techo), hombros (en las paredes), tapas
    p.cil_y([(0, z) for z in CUELLO_Z], TORRETA_INSERTO / 2, y1i - 2.9, y1i + 0.5, J)   # 2.9: mas abajo
    # tocaba el XL4015, que subio con la repisa nueva; quedan 5.3 mm de material para el inserto M2
    p.cil_x([(y, HOMBRO_Z) for y in HOMBRO_Y], TORRETA_INSERTO / 2, xi - 5.0, xi + 0.5, J)
    p.cil_x([(y, HOMBRO_Z) for y in HOMBRO_Y], TORRETA_INSERTO / 2, -xi - 0.5, -xi + 5.0, J)

    # 4) ESP32: rieles en los extremos cortos de la placa, entra desde atras con los pines arriba
    riel_y = (ESP_Y_PLACA[0] - 1.7, ESP_Y_PLACA[1] + 1.8)
    esp_centro_z = sum(ESP_Z) / 2
    for s in ((1, -1) if VARIANTE == "A" else ()):
        a, b = sorted((s * (ESP_BORDE_X - 0.7), s * xi))
        p.caja(a, b, riel_y[0], riel_y[1], zi_atras, ESP_Z[1] + 0.5, J)
    for s in ((1, -1) if VARIANTE == "A" else ()):
        a, b = sorted((s * (ESP_BORDE_X - 0.7), s * (ESP_BORDE_X + 0.5)))
        p.caja(a, b, ESP_Y_PLACA[0] - 0.2, ESP_Y_PLACA[1] + 0.3, Z_ATRAS, ESP_Z[1] + 1.0, C)   # ranura de la placa
        p.caja(a, b, riel_y[0] - 0.3, ESP_Y_PLACA[0], esp_centro_z - 9.6, esp_centro_z + 9.6, C)  # libre: modulo y USB

    # 5) PCA9685: postes desde el piso hasta la placa
    postes = [(sx * PCA_AGUJEROS_X, z) for sx in (1, -1) for z in PCA_AGUJEROS_Z]
    if VARIANTE == "A":
        p.cil_y(postes, 2.5, y0i - 0.5, PCA_Y_PLACA, J)

    # 6) bateria: topes atras (bajo los hombros) y repisa encima para el UBEC
    for s in (1, -1):
        a, b = sorted((s * 8.0, s * xi))
        p.caja(a, b, CUBIERTA[1] - 0.1, CUBIERTA[1] + 1.8, BAT[4] - 1.4, BAT[4] - 0.1, J)
    # la repisa NO llega hasta el costado izquierdo: termina donde termina el XL4015, asi el pedazo que sobra
    # (x de 26.55 a 31.6) queda vacio de arriba a abajo, sin repisa ni pared, y por ahi sube el cable de la LiPo
    p.caja(-xi, XL4015[0] / 2 + 0.4, BAT[3] + 0.2, UBEC_Y - 0.1, BAT[4] - 0.1, zi_frente, J)
    # tope del XL4015: una sola pared maciza, pegada al tubo del lado derecho del robot, tocando el XL4015
    # (0.4 mm de juego); el lado izquierdo es el hueco libre que se acaba de describir
    p.caja(-xi, -(XL4015[0] / 2 + 0.4), UBEC_Y - 0.1, UBEC_Y + TOPE_XL4015, XL4015_ESQUINA[2] - 0.5, Z_FRENTE, J)
    # canal para los cables de la LiPo: antes iba a los dos extremos, pero del lado derecho (x negativo) le
    # cortaba la conexion a la pared del XL4015 con el tubo, dejandola flotando en ese tramo. Ahora va solo
    # del lado izquierdo (abierto, sin pared: es ademas por donde ya sube el cable del XL4015)
    a, b = sorted((xi - CANAL_CABLE[0], xi + 0.5))
    p.caja(a, b, BAT[3] - CANAL_CABLE[1], UBEC_Y + 0.1, BAT[4] - 0.5, BAT[4] + CANAL_CABLE[2], C)

    # agarre del servo del cuello: un colgante CORTO pegado al techo (no una cuna profunda, que bloqueaba la
    # bajada del PCA9685/ESP32 por el hueco de arriba del torso). Solo 3 mm de alto, a los dos costados.
    esp, alto_cuna = 2.0, 3.0
    cuello_z = (sum(CUELLO_Z) / 2 - CUERPO_LARGO / 2, sum(CUELLO_Z) / 2 + CUERPO_LARGO / 2)
    for s_ in (1, -1):
        a, b = sorted((s_ * (CUERPO_MEDIO + 0.1), s_ * (CUERPO_MEDIO + 0.1 + esp)))
        p.caja(a, b, y1i - alto_cuna, y1i + 0.1, cuello_z[0], cuello_z[1], J)

    # 7) cortes de los servos
    p.caja(-CUERPO_MEDIO, CUERPO_MEDIO, CINTURA_Y - 0.1, CUBIERTA[1] + 0.5,
           sum(CINTURA_Z) / 2 - CUERPO_LARGO / 2, sum(CINTURA_Z) / 2 + CUERPO_LARGO / 2, C)
    p.caja(-7.5, 7.5, Y_PISO - 0.5, y0i + 0.5, CINTURA_Z[0] - 3.0, CINTURA_Z[1] + 3.0, C)      # piso: pasa la punta del servo
    # a diferencia de cuello/hombro (insertos en la pared del tubo, con espacio de sobra) el inserto de la
    # cintura queda pegado al cuerpo real del servo: cualquier torreta de refuerzo que se probo (hasta un
    # radio de solo 1.7 mm, apenas 0.1 mm mas que el agujero) choca contra la malla real del MG90S. Queda
    # sin torreta, tal como estaba.
    p.cil_y([(0, z) for z in CINTURA_Z], INSERTO_M2 / 2, CINTURA_Y - 0.1, CINTURA_Y + 3.5, C)
    p.caja(-CUERPO_MEDIO, CUERPO_MEDIO, y1i - 5.0, Y_TECHO + 0.1,
           sum(CUELLO_Z) / 2 - CUERPO_LARGO / 2, sum(CUELLO_Z) / 2 + CUERPO_LARGO / 2, C)
    p.cil_y([(0, z) for z in CUELLO_Z], INSERTO_M2 / 2, Y_TECHO - 5.0, Y_TECHO + 0.1, C)
    for s in (1, -1):
        a, b = sorted((s * (xi - 5.5), s * (X_EXT + 0.1)))
        p.caja(a, b, sum(HOMBRO_Y) / 2 - CUERPO_LARGO / 2, sum(HOMBRO_Y) / 2 + CUERPO_LARGO / 2,
               HOMBRO_Z - CUERPO_MEDIO, HOMBRO_Z + CUERPO_MEDIO, C)
        a, b = sorted((s * (X_EXT - 6.0), s * (X_EXT + 0.1)))
        p.cil_x([(y, HOMBRO_Z) for y in HOMBRO_Y], INSERTO_M2 / 2, a, b, C)

    # 8) agujeros del PCA y topes del ESP32 (M3 con arandela al final de cada riel)
    if VARIANTE == "A":
        p.cil_y(postes, 0.8, PCA_Y_PLACA - 6.0, PCA_Y_PLACA + 0.1, C)
        p.cil_z([(sx * TOPE_ESP[0], TOPE_ESP[1]) for sx in (1, -1)], M3_AUTORROSCA / 2, Z_ATRAS - 0.1, Z_ATRAS + 7.0, C)

    # 9) conexiones y aligerado
    if VARIANTE == "A":
        # USB del ESP32 por el costado izquierdo
        p.caja(ESP_BORDE_X - 0.6, X_EXT + 0.5, ESP_Y_PLACA[0] - 4.5, ESP_Y_PLACA[1] + 3.0, esp_centro_z - 6.0, esp_centro_z + 6.0, C)
        # piso bajo el PCA: fichas de los servos (miran abajo), bornera V+ y conector I2C del extremo
        p.caja(-25.5, 25.5, Y_PISO - 0.5, y0i + 0.5, zi_atras + 0.01, -0.5, C)
        # techo sobre el ESP32: se enchufan los Dupont en los pines y suben los cables a cabeza y brazos
        p.caja(-24.0, 24.0, y1i - 0.5, Y_TECHO + 0.5, ESP_Z[0] + 2.0, ESP_Z[1] - 2.5, C)
    else:
        # la pared de atras (PCA9685, ESP32, protector) es una pieza aparte (Torso_atras_B, carcasa.py) que se
        # atornilla aqui: el usuario la pidio separada porque con todo fundido no entraba el PCA armado.
        # el marco se rebaja PARED_ATRAS (2.4 mm) en todo el borde de atras para que la pared quede a ras del
        # tubo (si no, la pared y el aro del tubo ocupan el mismo lugar); los 4 tornillos entran por ese
        # rebaje y muerden autorroscante en el tubo macizo que sigue justo adelante
        z0, z1 = PARED_ATRAS
        p.caja(-X_EXT - 1, X_EXT + 1, Y_PISO - 1, Y_TECHO + 1, z0, z1, C)
        alto = 6.0
        p.cil_z(TORNILLOS_ATRAS_B, POSTE_ATRAS_B, z1 - 0.01, z1 + alto, J)      # poste (engrosa el aro, delgado)
        p.cil_z(TORNILLOS_ATRAS_B, M3_AUTORROSCA / 2, z1 - 0.1, z1 + alto, C)   # piloto autorroscante
    # estructura calada: ventanas en las paredes, dejando la columna de los hombros, la banda
    # de los rieles del ESP32 y los postes de adelante y de atras
    col_hombro = (HOMBRO_Z - 11.2, HOMBRO_Z + 8.8)            # z 14 .. 34
    riel_banda = (riel_y[0] - 2.25, riel_y[1] + 2.15)          # y 26.5 .. 36
    for s in (1, -1):
        a, b = sorted((s * (xi - 0.5), s * (X_EXT + 0.5)))
        if VARIANTE == "A":   # en B la parte de atras es corta: sin ventanas, el costado rigidiza los hombros
            p.caja(a, b, CUBIERTA[0], riel_banda[0], Z_ATRAS + MARCO, col_hombro[0], C)    # atras abajo (PCA)
            p.caja(a, b, riel_banda[1], Y_TECHO - MARCO, Z_ATRAS + MARCO, col_hombro[0], C)  # atras arriba
        p.caja(a, b, BARRA_Y[0], Y_TECHO - MARCO, col_hombro[1], Z_FRENTE - MARCO, C)    # adelante (bateria)
    # techo: a los lados del soporte del cuello
    for s in (1, -1):
        a, b = sorted((s * 10.0, s * 27.0))
        p.caja(a, b, y1i - 0.5, Y_TECHO + 0.5, ESP_Z[1] + 1.0, col_hombro[1] - 2.0, C)
    # piso de adelante: la que carga es la cubierta de la cintura; se deja el cuadrado donde
    # se atornilla el aro espaciador (Spacer01, gira con el torso sobre la pelvis)
    for s in (1, -1):
        a, b = sorted((s * (ESPACIADOR_MEDIO + 0.5), s * 28.0))
        p.caja(a, b, Y_PISO - 0.5, y0i + 0.5, 1.0, Z_FRENTE - MARCO, C)
    p.caja(-ESPACIADOR_MEDIO - 0.5, ESPACIADOR_MEDIO + 0.5, Y_PISO - 0.5, y0i + 0.5, 1.0, ESPACIADOR_Z[0] - 0.5, C)
    # cubierta bajo la bateria: la bateria apoya en el centro y en los bordes
    for s in (1, -1):
        a, b = sorted((s * 9.0, s * 27.0))
        p.caja(a, b, CUBIERTA[0] - 0.5, CUBIERTA[1] + 0.5, BAT[4] + 6.0, BAT[5] - 3.0, C)
    # postes del pecho (M3 desde adelante) y ranuras de sus ganchos en el techo
    p.cil_z(POSTES_PECHO, POSTE_PECHO[0], Z_FRENTE - POSTE_PECHO[1], Z_FRENTE, J)
    p.cil_z(POSTES_PECHO, M3_AUTORROSCA / 2, Z_FRENTE - POSTE_PECHO[1] + 0.5, Z_FRENTE + 0.1, C)
    for s in (1, -1):
        a, b = sorted((s * RANURA_GANCHO[0], s * RANURA_GANCHO[1]))
        p.caja(a, b, y1i - 0.5, Y_TECHO + 0.5, RANURA_GANCHO[2], RANURA_GANCHO[3], C)
    if VARIANTE != "A":
        # las fichas Dupont de la fila de adelante del ESP32 suben por el borde de atras del techo
        p.caja(-19.8, 19.8, y1i - 0.3, Y_TECHO + 0.2, Z_ATRAS + 2.3, 1.8, C)
    # (en el torso editado a mano hay ademas una muesca en la pared del XL4015 del usuario, x 22.2-25,
    # y 53.1-55.25, z 44-49.3, para que pase el gancho derecho del pecho; esa pared no esta en este codigo)
    # interruptor de la bateria
    p.caja(-X_EXT, -xi - 0.01, INTERRUPTOR_PLACA[0], INTERRUPTOR_PLACA[1], INTERRUPTOR_PLACA[2], INTERRUPTOR_PLACA[3], J)
    p.caja(-X_EXT - 0.5, -xi + 0.5, INTERRUPTOR[0], INTERRUPTOR[1], INTERRUPTOR[2], INTERRUPTOR[3], C)
    # ranuras en el techo sobre el disipador del XL4015
    for z in RANURAS_TECHO_Z:
        p.caja(-18.0, 18.0, y1i - 0.5, Y_TECHO + 0.5, z, z + 2.0, C)
    # torretas M3 del aro espaciador: del piso a la cubierta, tornillo desde abajo
    p.cil_y(TORNILLOS_ESPACIADOR, 3.0, Y_PISO + 0.5, CINTURA_Y + 0.1, J)
    p.cil_y(TORNILLOS_ESPACIADOR, ESPACIADOR_AGUJERO / 2, Y_PISO - 0.1, CINTURA_Y + 2.5, C)
    # nervio bajo las tiras del piso de atras (refuerzo)
    for s in ((1, -1) if VARIANTE == "A" else ()):
        a, b = sorted((s * NERVIO_PISO[0], s * NERVIO_PISO[1]))
        p.caja(a, b, NERVIO_PISO[2], Y_PISO + 0.5, Z_ATRAS, NERVIO_PISO[3], J)
    # giroscopio: postes con agujero M3 y apoyos
    p.cil_y(IMU_AGUJEROS, 3.0, CUBIERTA[1] - 0.1, IMU_Y, J)
    p.cil_y(IMU_APOYOS, 2.0, CUBIERTA[1] - 0.1, IMU_Y, J)
    p.cil_y(IMU_AGUJEROS, M3_AUTORROSCA / 2, CUBIERTA[1] - 2.5, IMU_Y + 0.1, C)
    # estetica: chaflan en el borde de arriba y en el de abajo. Quita material (no suma peso) y de paso
    # el de abajo evita la "pata de elefante" de la primera capa
    n1 = p.chaflan_borde(Y_TECHO, CHAFLAN_BORDE)
    n2 = p.chaflan_borde(Y_PISO, CHAFLAN_BORDE)
    print(f"chaflanes: {n1} aristas arriba, {n2} abajo")
    p.guardar("Torso_cuerpo" + SUF)
    cm = p.cd.MassProperties.CenterOfMass
    with open(os.path.join(BASE, f"torso_masas{SUF}.json"), "w", encoding="utf-8") as f:
        json.dump({f"Torso_cuerpo{SUF}.ipt": [p.cd.MassProperties.Volume * 1.24 * 0.75, [cm.X * 10, cm.Y * 10, cm.Z * 10]]}, f, indent=1)
    return p


def main():
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    app.Documents.CloseAll(False)      # el ensamble de estudio bloquea los .ipt si queda abierto
    p = cuerpo(app)
    for carpeta, ext in (("stl", ".stl"), ("para_imprimir", ".stl"), ("step", ".stp")):
        if VARIANTE == "A" or carpeta != "para_imprimir":
            ruta = os.path.join(BASE, carpeta, "Torso_cuerpo" + SUF + ext)
            exportar_stl(p.doc, ruta) if ext == ".stl" else p.doc.SaveAs(ruta, True)


if __name__ == "__main__":
    main()
