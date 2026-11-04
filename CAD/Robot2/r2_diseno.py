"""ROBOT 2 - REDISENO COMPLETO (v1: arquitectura)
Mismos 16 servos y articulaciones que el NX25 actual (piernas de 4 con paralelogramos en muslo y canilla,
brazos de 3, cintura y cuello), forma nueva pensada para pelear: centro de masa bajo y centrado, caderas mas
separadas, pies grandes, cada servo en una caja cerrada y articulaciones sostenidas por los dos lados.

Cada pieza es una lista de primitivas (caja / cilindro, sumar o restar) en coordenadas del robot parado:
X a la izquierda del robot, Y arriba, Z adelante, mm; origen en el eje de la cintura, y = 0 en la cara de
arriba de la pelvis. De la misma lista salen la malla (peso, centro de masa, choques: r2_revisar.py) y las
piezas nativas de Inventor (r2_inventor.py).
"""
import os

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
COMPONENTES = os.path.join(BASE, "..", "Componentes")

# =====================================================================
# SEGMENTO: COMPONENTES (medidas de fichas y del usuario; masas en g)
# =====================================================================
# MG90S (modelo de GrabCAD medido): cuerpo x +-11.4, y -0.7..22.5, z +-6.1; pestanas y 17..19.5, x +-16;
# eje en x -5.5, punta en y 31.5. MG92B (caderas, medido con calibre): 21.21 mm bajo las pestanas (MG90S 17.7)
BAJO_MG90S, BAJO_MG92B = 17.7, 21.21
MASAS = {  # g. Servos: fichas TowerPro. El resto son estimaciones a confirmar con balanza
    "MG90S": 13.4, "MG92B": 13.8, "bateria": 60.0, "PCA9685": 9.0, "ESP32": 10.0, "XL4015": 20.0,
    "IMU": 2.0, "OLED": 3.0, "interruptor": 2.0, "cables_y_tornillos": 30.0,
}
DENSIDAD_PLA = 1.24          # g/cm3
RELLENO = 0.7                # fraccion maciza efectiva (3 paredes + 15 % de relleno en piezas de pared gruesa)

PARED = 2.5                  # pared de las cajas de servo
JUEGO = 0.4                  # juego del cuerpo del servo en su caja
PLACA = 3.0                  # placas de horquillas y orejas
PERNO_R = 3.15               # agujero del perno (Pipe_M3 O6 + 0.15)


# =====================================================================
# SEGMENTO: MARCO DE CADA SERVO
# =====================================================================
def marco_servo(eje_punto, eje_dir, cuerpo_dir, punta=None):
    """matriz 4x4 local->robot de un servo. eje_punto: un punto del eje de salida (si punta, es la punta del
    eje); eje_dir: hacia donde sale el eje; cuerpo_dir: del eje hacia el centro del cuerpo (largo del servo)."""
    d = np.asarray(eje_dir, float)
    b = np.asarray(cuerpo_dir, float)
    z = np.cross(b, d)
    M = np.eye(4)
    M[:3, 0], M[:3, 1], M[:3, 2] = b, d, z
    p = np.asarray(eje_punto, float)
    # en el servo el eje esta en (x -5.5, z 0); la punta en y 31.5
    o = p - (-5.5) * b - (31.5 if punta is None else punta) * d
    M[:3, 3] = o
    return M


def a_robot(M, puntos):
    puntos = np.atleast_2d(np.asarray(puntos, float))
    return puntos @ M[:3, :3].T + M[:3, 3]


def caja_local(M, x0, x1, y0, y1, z0, z1):
    """caja en coords del servo -> caja alineada del robot (los ejes del servo son siempre +-X/Y/Z)"""
    esq = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)])
    w = a_robot(M, esq)
    lo, hi = w.min(0), w.max(0)
    return ("caja", (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))


def cil_local(M, x, z, r, y0, y1):
    """cilindro a lo largo del eje y del servo, centrado en (x, z) local"""
    a, b = a_robot(M, [[x, y0, z], [x, y1, z]])
    ej = int(np.argmax(np.abs(b - a)))
    otros = [k for k in range(3) if k != ej]
    return ("cil", "xyz"[ej], (a[otros[0]], a[otros[1]]), r, min(a[ej], b[ej]), max(a[ej], b[ej]))


