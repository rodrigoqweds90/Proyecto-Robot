"""SEGMENTO: VERIFICACION DE LOS TORNILLOS FIJOS (torso, tapas, aro, giroscopio, cabeza, pestanas M2)
Para cada tornillo pone su eje en el mundo y revisa en las mallas impresas:
  - rosca: mm del tramo roscado donde hay material alrededor del agujero (anillo a 0.6 mm del piloto)
  - agujero: que el piloto exista en la pieza que recibe (el centro del eje no tiene material)
  - punta: que la punta no choque con el fondo de un agujero ciego
  - paso: que la pieza que se aprieta tenga el agujero de paso y material bajo la cabeza
Las articulaciones con Pipe_M3 las revisa verificar_pipes.py.
"""
import os

import numpy as np
import trimesh

import cabeza as cb
import carcasa as ca
import torso as to

BASE = os.path.dirname(os.path.abspath(__file__))
PASO_ANILLO = 0.25          # mm entre muestras a lo largo del eje
ANGULOS = 16


def malla(nombre, ejes=None, t=(0.0, 0.0, 0.0)):
    for carpeta in ("stl", "piezas_m3"):
        ruta = os.path.join(BASE, carpeta, nombre + ".stl")
        if os.path.exists(ruta):
            m = trimesh.load(ruta, force="mesh")
            break
    M = np.eye(4)
    if ejes is not None:
        M[:3, :3] = np.column_stack([np.asarray(e, float) for e in ejes])
    M[:3, 3] = t
    m.apply_transform(M)
    return m


def base_ortogonal(d):
    a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(d, a)
    u /= np.linalg.norm(u)
    return u, np.cross(d, u)


def anillo(p, d, r):
    u, v = base_ortogonal(d)
    a = np.linspace(0, 2 * np.pi, ANGULOS, endpoint=False)
    return p + r * (np.outer(np.cos(a), u) + np.outer(np.sin(a), v))


def revisar(nombre, pts, d, cara, largo, piloto, recibe, paso=None, minimo=3.5, cabeza_r=2.6):
    """pts: puntos del eje (en el plano de la cara); d: hacia donde avanza el tornillo; cara: punto del eje
    donde apoya la cabeza (se toma su coordenada a lo largo de d)."""
    d = np.asarray(d, float) / np.linalg.norm(d)
    filas = []
    for p0 in pts:
        p0 = np.asarray(p0, float)
        o = p0 + d * (np.dot(np.asarray(cara, float) - p0, d))        # donde apoya la cabeza (aprox.)
        corrida = 0.0
        if paso is not None:
            # la cara real es la primera (desde el lado de la cabeza) con material bajo la cabeza y el paso libre
            for c in np.arange(-6.0, 6.0, 0.1):
                q = o + d * (c + 0.15)
                if paso.contains(anillo(q, d, cabeza_r)).mean() >= 0.75 and not paso.contains([q])[0]:
                    corrida = round(float(c), 1)
                    o = o + d * c
                    break
        s = np.arange(PASO_ANILLO / 2, largo, PASO_ANILLO)
        rosca = 0.0
        vacio = True
        for si in s:
            q = o + d * si
            dentro = recibe.contains(anillo(q, d, piloto + 0.6)).mean()
            if dentro >= 0.9:
                rosca += PASO_ANILLO
                if recibe.contains([q])[0]:
                    vacio = False
        punta = recibe.contains([o + d * (largo - 0.1)])[0] and not recibe.contains([o + d * (largo - 1.0)])[0]
        fila = {"rosca": round(rosca, 1), "agujero": vacio, "punta libre": not punta}
        if paso is not None:
            fila["paso libre"] = not paso.contains([o + d * 0.15]).any()
            fila["apoyo cabeza"] = round(float(paso.contains(anillo(o + d * 0.15, d, cabeza_r)).mean()), 2)
            fila["cara corrida mm"] = corrida
        ok = fila["rosca"] >= minimo and fila["agujero"] and fila["punta libre"] and \
            (paso is None or (fila["paso libre"] and fila["apoyo cabeza"] >= 0.75))
        filas.append((np.round(p0, 1).tolist(), fila, ok))
    return nombre, filas


