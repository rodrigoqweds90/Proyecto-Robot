"""SEGMENTO: PRUEBA DE FUERZA Y ALIGERADO DE TODAS LAS PIEZAS
Arma interfaces y casos de carga reales de cada pieza a partir del ensamble y corre
fea_pieza.aligerar_ventanas. Resultados en fea/resultados.json y piezas en fea/aligeradas/.
"""
import collections
import json
import os
import sys
import time
import traceback

import numpy as np
import trimesh

AQUI = os.path.dirname(os.path.abspath(__file__))
NUEVO = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
sys.path.insert(0, NUEVO)
import fea_pieza as fp  # noqa: E402
import m3_pernos as m3  # noqa: E402
import torso_estudio as te  # noqa: E402

nx = te.nx
SALIDA = os.path.join(AQUI, "aligeradas")
RESULTADOS = os.path.join(AQUI, "resultados.json")
PIEZAS_NX25 = ["Bracket01_B", "Bracket03_B", "Bracket04_B", "Bracket05_B", "Nee_B", "Link_W",
               "Bracket07_B", "Bracket08_B", "Bracket09_W", "Bracket10_W", "Bracket11_B", "Bracket12_B", "Bracket02_W"]
CENTRO_CUERPO = np.array([0.0, 0.0, 25.0])
PESO_BRAZO = 10.0


def fuente(nombre):
    for ruta in (os.path.join(NUEVO, "piezas_m3", nombre + ".stl"),
                 os.path.join(NUEVO, "piezas_canales", nombre + "_brida.stl"),
                 os.path.join(nx.BASE, "stl", nombre + ".stl")):
        if os.path.exists(ruta):
            return ruta


def matriz_instancia(nombre):
    for n, ejes, t in te.ensamble():
        if n == nombre:
            return np.column_stack([np.asarray(e, float) for e in ejes]), np.asarray(t, float)
    # piezas que en el estudio se corren (brazos): usar el armado del NX25
    piezas = [("Bracket06_W", [nx.X * -1, nx.Y, nx.Z * -1], [0, 0, 0])] + nx.pierna(1) + nx.pierna(-1) + nx.brazos()
    for n, ejes, t in piezas:
        if n == nombre:
            return np.column_stack([np.asarray(e, float) for e in ejes]), np.asarray(t, float)
    raise KeyError(nombre)


def interfaces_nx25(nombre):
    """Lista de interfaces (para fp.interfaces_desde_agujeros) con grupos: pestanas_k, horn_k, perno_k."""
    agujeros = json.load(open(m3.AGUJEROS, encoding="utf-8")).get(nombre, [])
    orig = trimesh.load(os.path.join(nx.BASE, "stl", nombre + ".stl"), force="mesh")
    lista = []
    usados = set()
    # servos sostenidos por la pieza: agujeros de pestana cerca de los puntos de SERVOS_EN
    servos = []
    for k, (cerca, lejos, eje) in enumerate(nx.SERVOS_EN.get(nombre, [])):
        cerca, lejos, eje = (np.asarray(v, float) for v in (cerca, lejos, eje))
        xs = (lejos - cerca) / np.linalg.norm(lejos - cerca)
        medio = (cerca + lejos) / 2
        servos.append(dict(nombre=f"pestanas_{k}", eje_punto=medio - xs * 5.5, eje=eje))
        for p in (cerca, lejos):
            lista.append(dict(nombre=f"pestanas_{k}", tipo="agujero", centro=p, eje=eje, radio=2.0, desde=-4.0, hasta=4.0))
    # horns: rebaje alrededor del punto de HORNS_EN
    horns = []
    for k, (p, eje) in enumerate(nx.HORNS_EN.get(nombre, [])):
        horns.append(dict(nombre=f"horn_{k}", punto=np.asarray(p, float), eje=np.asarray(eje, float)))
        lista.append(dict(nombre=f"horn_{k}", tipo="horn", centro=p, eje=eje, radio=5.0, desde=-2.5, hasta=2.5))
    # pernos M3: tramos de agujeros de giro (O5.5 original) y de agarre (O1.8 coaxial a un perno)
    for k, h in enumerate(agujeros):
        if not (2.6 < h["r"] < 2.8 or 0.8 < h["r"] < 1.0):
            continue
        eje = m3.EJES[h["eje"]]
        ci = h["centro"]["XYZ".index(h["eje"])]
        for j, (a, b) in enumerate(m3.tramos_con_pared(orig, h)):
            c = np.array(h["centro"], float)
            c["XYZ".index(h["eje"])] = (a + b) / 2
            # los O1.8 que ya son pestana u horn no se repiten
            if 0.8 < h["r"] < 1.0:
                if any(np.linalg.norm(c - it["centro"]) < 3.0 for it in lista if it["nombre"].startswith("pestanas")):
                    continue
                if any(np.linalg.norm(np.cross(c - hn["punto"], hn["eje"])) < 14.0 for hn in horns):
                    continue
            lista.append(dict(nombre=f"perno_{k}_{j}", tipo="agujero", centro=h["centro"], eje=eje,
                              radio=max(h["r"], 1.65) + 0.4, desde=a - ci - 0.2, hasta=b - ci + 0.2))
    return lista, servos, horns