def caja_servo(M, bajo=BAJO_MG90S, perno=True):
    """caja cerrada de un servo: el cuerpo entra desde arriba y las pestanas apoyan en el borde (y 17).
    Abajo, el boton del perno coaxial con el eje (la articulacion queda sostenida de los dos lados)."""
    fondo = 17.0 - bajo - JUEGO
    piso = fondo - PARED
    p = [("J",) + caja_local(M, -16.6, 16.6, piso, 17.0, -6.5 - PARED, 6.5 + PARED),
         ("C",) + caja_local(M, -11.8, 11.8, fondo, 17.1, -6.5, 6.5),
         ("C",) + caja_local(M, 10.0, 17.0, fondo, fondo + 5.0, -3.5, 3.5)]          # salida del cable
    p += [("C",) + cil_local(M, sx * 13.9, 0.0, 0.85, 11.0, 17.1) for sx in (1, -1)]     # M2 de las pestanas
    if perno:
        p += [("J",) + cil_local(M, -5.5, 0.0, 5.0, piso - 2.5, piso + 0.01),
              ("C",) + cil_local(M, -5.5, 0.0, 1.3, piso - 2.6, fondo - 0.6)]           # M3 rosca directo
    return p


def cara_horn(M, ancho=16.0, largo_extra=8.0):
    """placa que se atornilla al horn (encima de la punta del eje): devuelve la caja de la placa"""
    return caja_local(M, -5.5 - 8.0, -5.5 + 8.0 + largo_extra, 31.6, 31.6 + PLACA, -ancho / 2, ancho / 2)


def piso_perno(M, bajo=BAJO_MG90S):
    """y local de la cara de abajo del boton del perno (ahi apoya la placa del perno, con 0.4 de juego)"""
    return 17.0 - bajo - JUEGO - PARED - 2.5 - 0.4


# =====================================================================
# SEGMENTO: DISPOSICION (lado izquierdo; el derecho es espejo en X)
# =====================================================================
CADERA_X, CADERA_Y = 24.0, -22.0        # eje del rolido de cadera (a lo largo de Z)
EJE_Z_SERVO_HORIZ = 13.9                # los servos con eje en Z quedan centrados en z = 0
PIERNA_X = 30.0                         # plano medio de la pierna
MUSLO_Y, LARGO = -48.0, 30.0            # pivotes de arriba del muslo y largo de los eslabones
RODILLA = 14.0                          # alto del bloque de rodilla entre pivotes
Z_ATRAS, Z_ADELANTE = -7.5, 7.5         # eslabon con servo (atras) y eslabon pasivo (adelante)
RODILLA_ARRIBA = MUSLO_Y - LARGO        # -78
RODILLA_ABAJO = RODILLA_ARRIBA - RODILLA  # -92
TOBILLO_Y = RODILLA_ABAJO - LARGO       # -122: eje del servo de la canilla
ROLIDO_TOBILLO_Y = TOBILLO_Y - 22.0     # -144
SUELA_Y = ROLIDO_TOBILLO_Y - 22.0       # -166
PIE = (3.0, 61.0, -45.0, 55.0)          # x0, x1, z0, z1 del pie izquierdo

HOMBRO_Y = 53.0                         # eje del hombro (a lo largo de X): sus cajas pasan por encima de la cintura
# torso: todo adentro. Cintura al centro, PCA9685 atras, ESP32 adelante, hombros a los costados, cuello arriba.
# La bateria y el XL4015 (lo pesado) van abajo, en la pelvis, que no gira con la cintura
TORSO = (35.0, 6.5, 65.5, -25.5, 25.5)  # medio ancho, piso (cara de abajo), techo (cara de arriba), atras, adelante
PISO_TORSO = 3.5
ROLIDO_HOMBRO_X = 84.0                  # eje del rolido del hombro (a lo largo de Z): lejos de las piernas
CODO_Y = 1.0
PUNO_Y = -66.0                          # punta del puno

CINTURA_PUNTA_Y = -2.0                  # punta del eje de la cintura, hacia ABAJO: el horn va en la pelvis
CUELLO_PUNTA_Y = 80.0                   # las pestanas del cuello apoyan arriba del techo (y 65.5)
PELVIS = (34.0, -29.5, -38.0, 46.0)     # medio ancho, fondo, atras, adelante


