"""SEGMENTO: BARRIDO DE MOVIMIENTO (choques de cada articulacion en todo el rango del servo)
Los servos son de 180 grados y 90 es la posicion de parado derecho (piernas rectas, brazos colgando).
Para cada uno de los 16 servos mueve su articulacion de 0 a 180 (los demas quietos en 90) y busca choques
nuevos entre piezas (volumen de interseccion por encima del que ya hay en la pose de 90: contactos de pernos,
horns, etc.). Reporta el rango libre de choque de cada servo y que pieza choca primero.
Cinematica (desde la pelvis, anclada):
  - articulacion simple: gira todo lo que queda del otro lado (cintura, cuello, hombros, codos, caderas, tobillos)
  - paralelogramo (muslo y canilla del NX25): los dos eslabones giran cada uno sobre su perno de la base y
    todo lo de abajo se traslada (el pie queda paralelo a la pelvis)
Mallas: las mismas piezas del ensamble (STL); PCA9685 y ESP32 como su caja; cajas de bateria, fichas, etc.
Uso: python barrido_movimiento.py  (con ROBOT_VARIANTE=B para el modelo B)
"""
import collections
import os
import sys

import manifold3d as mf
import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import torso_estudio as te  # noqa: E402
import uniones as un  # noqa: E402

PASO = 5.0                      # grados
TOLERANCIA = 2.0                # mm3 de mas sobre el contacto de la pose de 90 para contar como choque
TOLERANCIA_REL = 0.5            # ...y mas de la mitad del contacto que ya habia (caras que se tocan en el eje)


def es_choque(vol, base):
    return vol - base > max(TOLERANCIA, TOLERANCIA_REL * base)
CAJAS_LOCALES = {               # piezas armadas en Inventor: su caja en coordenadas del modelo
    "PCA9685_adafruit_815": ((-1.91, -6.48, -2.01), (60.33, 18.92, 10.09)),
    "ESP32_devkit_v1_30pin": ((-2.44, -3.71, -10.17), (26.57, 49.37, 3.25)),
}


# ---------------------------------------------------------------------------
# SEGMENTO: MALLAS DE LAS PIEZAS
# ---------------------------------------------------------------------------
def malla_local(ruta):
    base = os.path.splitext(os.path.basename(ruta))[0]
    if base in CAJAS_LOCALES:
        a, b = (np.array(v) for v in CAJAS_LOCALES[base])
        m = trimesh.creation.box(extents=b - a)
        m.apply_translation((a + b) / 2)
        return m
    for r, tam, _ in te.CAJAS.values():
        if os.path.basename(r) == os.path.basename(ruta):
            m = trimesh.creation.box(extents=tam)
            m.apply_translation(np.array(tam) / 2)
            return m
    carpeta = os.path.dirname(ruta)
    if os.path.isabs(ruta):
        candidatos = [os.path.join(BASE, "piezas_estilo", base + ".stl"), os.path.join(carpeta, base + ".stl"),
                      os.path.join(carpeta, "stl", base + ".stl"), os.path.join(BASE, "stl", base + ".stl")]
    else:   # pieza del NX25: la misma prioridad que torso_estudio (forma nueva > pernos M3 > bridas > original)
        candidatos = [os.path.join(BASE, "piezas_estilo", base + ".stl"), os.path.join(BASE, "piezas_rediseno", base + ".stl"),
                      os.path.join(BASE, "piezas_m3", base + ".stl"),
                      os.path.join(BASE, "piezas_canales", base + "_brida.stl"), os.path.join(te.nx.BASE, "stl", base + ".stl")]
    for c in candidatos:
        if os.path.exists(c):
            return trimesh.load(c, force="mesh")
    raise FileNotFoundError(ruta)


def ruta_ipt(ruta):
    """el .ipt que usa el ensamble para esa pieza (misma prioridad que torso_estudio)."""
    if os.path.isabs(ruta):
        estilo = os.path.join(BASE, "piezas_estilo", os.path.basename(ruta))
        return estilo if os.path.exists(estilo) else ruta
    base = os.path.basename(ruta)
    for c in (os.path.join(BASE, "piezas_estilo", base + ".ipt"), os.path.join(BASE, "piezas_rediseno", base + ".ipt"),
              os.path.join(BASE, "piezas_m3", base + ".ipt"),
              os.path.join(BASE, "piezas_canales", base + "_brida.ipt")):
        if os.path.exists(c):
            return c
    return os.path.join(te.nx.BASE, base + ".ipt")


def a_manifold(m):
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32), tri_verts=np.asarray(m.faces, np.uint32)))


def cargar():
    P = un.piezas()
    rutas = [n for n, _, _ in te.ensamble()]
    cache, piezas = {}, []
    for p, ruta in zip(P, rutas):
        if ruta not in cache:
            cache[ruta] = malla_local(ruta)
        m = cache[ruta].copy()
        M = np.eye(4)
        M[:3, :3], M[:3, 3] = p["M"], p["t"]
        m.apply_transform(M)
        piezas.append(m)
    return P, piezas