def main():
    torso = malla("Torso_cuerpo" + to.SUF)
    pecho = malla("Torso_pecho")
    espalda = malla("Torso_espalda") if to.VARIANTE == "A" else None
    aro = malla("Spacer01_W", [[1, 0, 0], [0, -1, 0], [0, 0, -1]], (0.0, 4.0, 25.2))
    t_cab = np.array([0.0, 109.0, 13.85])
    frente = malla("Cabeza_frente", t=t_cab)
    tapa = malla("Cabeza_tapa", t=t_cab)
    r3 = to.M3_AUTORROSCA / 2
    casos = []
    # pecho -> torso: M3x10 desde adelante
    casos.append(revisar("pecho M3x10", [(x, y, 0) for x, y in to.POSTES_PECHO], (0, 0, -1), (0, 0, ca.PECHO_Z[1]),
                         10.0, r3, torso, pecho))
    # espalda -> torso (topes del ESP32): M3x8 desde atras, cabeza en su asiento
    if espalda is not None:
        casos.append(revisar("espalda M3x8", [(x, y, 0) for x, y in ca.TORNILLOS_ESPALDA], (0, 0, 1),
                             (0, 0, ca.ESPALDA_Z[0] + ca.M3_CABEZA[1]), 8.0, r3, torso, espalda, cabeza_r=2.4))
    atras = malla("Torso_atras_B") if to.VARIANTE != "A" else None
    if to.VARIANTE != "A":   # pared de atras -> torso: M3x8 desde atras, en el aro del tubo (postes autorroscantes)
        casos.append(revisar("atras M3x8", [(x, y, 0) for x, y in to.TORNILLOS_ATRAS_B], (0, 0, 1),
                             (0, 0, to.PARED_ATRAS[0] + ca.M3_CABEZA[1]), 8.0, r3, torso, atras, cabeza_r=2.4))
    # aro espaciador -> torso: M2x8 desde abajo
    casos.append(revisar("aro cintura M2x8", [(x, 0, z) for x, z in to.TORNILLOS_ESPACIADOR], (0, 1, 0), (0, 0.0, 0),
                         8.0, to.ESPACIADOR_AGUJERO / 2, torso, aro))
    # giroscopio: M3x6 desde arriba sobre la placa (1.6 mm)
    casos.append(revisar("giroscopio M3x6", [(x, 0, z) for x, z in to.IMU_AGUJEROS], (0, -1, 0), (0, to.IMU_Y + 1.6, 0),
                         6.0, r3, torso, minimo=3.0))
    # PCA9685: tornillos chicos de servo (M2 aprox, 6 mm) desde arriba sobre la placa
    if to.VARIANTE == "A":
        postes = [(sx * to.PCA_AGUJEROS_X, 0, z) for sx in (1, -1) for z in to.PCA_AGUJEROS_Z]
        casos.append(revisar("PCA9685 tornillo de servo", postes, (0, -1, 0), (0, to.PCA_Y_PLACA + 1.6, 0), 6.0, 0.8,
                             torso, minimo=3.0))
    else:   # B: placa parada, tornillos desde adelante (cara de las soldaduras) hacia los postes de Torso_atras_B
        casos.append(revisar("PCA9685 tornillo de servo", [(x, y, 0) for x, y in to.PCA_B_AGUJEROS], (0, 0, -1),
                             (0, 0, to.PCA_B_T[2]), 6.0, 0.8, atras, minimo=3.0))
    # M2 de las pestanas de servo, directo en el plastico (agujero 1.7): se mide la rosca que muerde
    ri = to.INSERTO_M2 / 2
    casos.append(revisar("M2 pestana cuello", [(0, 0, z) for z in to.CUELLO_Z], (0, -1, 0), (0, to.Y_TECHO, 0), 4.0, ri,
                         torso, minimo=3.5))
    casos.append(revisar("M2 pestana cintura", [(0, 0, z) for z in to.CINTURA_Z], (0, 1, 0), (0, to.CINTURA_Y, 0), 3.5, ri,
                         torso, minimo=3.0))
    for s in (1, -1):
        casos.append(revisar(f"M2 pestana hombro {'izq' if s > 0 else 'der'}", [(0, y, to.HOMBRO_Z) for y in to.HOMBRO_Y],
                             (-s, 0, 0), (s * to.X_EXT, 0, 0), 4.0, ri, torso, minimo=3.5))
    # cabeza: tapa -> frente, M3x10 desde atras (asiento de la cabeza 4 mm adentro de la tapa)
    x_t = cb.ANCHO / 2 - cb.PARED - cb.TORRE_DIAM / 2 + cb.TORRE_EMPOTRADO
    y_t = -cb.ALTO + cb.PISO + cb.TORRE_DIAM / 2 - cb.TORRE_EMPOTRADO
    z_asiento = cb.ADELANTE - cb.PROFUNDO / 2 - 1 + 4.0
    casos.append(revisar("cabeza tapa M3x10", [t_cab + (sx * x_t, y_t, 0) for sx in (1, -1)], (0, 0, 1),
                         t_cab + (0, 0, z_asiento), 10.0, cb.TORRE_AGUJERO / 2, frente, tapa, minimo=3.5, cabeza_r=2.4))
    malos = 0
    for nombre, filas in casos:
        for p, fila, ok in filas:
            malos += not ok
            print(f"{'OK ' if ok else 'MAL'} {nombre:26s} en {p}: {fila}")
    print(f"\n{sum(len(f) for _, f in casos)} tornillos revisados, con problema: {malos}")


if __name__ == "__main__":
    main()