def servos(s=1):
    """marcos de los servos del lado s (+1 izquierda, -1 derecha). Devuelve dict nombre -> (M, tipo)"""
    X = np.array([s, 1, 1], float)
    v = lambda *a: np.array(a, float) * X
    out = {
        "cadera": (marco_servo(v(CADERA_X, CADERA_Y, 0), [0, 0, -1], v(1, 0, 0), punta=31.5), "MG92B"),
        "muslo": (marco_servo(v(PIERNA_X, MUSLO_Y, Z_ATRAS), v(-1, 0, 0), [0, -1, 0]), "MG90S"),
        "canilla": (marco_servo(v(PIERNA_X, TOBILLO_Y, Z_ATRAS), v(-1, 0, 0), [0, 1, 0]), "MG90S"),
        "tobillo": (marco_servo(v(CADERA_X, ROLIDO_TOBILLO_Y, 0), [0, 0, -1], v(1, 0, 0)), "MG90S"),
        "hombro": (marco_servo(v(0, HOMBRO_Y, 0), v(1, 0, 0), [0, -1, 0]), "MG90S"),
        "rolido_hombro": (marco_servo(v(ROLIDO_HOMBRO_X, HOMBRO_Y, 0), [0, 0, -1], [0, -1, 0]), "MG90S"),
        "codo": (marco_servo(v(ROLIDO_HOMBRO_X, CODO_Y, 0), v(1, 0, 0), [0, 1, 0]), "MG90S"),
    }
    # posiciones a lo largo del eje: centrar el servo donde corresponde
    def correr(nombre, eje, valor_centro):
        M, t = out[nombre]
        centro = a_robot(M, [0, 13.9, 0])[0]     # mitad del servo entre fondo y torre
        M = M.copy()
        M[eje, 3] += valor_centro - centro[eje]
        out[nombre] = (M, t)
    correr("cadera", 2, 0.0)
    correr("tobillo", 2, 0.0)
    correr("rolido_hombro", 2, 0.0)
    correr("muslo", 0, s * PIERNA_X)
    correr("canilla", 0, s * PIERNA_X)
    # hombro: las pestanas apoyan en la cara de afuera de la pared del torso
    M, t = out["hombro"]
    tope = a_robot(M, [0, 17.0, 0])[0][0]
    M = M.copy(); M[0, 3] += s * TORSO[0] - tope
    out["hombro"] = (M, t)
    # codo: la caja centrada bajo el rolido del hombro
    correr("codo", 0, s * ROLIDO_HOMBRO_X)
    return out


def servos_centro():
    # cintura: cuerpo dentro del torso, parado en el piso; eje hacia abajo. Cuerpo hacia +X (deja libres
    # adelante y atras para el ESP32 y la PCA)
    cintura = marco_servo([0, CINTURA_PUNTA_Y, 0], [0, -1, 0], [1, 0, 0])
    # cuello: cuelga del techo; cuerpo hacia atras (no toca el ESP32 de adelante)
    cuello = marco_servo([0, CUELLO_PUNTA_Y, 0], [0, 1, 0], [0, 0, -1])
    return {"cintura": (cintura, "MG90S"), "cuello": (cuello, "MG90S")}


def espejo(prims):
    out = []
    for p in prims:
        op, tipo = p[0], p[1]
        if tipo == "caja":
            x0, x1, y0, y1, z0, z1 = p[2]
            out.append((op, "caja", (-x1, -x0, y0, y1, z0, z1)))
        else:
            _, _, eje, (a, b), r, t0, t1 = p
            if eje == "x":
                out.append((op, "cil", "x", (a, b), r, -t1, -t0))
            elif eje == "y":
                out.append((op, "cil", "y", (-a, b), r, t0, t1))
            else:
                out.append((op, "cil", "z", (-a, b), r, t0, t1))
    return out


def J(*a):
    return ("J", "caja", a)


def C(*a):
    return ("C", "caja", a)


def CIL(op, eje, centro, r, t0, t1):
    return (op, "cil", eje, centro, r, t0, t1)


# =====================================================================
# SEGMENTO: PIEZAS
# =====================================================================
def pelvis():
    w, fondo, atras, adelante = PELVIS
    p = [J(-w, w, -3.0, 0.0, atras, adelante)]                                       # placa de arriba
    # horn de la cintura (fijo a la pelvis): rebaje del brazo del horn y paso del cubo
    p += [CIL("C", "y", (0, 0), 4.5, -2.0, 0.1), C(-3.0, 3.0, -2.0, 0.1, -19.0, 3.0)]
    # bahia de adelante: bateria parada; bahia de atras: XL4015 parado (se compensan adelante/atras)
    p += [J(-w, w, fondo, -2.9, 44.5, adelante), J(-w, w, fondo, fondo + 2.5, 27.0, adelante),   # frente y piso
          J(-w, -w + 2.5, fondo, -2.9, 27.0, adelante), J(w - 2.5, w, fondo, -2.9, 27.0, adelante),
          C(-w + 8, w - 8, fondo + 6, -9.0, 44.4, adelante + 0.1)]                              # ventana del frente
    p += [J(-w, w, fondo, -2.9, atras, atras + 2.0), J(-w, w, fondo, fondo + 2.5, atras, -24.0),
          J(-w, -w + 2.5, fondo, -2.9, atras, -24.0), J(w - 2.5, w, fondo, -2.9, atras, -24.0),
          C(-w + 8, w - 8, fondo + 6, -9.0, atras - 0.1, atras + 2.1)]
    # colgantes de las caderas (atras: horn del servo de cadera; adelante: perno)
    for s in (1, -1):
        M, _ = servos(s)["cadera"]
        eje = a_robot(M, [-5.5, 31.5, 0])[0]
        ex, ey = eje[0], eje[1]
        za = eje[2]                                             # punta del eje (atras)
        zp = a_robot(M, [-5.5, piso_perno(M, BAJO_MG92B), 0])[0][2]
        for z0, z1 in ((za - PLACA - 2.0, za - 0.01), (zp + 0.01, zp + PLACA + 0.01)):
            p.append(J(ex - 10.0, ex + 10.0, ey - 10.0, -0.01, z0, z1))
            p.append(CIL("J", "z", (ex, ey), 10.0, z0, z1))
        p.append(CIL("C", "z", (ex, ey), 4.2, za - PLACA - 2.1, za - 1.9))          # collar del horn
        p.append(CIL("C", "z", (ex, ey), PERNO_R, zp - 0.1, zp + PLACA + 0.1))     # perno
    return p