# ---------------------------------------------------------------------------
# SEGMENTO: CINEMATICA
# ---------------------------------------------------------------------------
def rotacion(eje, grados, centro):
    T = trimesh.transformations.rotation_matrix(np.radians(grados), eje, centro)
    return T


def estructura(P):
    host = un.rigidas(P)
    giros = un.uniones_giratorias(P, host)
    g = lambda i: host.get(i, i)
    raiz = g(next(i for i, p in enumerate(P) if p["nombre"] == "Pelvis"))
    grupos = collections.defaultdict(list)
    for i in range(len(P)):
        grupos[g(i)].append(i)
    aristas = [(g(u["a"]), g(u["b"]), u) for u in giros]
    return host, giros, g, raiz, grupos, aristas


def alcanzables(raiz, aristas, sin=None):
    vecinos = collections.defaultdict(set)
    for a, b, u in aristas:
        if u is not sin:
            vecinos[a].add(b)
            vecinos[b].add(a)
    vistos, pila = {raiz}, [raiz]
    while pila:
        x = pila.pop()
        for y in vecinos[x] - vistos:
            vistos.add(y)
            pila.append(y)
    return vistos


def articulaciones(P, g, raiz, aristas):
    """una entrada por servo: (nombre, tipo, datos). tipo 'simple' o 'paralelogramo'."""
    todos = {a for a, _, _ in aristas} | {b for _, b, _ in aristas}
    lista = []
    for a, b, u in aristas:
        if u["tipo"] not in ("horn", "cuello"):
            continue
        lado = alcanzables(raiz, aristas, sin=u)
        if len(lado) < len(todos):          # simple: gira lo que queda del otro lado
            mueve = todos - lado
            lista.append(dict(u=u, tipo="simple", mueve=mueve))
            continue
        # paralelogramo: el eslabon es el grupo del servo o del horn que tiene 2 pernos/uniones
        grado = collections.Counter([x for a2, b2, _ in aristas for x in (a2, b2)])
        eslabon = a if grado[a] == 2 else b
        # base y punta: los dos grupos a los que se une el eslabon; la base es la mas cercana a la pelvis
        ext = [(x2 if y2 == eslabon else y2, uu) for x2, y2, uu in aristas if eslabon in (x2, y2)]
        (g1, u1), (g2, u2) = ext
        # el otro eslabon: comparte los mismos dos grupos
        otro_esl = [e for e in todos if e != eslabon and grado[e] == 2 and
                    {x2 if y2 == e else y2 for x2, y2, _ in aristas if e in (x2, y2)} == {g1, g2}]
        # base = la que sigue unida a la pelvis sin pasar por los eslabones
        sin_ambos = alcanzables(raiz, [(x, y, uu) for x, y, uu in aristas if eslabon not in (x, y) and (not otro_esl or otro_esl[0] not in (x, y))])
        base, punta = (g1, g2) if g1 in sin_ambos else (g2, g1)
        pb = u1["c"] if g1 == base else u2["c"]
        pt = u2["c"] if g1 == base else u1["c"]
        abajo = todos - sin_ambos - {eslabon} - set(otro_esl)
        pernos_otro = []
        for e in otro_esl:
            for x2, y2, uu in aristas:
                if e in (x2, y2) and (x2 == base or y2 == base):
                    pernos_otro.append((e, uu["c"]))
        lista.append(dict(u=u, tipo="paralelogramo", eslabon=eslabon, pivote=pb, punta=pt, eje=u["d"],
                          otros=pernos_otro, abajo=abajo, base=base))
    return lista


def angulo_actual(art):
    """paralelogramo: angulo del eslabon respecto de la vertical (recto = 0), medido sobre su eje."""
    d = art["eje"] / np.linalg.norm(art["eje"])
    v = art["punta"] - art["pivote"]
    v = v - (v @ d) * d
    abajo = np.array([0, -1.0, 0])
    abajo = abajo - (abajo @ d) * d
    return np.degrees(np.arctan2(d @ np.cross(abajo, v), abajo @ v))


def transformaciones(art, grupos, dtheta):
    """dict indice de pieza -> matriz 4x4 para girar la articulacion dtheta grados desde la pose del ensamble."""
    T = {}
    if art["tipo"] == "simple":
        R = rotacion(art["u"]["d"], dtheta, art["u"]["c"])
        for grp in art["mueve"]:
            for i in grupos[grp]:
                T[i] = R
        return T
    R = rotacion(art["eje"], dtheta, art["pivote"])
    for i in grupos[art["eslabon"]]:
        T[i] = R
    for e, c in art["otros"]:
        Re = rotacion(art["eje"], dtheta, c)
        for i in grupos[e]:
            T[i] = Re
    v = art["punta"] - art["pivote"]
    desplazamiento = R[:3, :3] @ v - v
    Tt = np.eye(4)
    Tt[:3, 3] = desplazamiento
    for grp in art["abajo"]:
        for i in grupos[grp]:
            T[i] = Tt
    return T