def casos_nx25(nombre, lista, servos, horns):
    # un perno coaxial con un agujero de pestana/horn es el mismo agujero (tornillo del servo): quitarlo,
    # si no se carga y se fija el mismo nodo y el caso da esfuerzo cero (Bracket10_W)
    def mismo_agujero(p, q):
        e = np.asarray(p["eje"], float) / np.linalg.norm(p["eje"])
        f = np.asarray(q["eje"], float) / np.linalg.norm(q["eje"])
        d = np.asarray(p["centro"], float) - np.asarray(q["centro"], float)
        return abs(abs(e @ f) - 1) < 0.02 and np.linalg.norm(d - (d @ e) * e) < 1.0 and abs(d @ e) < 6.0
    otros = [it for it in lista if not it["nombre"].startswith("perno")]
    lista[:] = [it for it in lista if not (it["nombre"].startswith("perno") and any(mismo_agujero(it, o) for o in otros))]
    M, t = matriz_instancia(nombre)
    grupos = sorted({it["nombre"] for it in lista})
    centro_grupo = {}
    for g in grupos:
        pts = [np.asarray(it["centro"], float) for it in lista if it["nombre"] == g]
        centro_grupo[g] = np.mean(pts, axis=0)
    dist = {g: np.linalg.norm(M @ c + t - CENTRO_CUERPO) for g, c in centro_grupo.items()}
    orden = sorted(grupos, key=lambda g: dist[g])
    mitad = max(1, len(orden) // 2)
    cerca, lejos = orden[:mitad], orden[mitad:]
    if nombre in ("Bracket04_B", "Bracket05_B"):
        # pie: la carga entra desde el piso (suela fija) y sale por el tobillo (horn + perno)
        abajo = M.T @ np.array([0, -1.0, 0])
        tobillo = [g for g in grupos]
        casos = [dict(nombre="suela", fijas=["suela"], fuerzas=[(tobillo, M.T @ (np.array(v) * fp.PESO_DINAMICO)) for v in ([1, 0, 0], [0, 1, 0], [0, 0, 1])])]
        for h in horns:
            casos.append(dict(nombre=f"torque {h['nombre']}", fijas=["suela"], torque=([h["nombre"]], h["punto"], h["eje"], fp.TORQUE_SERVO)))
        lista.append(dict(nombre="suela", tipo="agujero", plano=list(abajo)))
        return casos
    if nombre == "Link_W":
        # biela con pivote en cada extremo: solo trabaja a traccion/compresion entre sus ejes
        eje = np.mean([centro_grupo[g] for g in lejos], axis=0) - np.mean([centro_grupo[g] for g in cerca], axis=0)
        eje /= np.linalg.norm(eje)
        return [dict(nombre="biela", fijas=cerca, fuerzas=[(lejos, eje * fp.PESO_DINAMICO)])]
    es_brazo = nombre in ("Bracket07_B", "Bracket08_B", "Bracket09_W", "Bracket10_W", "Bracket11_B", "Bracket12_B")
    P = PESO_BRAZO if es_brazo else fp.PESO_DINAMICO
    casos = []
    for s in servos:
        fijas = [g for g in grupos if g != s["nombre"]]
        if fijas:
            casos.append(dict(nombre=f"torque {s['nombre']}", fijas=fijas, torque=([s["nombre"]], s["eje_punto"], s["eje"], fp.TORQUE_SERVO)))
    for h in horns:
        fijas = [g for g in grupos if g != h["nombre"]]
        if fijas:
            casos.append(dict(nombre=f"torque {h['nombre']}", fijas=fijas, torque=([h["nombre"]], h["punto"], h["eje"], fp.TORQUE_SERVO)))
    if lejos and cerca:
        # peso en direcciones del mundo, pasadas a coordenadas de la pieza
        fuerzas = [(lejos, M.T @ (np.array(v) * P)) for v in ([1, 0, 0], [0, 1, 0], [0, 0, 1])]
        casos.append(dict(nombre="peso", fijas=cerca, fuerzas=fuerzas))
    return casos


def interfaces_pelvis():
    import pelvis as pv
    L = []
    for s in (1, -1):
        L.append(dict(nombre=f"horn_cadera_{s}", tipo="horn", centro=[s * pv.CADERA_X, pv.CADERA_Y, pv.Z_BRAZO_CADERA + 1.0], eje=[0, 0, 1], radio=5.5, desde=-1.5, hasta=3.5))
        L.append(dict(nombre=f"perno_cadera_{s}", tipo="agujero", centro=[s * pv.CADERA_X, pv.CADERA_Y, 41.0], eje=[0, 0, 1], radio=2.1, desde=-2.2, hasta=2.4))
    L.append(dict(nombre="horn_cintura", tipo="horn", centro=[0, pv.BANDA_CINTURA["y"] + 1.2, pv.CINTURA_Z], eje=[0, 1, 0], radio=5.5, desde=-1.5, hasta=2.0))
    L.append(dict(nombre="disco", tipo="agujero", centro=[0, -0.05, pv.CINTURA_Z], eje=[0, 1, 0], radio=18.0, desde=-0.2, hasta=0.2))
    casos = [
        dict(nombre="parado", fijas=["horn_cadera_1", "horn_cadera_-1", "perno_cadera_1", "perno_cadera_-1"],
             fuerzas=[(["disco"], [0, -10.0, 0]), (["disco"], [10.0, 0, 0]), (["disco"], [0, 0, 10.0])]),
        dict(nombre="torque cintura", fijas=["horn_cadera_1", "horn_cadera_-1", "perno_cadera_1", "perno_cadera_-1"],
             torque=(["horn_cintura"], [0, 0, pv.CINTURA_Z], [0, 1, 0], fp.TORQUE_SERVO)),
    ]
    for s in (1, -1):
        casos.append(dict(nombre=f"torque cadera {s}", fijas=["horn_cintura", "disco", f"perno_cadera_{-s}", f"horn_cadera_{-s}"],
                          torque=([f"horn_cadera_{s}"], [s * pv.CADERA_X, pv.CADERA_Y, 0], [0, 0, 1], fp.TORQUE_SERVO)))
    return L, casos


def interfaces_torso():
    import torso as to
    L = []
    for z in to.CINTURA_Z:
        L.append(dict(nombre="cintura", tipo="agujero", centro=[0, to.CINTURA_Y + 1.7, z], eje=[0, 1, 0], radio=2.2, desde=-2.0, hasta=2.0))
    for z in to.CUELLO_Z:
        L.append(dict(nombre="cuello", tipo="agujero", centro=[0, to.Y_TECHO - 2.5, z], eje=[0, 1, 0], radio=2.2, desde=-3.0, hasta=3.0))
    for s in (1, -1):
        for y in to.HOMBRO_Y:
            L.append(dict(nombre=f"hombro_{s}", tipo="agujero", centro=[s * (to.X_EXT - 3.0), y, to.HOMBRO_Z], eje=[1, 0, 0], radio=2.2, desde=-3.5, hasta=3.5))
    for x, z in to.TORNILLOS_ESPACIADOR:
        L.append(dict(nombre="espaciador", tipo="agujero", centro=[x, to.Y_PISO + 3.0, z], eje=[0, 1, 0], radio=1.9, desde=-3.0, hasta=3.0))
    L.append(dict(nombre="bateria", tipo="agujero", centro=[0, to.CUBIERTA[1], (to.BAT[4] + to.BAT[5]) / 2], eje=[0, 1, 0], radio=30.0, desde=-0.3, hasta=0.3))
    casos = [dict(nombre="parado", fijas=["cintura", "espaciador"],
                  fuerzas=[(["bateria"], [0, -3.0, 0]), (["cuello"], [0, -2.0, 0]), (["hombro_1", "hombro_-1"], [0, -4.0, 0])])]
    for s in (1, -1):
        casos.append(dict(nombre=f"torque hombro {s}", fijas=["cintura", "espaciador"],
                          torque=([f"hombro_{s}"], [0, sum(to.HOMBRO_Y) / 2, to.HOMBRO_Z], [1, 0, 0], fp.TORQUE_SERVO)))
    casos.append(dict(nombre="torque cintura", fijas=["espaciador"], torque=(["cintura"], [0, 0, 25.35], [0, 1, 0], fp.TORQUE_SERVO)))
    casos.append(dict(nombre="torque cuello", fijas=["cintura", "espaciador"], torque=(["cuello"], [0, 0, 19.35], [0, 1, 0], fp.TORQUE_SERVO)))
    return L, casos


def main(solo=None):
    os.makedirs(SALIDA, exist_ok=True)
    resultados = json.load(open(RESULTADOS, encoding="utf-8")) if os.path.exists(RESULTADOS) else {}
    trabajos = [(n, fuente(n)) for n in PIEZAS_NX25]
    trabajos.append(("Pelvis", os.path.join(NUEVO, "step", "Pelvis.stp")))
    trabajos.append(("Torso_cuerpo", os.path.join(NUEVO, "step", "Torso_cuerpo.stp")))
    for nombre, stl in trabajos:
        if solo and nombre not in solo:
            continue
        if nombre in resultados and not solo:
            continue
        t0 = time.time()
        try:
            if nombre == "Pelvis":
                lista, casos = interfaces_pelvis()
            elif nombre == "Torso_cuerpo":
                lista, casos = interfaces_torso()
            else:
                lista, servos, horns = interfaces_nx25(nombre)
                casos = casos_nx25(nombre, lista, servos, horns)
            print(f"== {nombre}: {len({i['nombre'] for i in lista})} interfaces, {len(casos)} casos", flush=True)
            # piezas grandes (pies, pelvis, torso): malla de 1 mm para no llenar la RAM
            h = 1.0 if nombre in ("Torso_cuerpo", "Pelvis", "Bracket04_B", "Bracket05_B") else 0.8
            r = fp.aligerar_ventanas(nombre, stl, lista, casos, h=h, carpeta_salida=SALIDA)
            r["segundos"] = round(time.time() - t0)
            r["casos"] = [c["nombre"] for c in casos]
        except Exception as e:
            r = dict(pieza=nombre, error=str(e), traza=traceback.format_exc()[-800:])
        # varios procesos en paralelo: releer antes de escribir para no pisar resultados ajenos
        resultados = json.load(open(RESULTADOS, encoding="utf-8")) if os.path.exists(RESULTADOS) else {}
        resultados[nombre] = r
        json.dump(resultados, open(RESULTADOS, "w", encoding="utf-8"), indent=1)
        print(json.dumps({k: v for k, v in r.items() if k != "traza"}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