def torso():
    w, piso, techo, atras, adelante = TORSO
    p = [J(-w, w, piso, piso + PISO_TORSO, atras, adelante),                       # piso
         CIL("J", "y", (0, 0), 18.0, 0.5, piso + 0.01), CIL("C", "y", (0, 0), 8.0, 0.4, piso + 0.02),   # aro de giro
         J(-w, -w + 3.0, piso, techo, atras, adelante), J(w - 3.0, w, piso, techo, atras, adelante),     # costados
         J(-w, w, piso, techo, atras, atras + 3.0),                                                       # espalda
         J(-w, w, techo - 3.0, techo, atras, adelante)]                                                   # techo
    p += [C(-w + 6, w - 6, piso + 8, 37.0, atras - 0.1, atras + 3.1)]           # ventana de la espalda (pines PCA)
    for x0, x1 in ((w - 3.1, w + 0.1), (-w - 0.1, -w + 3.1)):
        p += [C(x0, x1, piso + 6, 19.0, atras + 6, adelante - 6)]
    # cintura: el servo va invertido (eje hacia abajo) parado sobre el piso: las pestanas (y local 17..19.5)
    # apoyan en la cara de arriba del piso y la tapa, la torre y el eje pasan por el piso y el aro
    Mc, _ = servos_centro()["cintura"]
    p += [("C",) + caja_local(Mc, -11.8, 11.8, 19.4, 30.0, -6.5, 6.5)]
    p += [("C",) + cil_local(Mc, sx * 13.9, 0.0, 0.85, 19.4, 25.5) for sx in (1, -1)]
    # cuello: cuelga del techo (pestanas arriba del techo)
    Mn, _ = servos_centro()["cuello"]
    p += [("C",) + caja_local(Mn, -11.8, 11.8, -2, 17.1, -6.5, 6.5)]
    p += [("C",) + cil_local(Mn, sx * 13.9, 0.0, 0.85, 11.0, 17.1) for sx in (1, -1)]
    # hombros: caja del servo hacia adentro, las pestanas apoyan afuera de la pared
    for s in (1, -1):
        M, _ = servos(s)["hombro"]
        p += caja_servo(M, perno=False)
        p += [("C",) + caja_local(M, -11.8, 11.8, 10.0, 17.2, -6.5, 6.5)]
    return p


def tapa_torso():
    w, piso, techo, atras, adelante = TORSO
    return [J(-w, w, piso, techo, adelante, adelante + 2.5),
            C(-w + 8, w - 8, piso + 10, techo - 12, adelante - 0.1, adelante + 2.6)]


def cabeza():
    y0 = CUELLO_PUNTA_Y
    return [J(-23.0, 23.0, y0, y0 + 37.0, -15.0, 23.0),
            C(-20.6, 20.6, y0 + 5.4, y0 + 34.6, -12.6, 20.6),
            C(-12.5, 12.5, y0 + 12.25, y0 + 25.75, 20.5, 23.1)]          # visera (OLED adentro)