# ---------------------------------------------------------------------------
# SEGMENTO: CHOQUES
# ---------------------------------------------------------------------------
def pares_a_revisar(T, n):
    """pares (i, j) cuya posicion relativa cambia con la articulacion."""
    clase = {}
    for i in range(n):
        m = T.get(i)
        clase[i] = None if m is None else id(m)
    return [(i, j) for i in range(n) for j in range(i + 1, n) if clase[i] != clase[j]]


def cajas_se_tocan(a, b):
    return np.all(a[0] <= b[1] + 0.01) and np.all(b[0] <= a[1] + 0.01)


def volumenes(piezas_m, cajas, pares):
    out = {}
    for i, j in pares:
        if cajas_se_tocan(cajas[i], cajas[j]):
            v = (piezas_m[i] ^ piezas_m[j]).volume()
            if v > 0.05:
                out[(i, j)] = v
    return out


def barrer(P, piezas, art, grupos, nombre):
    n = len(piezas)
    base_m = [a_manifold(m) for m in piezas]
    T0 = transformaciones(art, grupos, 0.0)
    pares = pares_a_revisar(T0, n)
    cajas0 = [m.bounds for m in piezas]
    base_v = volumenes(base_m, cajas0, pares)
    actual = angulo_actual(art) if art["tipo"] == "paralelogramo" else 0.0
    resultado = {}
    for sentido in (1, -1):
        choque = None
        ang = 90.0
        while True:
            ang_nuevo = ang + sentido * PASO
            if ang_nuevo < 0 - 1e-6 or ang_nuevo > 180 + 1e-6:
                break
            dtheta = (ang_nuevo - 90.0) - actual        # relativo a la pose del ensamble
            T = transformaciones(art, grupos, dtheta)
            movidas, cajas = [], []
            for i in range(n):
                if i in T:
                    M = T[i]
                    movidas.append(base_m[i].transform(M[:3, :4]))
                    c = trimesh.bounds.corners(cajas0[i]) @ M[:3, :3].T + M[:3, 3]
                    cajas.append((c.min(0), c.max(0)))
                else:
                    movidas.append(base_m[i])
                    cajas.append((cajas0[i][0], cajas0[i][1]))
            v = volumenes(movidas, cajas, pares)
            nuevos = [(par, vol - base_v.get(par, 0.0)) for par, vol in v.items() if es_choque(vol, base_v.get(par, 0.0))]
            if nuevos:
                par, vol = max(nuevos, key=lambda x: x[1])
                choque = (ang_nuevo, P[par[0]]["nombre"], P[par[1]]["nombre"], round(vol, 1))
                break
            ang = ang_nuevo
        resultado[sentido] = (ang, choque)
    return actual, resultado


def nombre_articulacion(P, g, art):
    u = art["u"]
    a, b = P[u["a"]]["nombre"], P[u["b"]]["nombre"]
    c = u["c"]
    lado = "izq" if c[0] > 1 else ("der" if c[0] < -1 else "")
    if u["tipo"] == "cuello":
        return "cuello (giro de la cabeza)"
    if abs(c[1] - 0) < 6 and abs(c[0]) < 1:
        return "cintura (giro del torso)"
    if art["tipo"] == "paralelogramo":
        return f"{'muslo (cadera adelante-atras)' if c[1] > -80 else 'rodilla'} {lado}"
    if c[1] < -120:
        return f"tobillo (lateral) {lado}"
    if -30 < c[1] < -20:
        return f"cadera (lateral) {lado}"
    if abs(c[0]) > 85:
        return f"codo {lado}"
    if abs(c[0]) > 60:
        return f"hombro (abrir brazo) {lado}"
    return f"hombro (adelante-atras) {lado}"


def main():
    P, piezas = cargar()
    host, giros, g, raiz, grupos, aristas = estructura(P)
    arts = articulaciones(P, g, raiz, aristas)
    print(f"{len(piezas)} piezas, {len(arts)} servos\n")
    print(f"{'servo':34s} {'pose CAD':>8s}  {'rango libre (0-180)':>20s}  primer choque")
    for art in arts:
        nombre = nombre_articulacion(P, g, art)
        actual, res = barrer(P, piezas, art, grupos, nombre)
        (a_max, c_max), (a_min, c_min) = res[1], res[-1]
        txt = []
        for c in (c_min, c_max):
            if c:
                txt.append(f"a {c[0]:.0f}: {c[1]} con {c[2]} ({c[3]} mm3)")
        print(f"{nombre:34s} {90 + actual:8.0f}  {a_min:8.0f} a {a_max:5.0f}      {' | '.join(txt) if txt else 'sin choques'}", flush=True)


if __name__ == "__main__":
    main()
