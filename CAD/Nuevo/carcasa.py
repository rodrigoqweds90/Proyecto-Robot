"""SEGMENTO: CARCASAS DEL TORSO (estilo robot clasico cuadrado)
Tapas de adorno sobre el torso calado, sin tocar Torso_cuerpo:
  - Torso_pecho.ipt  : placa del ancho del torso, con rejilla, remaches y cinturon; traba la bateria por delante.
                       Arriba tiene un abultamiento que tapa la punta del reductor XL4015 (asoma del torso), con
                       las 2 luces al frente y ranuras arriba. Se engancha arriba con 2 ganchos en ranuras del
                       techo y va con 2 M3 abajo: sacando esos 2 tornillos sale y se saca la bateria.
  - Torso_espalda.ipt: placa detras del ESP32 con panel, ranuras de ventilacion y remaches. Va con los
                       2 M3 que antes trababan el ESP32 (la tapa hace de tope de la placa); muesca abajo
                       para los cables.
Coordenadas del robot (X izquierda, Y arriba, Z adelante), en mm.
"""
import os

import pythoncom
import pywintypes
from win32com.client import dynamic, gencache

import torso as to

BASE = os.path.dirname(os.path.abspath(__file__))

# --- pecho ---
PECHO_X = to.X_EXT                           # al ras de los costados del torso
PECHO_Y = (to.Y_PISO, to.Y_TECHO)
PECHO_Z = (to.Z_FRENTE, to.Z_FRENTE + 2.5)   # apoya en la cara de adelante del torso
PECHO_RADIO = to.R_EXT                       # mismas esquinas que el torso
# ganchos de arriba: van hacia atras bajo el techo y suben dentro de las ranuras (0.3 mm de juego)
GANCHO = (0.3, 1.6)                          # juego, espesor
PANEL = (25.0, 19.0, 45.0, 0.8)              # medio ancho, y0, y1, fondo
REJILLA_Y = (23.0, 27.5, 32.0)              # las de arriba quedaron bajo el abultamiento
REJILLA = (20.0, 2.5)                        # medio largo, alto (pasantes)
# abultamiento sobre la punta del XL4015: 0.4 mm de juego y pared de 2
JUEGO_XL, PARED_BULTO = 0.4, 2.0
LUCES = [(15.0, 46.0), (-15.0, 46.0)]      # en la cara de adelante del abultamiento
RANURAS_BULTO = (-12.0, -4.0, 4.0, 12.0)   # x de las ranuras de arriba (a lo largo de z)
LUZ = (3.2, 1.2, 1.6)                        # radio, alto, radio del hoyuelo
CINTURON = (30.0, 5.0, 7.5, 0.8)             # medio ancho, y0, y1, alto (los tornillos van justo arriba)
REMACHES_PECHO = [(sx * 29.5, y) for sx in (1, -1) for y in (16.0, 33.0)]
REMACHE = (1.2, 0.7)                         # radio, alto

# --- espalda ---
ESPALDA_X = to.X_EXT
ESPALDA_Y = (8.0, to.Y_TECHO)                # abajo quedan libres las fichas de los servos (bajo el piso)
ESPALDA_Z = (to.Z_ATRAS - 2.5, to.Z_ATRAS)
ESPALDA_RADIO = 5.0
TORNILLOS_ESPALDA = [(sx * to.TOPE_ESP[0], to.TOPE_ESP[1]) for sx in (1, -1)]
M3_PASO = 3.4
M3_CABEZA = (2.9, 0.9)                       # radio del asiento (boton M3 O5.7), fondo
PANEL_ESPALDA = [(22.0, 38.0, 53.0), (22.0, 14.0, 26.0)]    # medio ancho, y0, y1 (rebajes de 0.8)
RANURAS_X = (-15.0, -5.0, 5.0, 15.0)
RANURA = (1.5, 40.5, 50.5)                   # medio ancho, y0, y1 (pasantes)
MUESCA = (15.0, 11.0)                        # medio ancho, alto desde el borde de abajo
REMACHES_ESPALDA = [(sx * 29.0, y) for sx in (1, -1) for y in (12.0, 54.0)]

# --- pared de atras (variante B): PCA9685 + ESP32, pieza aparte que se atornilla al marco del torso ---
ATRAS_XI = to.X_EXT - to.PARED               # xi de cuerpo(): ancho interior del marco
ATRAS_Y1I = to.Y_TECHO - to.PARED            # y1i de cuerpo(): techo interior del marco