def cadera(s=1):
    """bloque de cadera: caja del servo de rolido (MG92B) + orejas del muslo (paralelogramo)"""
    sv = servos(s)
    Mh, _ = sv["cadera"]
    Mm, _ = sv["muslo"]
    p = caja_servo(Mh, bajo=BAJO_MG92B)
    horn_x = a_robot(Mm, [-5.5, 31.5, 0])[0][0]                         # punta del eje del muslo (adentro)
    perno_x = a_robot(Mm, [-5.5, piso_perno(Mm), 0])[0][0]            # cara de abajo del boton (afuera)
    # orejas: adentro (placa del horn) y afuera (perno); bajan del servo de cadera hasta los pivotes del muslo
    for x0, x1 in ((horn_x - s * (PLACA + 2.0), horn_x - s * 0.01), (perno_x + s * 0.01, perno_x + s * (PLACA + 0.01))):
        a, b = min(x0, x1), max(x0, x1)
        p.append(J(a, b, MUSLO_Y - 7.0, CADERA_Y - 2.0, Z_ATRAS - 8.0, Z_ADELANTE + 8.0))
        for z in (Z_ATRAS, Z_ADELANTE):
            p.append(CIL("J", "x", (MUSLO_Y, z), 7.0, a, b))
    # puente de la oreja de afuera al servo de cadera
    xa = sorted([perno_x, a_robot(Mh, [16.6, 0, 0])[0][0], perno_x + s * PLACA])
    p.append(J(xa[0], xa[-1], CADERA_Y - 8.6, CADERA_Y - 2.0, Z_ATRAS - 8.0, Z_ADELANTE + 8.0))
    # puente de la oreja de adentro: por encima de lo que barre la caja del muslo al girar (radio 14)
    xi = sorted([horn_x - s * (PLACA + 2.0), a_robot(Mh, [-16.6, 0, 0])[0][0] + s * 0.5])
    p.append(J(xi[0], xi[1], MUSLO_Y + 14.5, CADERA_Y - 2.0, Z_ATRAS - 8.0, Z_ADELANTE + 8.0))
    for x0, x1 in ((horn_x - s * (PLACA + 2.1), horn_x + s * 0.1), (perno_x - s * 0.1, perno_x + s * (PLACA + 0.2))):
        a, b = min(x0, x1), max(x0, x1)
        p.append(CIL("C", "x", (MUSLO_Y, Z_ADELANTE), PERNO_R, a, b))
    a, b = sorted((horn_x - s * (PLACA + 2.1), horn_x - s * 1.9))
    p.append(CIL("C", "x", (MUSLO_Y, Z_ATRAS), 4.2, a, b))                        # collar del horn del muslo
    a, b = sorted((perno_x - s * 0.1, perno_x + s * (PLACA + 0.2)))
    p.append(CIL("C", "x", (MUSLO_Y, Z_ATRAS), PERNO_R, a, b))
    return p


def eslabon_servo(nombre, s=1):
    """muslo o canilla: la caja del servo es el eslabon de atras del paralelogramo; lengueta con perno en la
    rodilla (arriba para la canilla, abajo para el muslo)"""
    sv = servos(s)
    M, _ = sv[nombre]
    p = caja_servo(M, perno=True)
    y_piv = RODILLA_ARRIBA if nombre == "muslo" else RODILLA_ABAJO
    caja = a_robot(M, [[-16.6, 0, 0], [16.6, 0, 0]])[:, 1]
    y_borde = caja.min() if nombre == "muslo" else caja.max()
    horn_x = a_robot(M, [-5.5, 31.5, 0])[0][0]
    perno_x = a_robot(M, [-5.5, piso_perno(M), 0])[0][0]
    a, b = sorted((horn_x + s * 2.4, perno_x - s * 0.4))
    y0, y1 = sorted((y_borde, y_piv))
    p.append(J(a, b, y0 - (7.0 if nombre == "muslo" else 0), y1 + (7.0 if nombre != "muslo" else 0), Z_ATRAS - 5.0, Z_ATRAS + 5.0))
    p.append(CIL("C", "x", (y_piv, Z_ATRAS), PERNO_R, a - 0.1, b + 0.1))
    return p


def eslabon_pasivo(y_arriba, s=1):
    sv = servos(s)
    Mm, _ = sv["muslo"]
    horn_x = a_robot(Mm, [-5.5, 31.5, 0])[0][0]
    perno_x = a_robot(Mm, [-5.5, piso_perno(Mm), 0])[0][0]
    a, b = sorted((horn_x + s * 0.4, perno_x - s * 0.4))
    y1, y0 = y_arriba, y_arriba - LARGO
    p = [J(a, b, y0, y1, Z_ADELANTE - 4.0, Z_ADELANTE + 4.0),
         CIL("J", "x", (y1, Z_ADELANTE), 6.0, a, b), CIL("J", "x", (y0, Z_ADELANTE), 6.0, a, b),
         C(a + 4.0, b - 4.0, y0 + 6.0, y1 - 6.0, Z_ADELANTE - 4.1, Z_ADELANTE + 4.1)]
    p += [CIL("C", "x", (y, Z_ADELANTE), PERNO_R, a - 0.1, b + 0.1) for y in (y0, y1)]
    return p


