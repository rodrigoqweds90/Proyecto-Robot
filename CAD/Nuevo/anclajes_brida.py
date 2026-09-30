"""SEGMENTO: PASOS DE BRIDA EN TODAS LAS PIEZAS POR DONDE PASAN CABLES
Busca automaticamente, en cada pieza impresa que toca un tramo del recorrido de cables,
un lugar para dos ranuras pasantes donde una brida de 2.5 mm abrace el mazo:
  - placa de 2 a 6 mm de espesor, paralela al cable
  - ranuras y su contorno (1.2 mm) dentro de material macizo: lejos de agujeros y bordes
  - afuera: lugar libre para el mazo; adentro: lugar libre para que cruce la brida
    (sin piezas vecinas ni servos)
Solo corta material. Si una pieza se usa en varias posiciones (izq/der), se cortan las
ranuras de todas sus posiciones en el mismo modelo.
Coordenadas del robot en mm: X izquierda, Y arriba, Z adelante.
"""
import json
import os
import sys

import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import cables_largo as cl  # noqa: E402
import cables_salida as cs  # noqa: E402

nx = cs.nx
SALIDA = os.path.join(BASE, "piezas_canales")
SERVO_STL = os.path.join(os.environ["TEMP"], "mg90s.stl")

BRIDA_ANCHO = 2.5
RANURA = (BRIDA_ANCHO + 0.5, 1.6)     # (a lo largo del cable, a lo ancho) con juego de impresion
MAZO_ANCHO = 4.2
CONTORNO = 1.2                        # material minimo alrededor de cada ranura
ESPESOR = (2.0, 6.0)
DIST_MAX = 15.0                       # del tramo de cable a la superficie

# piezas que ya se resolvieron a mano
YA_HECHAS = {"Bracket02_W"}


def tramos():
    """(punto a, punto b, cantidad de cables) de todos los recorridos, sin repetir."""
    vistos = {}
    for c in range(16):
        puntos = [np.array([cl.x_canal(c), cl.Y_FICHA, cl.Z_FICHA])] + [np.array(p, float) for p, _ in cl.CANALES[c][1]]
        for a, b in zip(puntos[1:], puntos[2:]):          # el primero va por dentro del torso
            clave = (tuple(np.round(a, 1)), tuple(np.round(b, 1)))
            vistos[clave] = vistos.get(clave, 0) + 1
    return [(np.array(a), np.array(b), n) for (a, b), n in vistos.items()]