def pecho(app):
    p = to.Pieza(app, os.path.join(BASE, "Torso_pecho.ipt"))
    J, C = p.k.kJoinOperation, p.k.kCutOperation
    z0, z1 = PECHO_Z
    p.placa_redondeada(PECHO_X, PECHO_Y[0], PECHO_Y[1], z0, z1, PECHO_RADIO)
    p.cil_z(to.POSTES_PECHO, M3_PASO / 2, z0 - 0.1, z1 + 0.1, C)
    j, g = GANCHO
    x0, x1, gz0, gz1 = to.RANURA_GANCHO
    y_techo = to.Y_TECHO - to.PARED                 # cara de abajo del techo
    for s in (1, -1):
        a, b = sorted((s * (x0 + j), s * (x1 - j)))
        p.caja(a, b, y_techo - j - g, y_techo - j, gz0 + j, z0 + 0.01, J)          # brazo bajo el techo
        p.caja(a, b, y_techo - j - g, to.Y_TECHO - 0.3, gz0 + j, gz0 + j + g, J)  # dedo que sube en la ranura
    p.caja(-PANEL[0], PANEL[0], PANEL[1], PANEL[2], z1 - PANEL[3], z1 + 0.1, C)
    for y in REJILLA_Y:
        p.caja(-REJILLA[0], REJILLA[0], y - REJILLA[1] / 2, y + REJILLA[1] / 2, z0 - 0.1, z1 + 0.1, C)
    # abultamiento: caja hueca abierta atras sobre la punta del XL4015
    _, xy, xz = to.XL4015_ESQUINA
    ex, ey, ez = to.XL4015
    j, e = JUEGO_XL, PARED_BULTO
    frente = xz + ez + j + e
    # por fuera centrado y simetrico; por dentro el hueco cubre todo el lugar del XL4015, que va corrido hacia un
    # costado. Del otro lado queda un bolsillo abierto hacia atras (pared de e entre los dos) para no gastar
    # plastico; cerrado dejaba un hueco interno aislado en la malla.
    # (0.8 mm adentro del borde de la placa: si llega al borde, el chaflan de la cara de afuera no encuentra aristas)
    h0, h1 = to.XL4015_HUECO_X
    ancho = to.X_EXT - 0.8
    p.caja(-ancho, ancho, xy - j - e, xy + ey + j + e, z0, frente, J)
    p.caja(h0 - j, h1 + j, xy - j, xy + ey + j, z0 - 0.1, frente - e, C)
    if ancho - e > h1 + j + 2 * e:
        p.caja(h1 + j + e, ancho - e, xy - j, xy + ey + j, z0 - 0.1, frente - e, C)
    for x in RANURAS_BULTO:
        p.caja(x - 1.0, x + 1.0, xy + ey + j - 0.1, xy + ey + j + e + 0.1, z0 + 0.5, frente - e - 0.5, C)
    p.cil_z(LUCES, LUZ[0], frente - 0.01, frente + LUZ[1], J)
    p.cil_z(LUCES, LUZ[2], frente + LUZ[1] - 0.5, frente + LUZ[1] + 0.1, C)
    p.caja(-CINTURON[0], CINTURON[0], CINTURON[1], CINTURON[2], z1 - 0.01, z1 + CINTURON[3], J)
    p.cil_z(REMACHES_PECHO, REMACHE[0], z1 - 0.01, z1 + REMACHE[1], J)
    # estetica: chaflan del borde de la placa (la cara de afuera, la mas visible del robot)
    n = p.chaflan_borde(z1, 1.0, eje="z")
    print(f"pecho: chaflan en {n} aristas")
    return p


def espalda(app):
    p = to.Pieza(app, os.path.join(BASE, "Torso_espalda.ipt"))
    J, C = p.k.kJoinOperation, p.k.kCutOperation
    z0, z1 = ESPALDA_Z                        # z0 es la cara de afuera
    p.placa_redondeada(ESPALDA_X, ESPALDA_Y[0], ESPALDA_Y[1], z0, z1, ESPALDA_RADIO)
    p.cil_z(TORNILLOS_ESPALDA, M3_PASO / 2, z0 - 0.1, z1 + 0.1, C)
    p.cil_z(TORNILLOS_ESPALDA, M3_CABEZA[0], z0 - 0.1, z0 + M3_CABEZA[1], C)
    for mx, y0, y1 in PANEL_ESPALDA:
        p.caja(-mx, mx, y0, y1, z0 - 0.1, z0 + 0.8, C)
    for x in RANURAS_X:
        p.caja(x - RANURA[0], x + RANURA[0], RANURA[1], RANURA[2], z0 - 0.1, z1 + 0.1, C)
    p.caja(-MUESCA[0], MUESCA[0], ESPALDA_Y[0] - 0.1, MUESCA[1], z0 - 0.1, z1 + 0.1, C)
    p.cil_z(REMACHES_ESPALDA, REMACHE[0], z0 - REMACHE[1], z0 + 0.01, J)
    return p