def rodilla(s=1):
    sv = servos(s)
    Mm, _ = sv["muslo"]
    horn_x = a_robot(Mm, [-5.5, 31.5, 0])[0][0]
    perno_x = a_robot(Mm, [-5.5, piso_perno(Mm), 0])[0][0]
    p = []
    for x0, x1 in ((horn_x - s * (PLACA + 2.0), horn_x), (perno_x, perno_x + s * PLACA)):
        a, b = sorted((x0, x1))
        p.append(J(a, b, RODILLA_ABAJO - 7.0, RODILLA_ARRIBA + 7.0, Z_ATRAS - 7.0, Z_ADELANTE + 9.5))
        for y in (RODILLA_ARRIBA, RODILLA_ABAJO):
            for z in (Z_ATRAS, Z_ADELANTE):
                p.append(CIL("C", "x", (y, z), PERNO_R, a - 0.1, b + 0.1))
    a, b = sorted((horn_x - s * (PLACA + 2.0), perno_x + s * PLACA))
    p.append(J(a, b, RODILLA_ABAJO + 3.0, RODILLA_ARRIBA - 3.0, Z_ADELANTE + 6.5, Z_ADELANTE + 9.5))   # puente de adelante

    return p


def tobillo(s=1):
    """bloque de tobillo: orejas de la canilla (horn adentro, perno afuera) + caja del servo de rolido"""
    sv = servos(s)
    Mt, _ = sv["tobillo"]
    Mc, _ = sv["canilla"]
    p = caja_servo(Mt)
    horn_x = a_robot(Mc, [-5.5, 31.5, 0])[0][0]
    perno_x = a_robot(Mc, [-5.5, piso_perno(Mc), 0])[0][0]
    for x0, x1 in ((horn_x - s * (PLACA + 2.0), horn_x - s * 0.01), (perno_x + s * 0.01, perno_x + s * (PLACA + 0.01))):
        a, b = sorted((x0, x1))
        p.append(J(a, b, ROLIDO_TOBILLO_Y + 2.0, TOBILLO_Y + 7.0, Z_ATRAS - 8.0, Z_ADELANTE + 8.0))
        for z in (Z_ATRAS, Z_ADELANTE):
            p.append(CIL("J", "x", (TOBILLO_Y, z), 7.0, a, b))
    xa = sorted([perno_x, a_robot(Mt, [16.6, 0, 0])[0][0], perno_x + s * PLACA])
    p.append(J(xa[0], xa[-1], ROLIDO_TOBILLO_Y + 2.0, ROLIDO_TOBILLO_Y + 8.6, Z_ATRAS - 8.0, Z_ADELANTE + 8.0))
    # puente de la oreja de adentro: por debajo de lo que barre la caja de la canilla al girar (radio 14)
    xi = sorted([horn_x - s * (PLACA + 2.0), a_robot(Mt, [-16.6, 0, 0])[0][0] + s * 0.5])
    p.append(J(xi[0], xi[1], ROLIDO_TOBILLO_Y + 2.0, TOBILLO_Y - 14.5, Z_ATRAS - 8.0, Z_ADELANTE + 8.0))
    for x0, x1 in ((horn_x - s * (PLACA + 2.1), horn_x + s * 0.1), (perno_x - s * 0.1, perno_x + s * (PLACA + 0.2))):
        a, b = sorted((x0, x1))
        p.append(CIL("C", "x", (TOBILLO_Y, Z_ADELANTE), PERNO_R, a, b))
    a, b = sorted((horn_x - s * (PLACA + 2.1), horn_x - s * 1.9))
    p.append(CIL("C", "x", (TOBILLO_Y, Z_ATRAS), 4.2, a, b))
    a, b = sorted((perno_x - s * 0.1, perno_x + s * (PLACA + 0.2)))
    p.append(CIL("C", "x", (TOBILLO_Y, Z_ATRAS), PERNO_R, a, b))
    return p


def pie(s=1):
    sv = servos(1)                     # se arma el izquierdo y el derecho es su espejo
    Mt, _ = sv["tobillo"]
    x0, x1, z0, z1 = PIE
    eje = a_robot(Mt, [-5.5, 31.5, 0])[0]
    ex, ey, za = eje
    zp = a_robot(Mt, [-5.5, piso_perno(Mt), 0])[0][2]
    p = [J(x0, x1, SUELA_Y, SUELA_Y + 4.0, z0, z1),
         C(x0 + 6, x1 - 6, SUELA_Y + 1.5, SUELA_Y + 4.1, z0 + 6, z1 - 6),        # bandeja aligerada
         J(x0 + 6, x1 - 6, SUELA_Y, SUELA_Y + 4.0, -2.0, 2.0),                    # nervio en cruz
         J((x0 + x1) / 2 - 2, (x0 + x1) / 2 + 2, SUELA_Y, SUELA_Y + 4.0, z0 + 6, z1 - 6)]
    for a, b in ((za - PLACA - 2.0, za - 0.01), (zp + 0.01, zp + PLACA + 0.01)):
        p.append(J(ex - 10.0, ex + 10.0, SUELA_Y + 2.0, ey, a, b))
        p.append(CIL("J", "z", (ex, ey), 10.0, a, b))
    p.append(CIL("C", "z", (ex, ey), 4.2, za - PLACA - 2.1, za - 1.9))
    p.append(CIL("C", "z", (ex, ey), PERNO_R, zp - 0.1, zp + PLACA + 0.1))
    if s < 0:
        p = espejo(p)
    return p