def dist_segmento(p, a, b):
    ab = b - a
    t = np.clip(((p - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1), ab / np.linalg.norm(ab)


def caja_orientada(centro, u, w, n, tam):
    b = trimesh.creation.box(extents=tam)
    mat = np.eye(4)
    mat[:3, :3] = np.column_stack([u, w, n])
    mat[:3, 3] = centro
    b.apply_transform(mat)
    return b


def vol_dentro(caja, malla):
    inter = trimesh.boolean.intersection([caja, malla], engine="manifold")
    return inter.volume if not inter.is_empty else 0.0


def buscar(malla, vecinos, a, b, n_cables, semilla=0):
    rng = np.random.default_rng(semilla)
    puntos, caras = trimesh.sample.sample_surface_even(malla, 4000, seed=semilla)
    normales = malla.face_normals[caras]
    d, direccion = dist_segmento(puntos, a, b)
    ok = (d < DIST_MAX) & (np.abs(normales @ direccion) < 0.25)
    if not ok.any():
        return None
    orden = np.argsort(d[ok])[:80]
    puntos, normales, d = puntos[ok][orden], normales[ok][orden], d[ok][orden]
    # espesor de placa: rayo hacia adentro desde la superficie
    origenes = puntos - normales * 0.02
    hits, idx_rayo, _ = malla.ray.intersects_location(origenes, -normales, multiple_hits=False)
    espesor = np.full(len(puntos), np.inf)
    for h, i in zip(hits, idx_rayo):
        espesor[i] = min(espesor[i], np.linalg.norm(h - origenes[i]))
    mazo_alto = 1.25 * n_cables + 0.6
    for i in np.argsort(d + 0.2 * np.abs(espesor - 3.5)):
        t = espesor[i]
        if not (ESPESOR[0] <= t <= ESPESOR[1]):
            continue
        p, n = puntos[i], normales[i]
        u = direccion - (direccion @ n) * n
        u /= np.linalg.norm(u)
        w = np.cross(n, u)
        sep = MAZO_ANCHO / 2 + RANURA[1] / 2 + 0.2
        medio = p - n * t / 2
        # 1) ranuras + contorno dentro de material macizo
        macizo = True
        for s in (-1, 1):
            c = caja_orientada(medio + w * s * sep, u, w, n,
                               [RANURA[0] + 2 * CONTORNO, RANURA[1] + 2 * CONTORNO, t * 0.9])
            if vol_dentro(c, malla) < 0.95 * c.volume:
                macizo = False
                break
        if not macizo:
            continue
        # 2) afuera: mazo libre (ni la propia pieza ni vecinos)
        mazo = caja_orientada(p + n * (mazo_alto / 2 + 0.15), u, w, n, [8.0, MAZO_ANCHO + 2 * RANURA[1] + 1.0, mazo_alto])
        if vol_dentro(mazo, malla) > 0.05 or cs.volumen_choque(mazo, vecinos):
            continue
        # 3) adentro: la brida cruza por la cara de atras de la placa
        paso = caja_orientada(p - n * (t + 0.7), u, w, n, [RANURA[0], 2 * sep + RANURA[1], 1.2])
        if vol_dentro(paso, malla) > 0.05 or cs.volumen_choque(paso, vecinos):
            continue
        ranuras = [caja_orientada(medio + w * s * sep, u, w, n, [RANURA[0], RANURA[1], t + 1.0]) for s in (-1, 1)]
        return dict(punto=p, normal=n, espesor=t, distancia=float(d[i]), ranuras=ranuras)
    return None


def main():
    piezas = cs.piezas_impresas()
    servo = max(trimesh.load(SERVO_STL, force="mesh").split(only_watertight=False), key=lambda m: m.volume)
    servos_w = []
    for m_rot, t in cs.servos():
        s = servo.copy()
        mat = np.eye(4)
        mat[:3, :3], mat[:3, 3] = m_rot, t
        s.apply_transform(mat)
        servos_w.append(("MG90S", s))
    inst = cs.instancias()
    lista_tramos = tramos()
    cortes = {}
    informe = []
    for nombre, mat, malla in inst:
        if nombre in YA_HECHAS or nombre in ("Pipe_B", "Link_W", "Spacer01_W"):
            continue
        cerca = [(a, b, n) for a, b, n in lista_tramos
                 if dist_segmento(malla.vertices[::max(1, len(malla.vertices) // 400)], a, b)[0].min() < DIST_MAX]
        if not cerca:
            continue
        vecinos = [(nn, mm) for nn, mm in piezas if not np.allclose(mm.bounds, malla.bounds)] + servos_w
        # un anclaje por tramo con mas cables primero; no repetir si ya hay uno a < 12 mm
        hechos = []
        for a, b, n_cab in sorted(cerca, key=lambda x: -x[2]):
            r = buscar(malla, vecinos, a, b, n_cab)
            if r is None:
                informe.append(f"{nombre}: sin lugar para brida en tramo {np.round(a)}->{np.round(b)} ({n_cab} cables)")
                continue
            if any(np.linalg.norm(r["punto"] - h) < 12 for h in hechos):
                continue
            hechos.append(r["punto"])
            inv = np.linalg.inv(mat)
            for ran in r["ranuras"]:
                loc = ran.copy()
                loc.apply_transform(inv)
                cortes.setdefault(nombre, []).append(loc)
            informe.append(f"{nombre}: brida para {n_cab} cable(s) en {np.round(r['punto'], 1).tolist()}, placa {r['espesor']:.1f} mm, "
                           f"a {r['distancia']:.1f} mm del recorrido")
    print("\n".join(informe))

    os.makedirs(SALIDA, exist_ok=True)
    resumen = {}
    for nombre, cajas in cortes.items():
        con_salida = os.path.join(BASE, "stl_con_canales", nombre + ".stl")
        origen = con_salida if os.path.exists(con_salida) else os.path.join(nx.BASE, "stl", nombre + ".stl")
        pieza = trimesh.load(origen, force="mesh")
        unicas = []
        for c in cajas:
            if not any(np.allclose(c.bounds, u.bounds, atol=0.1) for u in unicas):
                unicas.append(c)
        nueva = trimesh.boolean.difference([pieza, trimesh.boolean.union(unicas, engine="manifold")], engine="manifold")
        nueva.export(os.path.join(SALIDA, nombre + "_brida.stl"))
        original = trimesh.load(os.path.join(nx.BASE, "stl", nombre + ".stl"), force="mesh")
        resumen[nombre] = dict(ranuras=len(unicas), dv=round(nueva.volume - original.volume, 1), estanco=bool(nueva.is_watertight))
        print(f"{nombre}_brida: {len(unicas)} ranuras, {nueva.volume - original.volume:+.0f} mm3, estanco {nueva.is_watertight}")
    # piezas que solo tienen rebaje de salida (sin brida): se copian con el mismo nombre
    for f in os.listdir(os.path.join(BASE, "stl_con_canales")):
        nombre = os.path.splitext(f)[0]
        if f.endswith(".stl") and nombre not in cortes and nombre not in YA_HECHAS:
            trimesh.load(os.path.join(BASE, "stl_con_canales", f), force="mesh").export(os.path.join(SALIDA, nombre + "_brida.stl"))
            print(f"{nombre}_brida: solo rebaje de salida")
    with open(os.path.join(SALIDA, "resumen.json"), "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, indent=1)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# SEGMENTO: BUSQUEDA POR CARA DE ATRAS (piezas donde el recorrido aproximado no sirve)
# Brida cruzada al largo de la extremidad (vertical) en la cara que mira hacia atras.
# Si del lado de adentro esta el servo, se permite una canaleta de 1.2 mm bajo la brida
# siempre que a la placa le queden 2 mm.
# ---------------------------------------------------------------------------
CANALETA = 1.2
# la rodilla (Nee) y los costados de cadera/tobillo quedan delante del mazo, que pasa por detras
# de las Bracket02: ahi no va brida (jalaria el cable hacia adelante)
PIEZAS_ATRAS = ("Bracket09_W", "Bracket10_W")
CONTORNO_ATRAS = 0.8                   # 2 lineas de 0.4 alrededor de cada ranura


def buscar_atras(malla, vecinos, largo=np.array([0, 1.0, 0]), atras=np.array([0, 0, -1.0]), semilla=0):
    puntos, caras = trimesh.sample.sample_surface_even(malla, 6000, seed=semilla)
    normales = malla.face_normals[caras]
    ok = (normales @ atras > 0.7) & (np.abs(normales @ largo) < 0.3)
    if not ok.any():
        return None
    puntos, normales = puntos[ok], normales[ok]
    origenes = puntos - normales * 0.02
    hits, idx_rayo, _ = malla.ray.intersects_location(origenes, -normales, multiple_hits=False)
    espesor = np.full(len(puntos), np.inf)
    for h, i in zip(hits, idx_rayo):
        espesor[i] = min(espesor[i], np.linalg.norm(h - origenes[i]))
    centro = malla.bounds.mean(axis=0)
    orden = np.argsort(-(puntos @ atras) + 0.3 * np.abs(espesor - 3.5))     # lo mas atras primero
    mazo_alto = 1.25 * 2 + 0.6          # por rodilla, tobillo y brazo pasan hasta 2 cables
    for i in orden:
        t = espesor[i]
        if not (ESPESOR[0] <= t <= ESPESOR[1]):
            continue
        p, n = puntos[i], normales[i]
        u = largo - (largo @ n) * n
        u /= np.linalg.norm(u)
        w = np.cross(n, u)
        sep = MAZO_ANCHO / 2 + RANURA[1] / 2 + 0.2
        medio = p - n * t / 2
        contorno = CONTORNO_ATRAS
        if any(vol_dentro(caja_orientada(medio + w * s * sep, u, w, n,
                                         [RANURA[0] + 2 * contorno, RANURA[1] + 2 * contorno, t * 0.9]), malla)
               < 0.97 * (RANURA[0] + 2 * contorno) * (RANURA[1] + 2 * contorno) * t * 0.9 for s in (-1, 1)):
            continue
        mazo = caja_orientada(p + n * (mazo_alto / 2 + 0.15), u, w, n, [5.0, MAZO_ANCHO + 2 * RANURA[1] + 0.6, mazo_alto])
        if vol_dentro(mazo, malla) > 0.05 or cs.volumen_choque(mazo, vecinos):
            continue
        cortes_extra = []
        paso = caja_orientada(p - n * (t + 0.7), u, w, n, [RANURA[0], 2 * sep + RANURA[1], 1.2])
        if vol_dentro(paso, malla) > 0.05 or cs.volumen_choque(paso, vecinos):
            if t - CANALETA < 2.0:
                continue
            canaleta = caja_orientada(p - n * (t - CANALETA / 2), u, w, n, [RANURA[0], 2 * sep + RANURA[1], CANALETA + 0.02])
            paso2 = caja_orientada(p - n * (t - CANALETA / 2), u, w, n, [RANURA[0], 2 * sep + RANURA[1], CANALETA])
            if cs.volumen_choque(paso2, [v for v in vecinos if v[0] != "MG90S"]):
                continue
            # la canaleta deja 1.2 mm libres aunque adentro este el servo apoyado
            cortes_extra.append(canaleta)
        ranuras = [caja_orientada(medio + w * s * sep, u, w, n, [RANURA[0], RANURA[1], t + 1.0]) for s in (-1, 1)]
        return dict(punto=p, normal=n, espesor=t, ranuras=ranuras + cortes_extra, canaleta=bool(cortes_extra))
    return None


def main_atras():
    piezas = cs.piezas_impresas()
    servo = max(trimesh.load(SERVO_STL, force="mesh").split(only_watertight=False), key=lambda m: m.volume)
    servos_w = []
    for m_rot, t in cs.servos():
        s = servo.copy()
        mat = np.eye(4)
        mat[:3, :3], mat[:3, 3] = m_rot, t
        s.apply_transform(mat)
        servos_w.append(("MG90S", s))
    cortes = {}
    for nombre, mat, malla in cs.instancias():
        if nombre not in PIEZAS_ATRAS:
            continue
        vecinos = [(nn, mm) for nn, mm in piezas if not np.allclose(mm.bounds, malla.bounds)] + servos_w
        r = buscar_atras(malla, vecinos)
        lado = "izq" if malla.bounds.mean(axis=0)[0] > 0 else "der"
        altura = malla.bounds.mean(axis=0)[1]
        if r is None:
            print(f"{nombre} ({lado}, y {altura:.0f}): sin lugar en la cara de atras")
            continue
        inv = np.linalg.inv(mat)
        for c in r["ranuras"]:
            loc = c.copy()
            loc.apply_transform(inv)
            cortes.setdefault(nombre, []).append(loc)
        print(f"{nombre} ({lado}, y {altura:.0f}): brida en {np.round(r['punto'], 1).tolist()}, placa {r['espesor']:.1f} mm"
              f"{', con canaleta bajo la brida' if r['canaleta'] else ''}")
    for nombre, cajas in cortes.items():
        previa = os.path.join(SALIDA, nombre + "_brida.stl")
        con_salida = os.path.join(BASE, "stl_con_canales", nombre + ".stl")
        origen = previa if os.path.exists(previa) else (con_salida if os.path.exists(con_salida) else os.path.join(nx.BASE, "stl", nombre + ".stl"))
        pieza = trimesh.load(origen, force="mesh")
        unicas = []
        for c in cajas:
            if not any(np.allclose(c.bounds, u.bounds, atol=0.1) for u in unicas):
                unicas.append(c)
        nueva = trimesh.boolean.difference([pieza, trimesh.boolean.union(unicas, engine="manifold")], engine="manifold")
        nueva.export(previa)
        original = trimesh.load(os.path.join(nx.BASE, "stl", nombre + ".stl"), force="mesh")
        print(f"{nombre}_brida: {nueva.volume - original.volume:+.0f} mm3 respecto del original, estanco {nueva.is_watertight}")