def atras_b(app):
    """pared de atras de la variante B (PCA9685 + ESP32), pieza aparte que se atornilla al marco del torso:
    separada porque con todo fundido la PCA9685 ya armada (con los 16 cables puestos) no bajaba por el hueco
    de arriba del torso. Lleva las mismas ventanas/postes/USB que antes iban fundidos al cuerpo, mas las guias
    del ESP32 reforzadas (las anteriores eran muy delgadas, "no agarraban nada") y 4 pasos M3 con avellanado
    para atornillarla contra los postes autorroscantes del marco (to.TORNILLOS_ATRAS_B)."""
    p = to.Pieza(app, os.path.join(BASE, "Torso_atras_B.ipt"))
    J, C = p.k.kJoinOperation, p.k.kCutOperation
    z0, z1 = to.PARED_ATRAS
    p.caja(-to.X_EXT, to.X_EXT, to.PCA_B_T[1] - 6.5, to.Y_TECHO, z0, z1, J)
    for a, b, c, d in to.VENTANAS_PARED_B:
        p.caja(a, b, c, d, z0 - 0.1, z1 + 0.1, C)
    p.cil_z(to.CONDENSADOR_XY, to.CONDENSADOR / 2 + 1.5, z0 - 0.1, z1 + 0.1, C)   # paso del condensador de la PCA
    p.cil_z(to.PCA_B_AGUJEROS, 2.3, z1 - 0.01, to.PCA_B_CARA, J)                  # postes de la PCA (adentro)
    p.cil_z(to.PCA_B_AGUJEROS, 0.8, z0 + 1.0, to.PCA_B_CARA + 0.1, C)             # tornillos de servo
    # repisa horizontal que sale de la tapa hacia atras: encima va el ESP32 recto, con los pines arriba.
    # Queda por fuera del torso, asi que no le saca espacio a los servos
    mx, ry0, ry1, rz0, rz1 = to.ESP_RECTO_REPISA
    p.caja(-mx, mx, ry0, ry1, rz0, rz1, J)      # cruza la pared, asi los 4 postes quedan sobre ella
    r, tope = to.ESP_RECTO_POSTE                                                  # postes M2 de la placa
    p.cil_y(to.ESP_RECTO_AGUJEROS, r, ry1 - 0.01, tope, J)
    p.cil_y(to.ESP_RECTO_AGUJEROS, 0.8, ry0 - 0.1, tope + 0.1, C)
    # abertura por donde cruza la placa del ESP32 (entra 7 mm al torso y el resto queda atras, sobre la repisa)
    ux0, ux1, uy0, uy1 = to.ESP_PASO
    p.caja(ux0, ux1, uy0, uy1, z0 - 0.1, z1 + 0.1, C)
    # 4 tornillos que la sujetan al marco (pasan por aca y muerden autorroscante en el marco del cuerpo)
    p.cil_z(to.TORNILLOS_ATRAS_B, M3_PASO / 2, z0 - 0.1, z1 + 0.1, C)
    p.cil_z(to.TORNILLOS_ATRAS_B, M3_CABEZA[0], z0 - 0.1, z0 + M3_CABEZA[1], C)
    return p


def main():
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    app.Documents.CloseAll(False)      # Robot_armado.iam bloquea los .ipt si queda abierto
    piezas = (("Torso_pecho", pecho),) + ((("Torso_espalda", espalda),) if to.VARIANTE == "A" else
              (("Torso_atras_B", atras_b),))
    for nombre, fabricar in piezas:
        p = fabricar(app)
        p.guardar(nombre)
        for carpeta in ("stl", "para_imprimir"):
            to.exportar_stl(p.doc, os.path.join(BASE, carpeta, nombre + ".stl"))
        p.doc.Close(True)


if __name__ == "__main__":
    main()