def hombro(s=1):
    """horquilla del hombro: placa sobre el horn del servo del torso + caja del servo de rolido"""
    sv = servos(s)
    Mh, _ = sv["hombro"]
    Mr, _ = sv["rolido_hombro"]
    eje = a_robot(Mh, [-5.5, 31.5, 0])[0]
    x0, x1 = sorted((eje[0] + s * 0.01, eje[0] + s * (PLACA + 2.0)))
    caja = caja_servo(Mr)
    bx = np.array([c for pr in caja if pr[1] == "caja" for c in (pr[2][0], pr[2][1])])
    p = [J(x0, x1, HOMBRO_Y - 22.0, HOMBRO_Y + 12.0, -12.0, 12.0),
         CIL("J", "x", (HOMBRO_Y, 0.0), 12.0, x0, x1)]
    p += caja
    a, b = sorted((x1 if s > 0 else x0, bx.min() if s > 0 else bx.max()))
    p.append(J(a, b, HOMBRO_Y - 22.0, HOMBRO_Y - 14.0, -8.0, 8.0))
    p.append(CIL("C", "x", (HOMBRO_Y, 0.0), 4.2, *sorted((eje[0] - s * 0.1, eje[0] + s * 2.0))))
    return p


def brazo(s=1):
    """brazo: horquilla en el rolido del hombro (horn atras, perno adelante) que baja hasta la caja del codo;
    el puente va ARRIBA de la caja del codo (abajo se mueve el antebrazo)"""
    sv = servos(s)
    Mr, _ = sv["rolido_hombro"]
    Mc, _ = sv["codo"]
    eje = a_robot(Mr, [-5.5, 31.5, 0])[0]
    zp = a_robot(Mr, [-5.5, piso_perno(Mr), 0])[0][2]
    p = caja_servo(Mc)
    tope = a_robot(Mc, [16.6, 0, 0])[0][1]                          # cara de arriba de la caja del codo
    cx = sorted(a_robot(Mc, [[0, -6.1, 0], [0, 17.0, 0]])[:, 0])
    for a, b in ((eje[2] - PLACA - 2.0, eje[2] - 0.01), (zp + 0.01, zp + PLACA + 0.01)):
        p.append(J(eje[0] - 9.0, eje[0] + 9.0, tope - 0.01, HOMBRO_Y, a, b))
        p.append(CIL("J", "z", (eje[0], eje[1]), 9.0, a, b))
    p.append(J(min(cx[0], eje[0] - 9.0), max(cx[1], eje[0] + 9.0), tope - 0.01, tope + 5.0, eje[2] - PLACA - 2.0, zp + PLACA))
    p.append(CIL("C", "z", (eje[0], eje[1]), 4.2, eje[2] - PLACA - 2.1, eje[2] - 1.9))
    p.append(CIL("C", "z", (eje[0], eje[1]), PERNO_R, zp - 0.1, zp + PLACA + 0.1))
    return p


def antebrazo(s=1):
    """antebrazo y puno: horquilla en el codo (horn afuera, perno adentro) y puno macizo para pegar"""
    sv = servos(s)
    Mc, _ = sv["codo"]
    eje = a_robot(Mc, [-5.5, 31.5, 0])[0]
    xp = a_robot(Mc, [-5.5, piso_perno(Mc), 0])[0][0]
    p = []
    for a, b in (sorted((eje[0] + s * 0.01, eje[0] + s * (PLACA + 2.0))), sorted((xp - s * 0.01, xp - s * (PLACA + 0.01)))):
        p.append(J(a, b, PUNO_Y + 25.0, CODO_Y, -9.0, 9.0))
        p.append(CIL("J", "x", (CODO_Y, 0.0), 9.0, a, b))
    xs = sorted((eje[0] + s * (PLACA + 2.0), xp - s * (PLACA + 0.01)))
    p.append(J(xs[0], xs[1], PUNO_Y, PUNO_Y + 28.0, -12.0, 12.0))                    # puno
    p.append(C(xs[0] + 3, xs[1] - 3, PUNO_Y + 4.0, PUNO_Y + 24.0, -12.1, 9.0))      # hueco del puno, abierto atras
    p.append(CIL("C", "x", (CODO_Y, 0.0), 4.2, *sorted((eje[0] + s * 1.9, eje[0] + s * (PLACA + 2.1)))))
    p.append(CIL("C", "x", (CODO_Y, 0.0), PERNO_R, *sorted((xp + s * 0.1, xp - s * (PLACA + 0.2)))))
    return p


def piezas():
    """nombre -> primitivas. Las de pierna y brazo van en version izquierda y derecha"""
    d = {"R2_pelvis": pelvis(), "R2_torso": torso(), "R2_tapa_torso": tapa_torso(), "R2_cabeza": cabeza()}
    for s, lado in ((1, "izq"), (-1, "der")):
        d[f"R2_cadera_{lado}"] = cadera(s)
        d[f"R2_muslo_{lado}"] = eslabon_servo("muslo", s)
        d[f"R2_muslo_link_{lado}"] = eslabon_pasivo(MUSLO_Y, s)
        d[f"R2_rodilla_{lado}"] = rodilla(s)
        d[f"R2_canilla_{lado}"] = eslabon_servo("canilla", s)
        d[f"R2_canilla_link_{lado}"] = eslabon_pasivo(RODILLA_ABAJO, s)
        d[f"R2_tobillo_{lado}"] = tobillo(s)
        d[f"R2_pie_{lado}"] = pie(s)
        d[f"R2_hombro_{lado}"] = hombro(s)
        d[f"R2_brazo_{lado}"] = brazo(s)
        d[f"R2_antebrazo_{lado}"] = antebrazo(s)
    return d


# =====================================================================
# SEGMENTO: COMPONENTES EN SU LUGAR (modelo, matriz local->robot, masa)
# =====================================================================
def matriz(cols, caja_local, minimo):
    """rota la caja local con las columnas dadas (imagen de x, y, z locales) y la traslada a 'minimo'"""
    R = np.column_stack([np.asarray(c, float) for c in cols])
    lo, hi = np.asarray(caja_local[0], float), np.asarray(caja_local[1], float)
    esq = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]) @ R.T
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = np.asarray(minimo, float) - esq.min(0)
    return M


def componentes():
    w, piso, techo, atras, adelante = TORSO
    pw, pfondo, patras, padelante = PELVIS
    piso_t = piso + PISO_TORSO
    c = []
    ruta = lambda n: os.path.join(COMPONENTES, n)
    servo = ruta("MG90S_grabcad_mg90s9.ipt")
    for nombre, (M, tipo) in servos_centro().items():
        c.append((f"servo_{nombre}", servo, M, MASAS[tipo]))
    for s, lado in ((1, "izq"), (-1, "der")):
        for nombre, (M, tipo) in servos(s).items():
            c.append((f"servo_{nombre}_{lado}", servo, M, MASAS[tipo]))
    # pelvis: bateria parada adelante de las caderas, XL4015 parado atras (lo pesado, lo mas abajo posible)
    c.append(("bateria", ruta("Bateria_LiPo_2S_1000_62x23x17.ipt"),
              matriz([(1, 0, 0), (0, 1, 0), (0, 0, 1)], ((0, 0, 0), (62.0, 23.4, 16.7)), (-31.0, pfondo + 2.5, 27.5)), MASAS["bateria"]))
    c.append(("XL4015", ruta("XL4015_52x12x24_acostado.ipt"),
              matriz([(1, 0, 0), (0, 0, 1), (0, -1, 0)], ((0, 0, 0), (52.3, 12.0, 23.5)), (-26.15, pfondo + 2.5, patras + 2.0)), MASAS["XL4015"]))
    c.append(("IMU", ruta("IMU_GY521_21x16.ipt"),
              matriz([(1, 0, 0), (0, 1, 0), (0, 0, 1)], ((0, 0, 0), (21.2, 3.0, 16.4)), (-10.6, -6.5, 1.0)), MASAS["IMU"]))
    # torso: PCA9685 parada atras (pines hacia la espalda), ESP32 parado adelante
    c.append(("PCA9685", ruta("PCA9685_adafruit_815.iam"),
              matriz([(-1, 0, 0), (0, 1, 0), (0, 0, -1)], ((-1.9, -6.5, -2.0), (60.3, 18.9, 10.1)), (-31.1, piso_t, atras + 3.0)), MASAS["PCA9685"]))
    c.append(("ESP32", ruta("ESP32_devkit_v1_30pin.iam"),
              matriz([(0, 1, 0), (1, 0, 0), (0, 0, -1)], ((-2.4, -3.7, -10.2), (26.6, 49.4, 3.3)), (-26.55, piso_t, adelante - 3.0 - 13.5)), MASAS["ESP32"]))
    return c


EXTRAS = [  # masas sin modelo (g) y donde van
    ("OLED", MASAS["OLED"], (0.0, CUELLO_PUNTA_Y + 18.0, 18.0)),
    ("interruptor", MASAS["interruptor"], (-PELVIS[0], -15.0, 35.0)),
    ("cables_y_tornillos", MASAS["cables_y_tornillos"], (0.0, 10.0, 0.0)),
]
