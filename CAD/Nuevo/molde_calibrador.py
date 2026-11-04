"""SEGMENTO: MOLDE CALIBRADOR DE PIERNAS (con el robot ya armado)
Las piernas solo entran si estan rectas. Con el robot prendido en su pose de inicio, se lo acerca al molde por
adelante y se corrige en la app el servo de la parte que no entra o que no apoya. Cada guia delata un servo:
  - bolsillos de los pies (abiertos adelante para entrar deslizando): tobillo lateral mal = pie ladeado
  - topes de afuera y aleta del medio en las rodillas: cadera lateral mal = rodilla corrida de costado
  - dedos de la pared de atras en muslo y canilla: femur o tibia mal = el eslabon no apoya parejo
  - dos topes en las esquinas de atras de la pelvis: el robot no queda inclinado ni girado
Las guias quedan a JUEGO de las caras reales (rayos sobre las mallas en la pose recta de Robot_en_soporte.iam)
y lejos de los horns de femur, tibia, cadera y tobillo.
Entrada: %TEMP%/pose_recta_inventor.json (transformaciones de Robot_en_soporte.iam). Salida: piezas_soportes/.
"""
import json
import os

import manifold3d as mf
import numpy as np
import trimesh
from shapely.geometry import Polygon, box as sbox
from shapely.ops import unary_union

BASE = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(BASE, "piezas_soportes")
POSE = os.path.join(os.environ["TEMP"], "pose_recta_inventor.json")

JUEGO = 0.3            # de cada guia a la cara que controla
BASE_ESP = 4.0         # espesor de la base bajo los pies
CERCO = (3.0, 2.5)     # ancho y alto del cerco de los pies (atras y a los costados; adelante abierto)
PARED_Z = -16.0        # cara de adelante de la pared de atras (detras del pie, z -10.3)
PARED_ESP = 4.0
ANCHO = 64.0           # medio ancho del molde (los postes pasan por fuera de los pies, x 56.2)
# ventanas de contacto (y0, y1, z0, z1 o x0, x1): elegidas sin pernos, horns ni tornillos
DEDOS_ATRAS = {"muslo": (20.0, 35.0, -64.0, -54.0), "canilla": (20.0, 35.0, -110.0, -100.0),
               "pelvis": (23.0, 27.0, -8.0, -3.0)}          # x0, x1, y0, y1 (lado izquierdo; el derecho espejo)
RODILLA = (-88.0, -72.0, 14.0, 40.0)                        # y0, y1, z0, z1 de aleta y topes
POSTE = 5.0            # espesor de los postes de afuera
# en dos mitades (izquierda / derecha del robot) para imprimir en dos impresoras a la vez: se cortan en x = 0 y
# encastran bajando la derecha sobre la izquierda: colas de milano en la base y una lengueta a lo alto de la pared
# (todo con la misma direccion de entrada, vertical); la aleta del medio va entera en la derecha, que es la que baja
# (si quedara en la izquierda, la base de la derecha chocaria con ella al bajar)
COLA = (6.0, 10.0, 6.0)          # cuello, cabeza y largo de cada cola de milano
COLA_JUEGO = 0.15                # por lado
COLAS_BASE_Z = (8.0, 44.0)       # en la base, entre los bolsillos de los pies
LARGO_COLA_BASE = 3.5           # corta: el cerco del pie derecho empieza en x -4.1
LENGUETA = (1.6, 3.0)           # ancho y largo de la lengueta de la pared (a lo alto): entra de arriba, como las colas


def cargar():
    D = json.load(open(POSE))
    cache, mallas = {}, {}
    for d in D:
        if d["stl"] is None or d["nombre"].startswith("Soporte"):
            continue
        if d["stl"] not in cache:
            cache[d["stl"]] = trimesh.load(d["stl"], force="mesh")
        m = cache[d["stl"]].copy()
        m.apply_transform(np.array(d["M"]))
        mallas[d["nombre"]] = m
    for n in ("Torso_cuerpo_B", "Torso_pecho", "Torso_atras_B", "Cabeza_frente", "Cabeza_tapa"):
        for d in D:
            if d["nombre"].startswith(n) and n not in mallas:
                p = os.path.join(BASE, "stl", n + ".stl")
                if os.path.exists(p):
                    m = trimesh.load(p, force="mesh"); m.apply_transform(np.array(d["M"])); mallas[d["nombre"]] = m
    return mallas


def caja(x0, x1, y0, y1, z0, z1):
    return mf.Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def a_manifold(m):
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32), tri_verts=np.asarray(m.faces, np.uint32)))


def rayos(robot, origenes, direccion):
    """distancia minima desde los origenes hasta el robot en la direccion dada"""
    loc, ri, _ = robot.ray.intersects_location(origenes, np.tile(direccion, (len(origenes), 1)), multiple_hits=False)
    if not len(ri):
        return None
    return float(np.min(np.linalg.norm(loc - origenes[ri], axis=1)))


def main():
    os.makedirs(SALIDA, exist_ok=True)
    mallas = cargar()
    robot = trimesh.util.concatenate(list(mallas.values()))
    piernas = trimesh.util.concatenate([m for n, m in mallas.items() if n.split(":")[0] in
                                        ("Bracket01_B", "Bracket02_W", "Bracket03_B", "Bracket04_B", "Bracket05_B",
                                         "Link_W", "Nee_B", "Pipe_M3", "MG90S_grabcad_mg90s9")])
    suelo = min(m.bounds[0][1] for n, m in mallas.items() if n.startswith(("Bracket04_B", "Bracket05_B")))
    print(f"suela de los pies en y {suelo:.2f}")
    piezas = [caja(-ANCHO, ANCHO, suelo - BASE_ESP, suelo, PARED_Z - PARED_ESP, 68.0),          # base
              caja(-ANCHO, ANCHO, suelo - BASE_ESP, -1.0, PARED_Z - PARED_ESP, PARED_Z)]       # pared de atras
    informe = []
    # --- bolsillos de los pies: cerco atras y a los costados, adelante abierto ---
    cercos = []
    for n in ("Bracket04_B:1", "Bracket05_B:1"):
        pie = mallas[n]
        sil = []
        for y in np.arange(suelo + 0.2, suelo + CERCO[1] + 0.25, 0.5):
            s = pie.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
            if s is None:
                continue
            p, T = s.to_2D(to_2D=np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float))
            sil += list(p.polygons_full)
        hueco = unary_union([Polygon(p.exterior) for p in sil]).buffer(JUEGO)     # el pie es una bandeja: solo el contorno
        b = hueco.bounds                                  # x0, z0, x1, z1
        cerco = sbox(b[0] - CERCO[0], b[1] - CERCO[0], b[2] + CERCO[0], b[3] + 5.0).difference(hueco)
        cerco = cerco.difference(sbox(b[0] - 10, b[3] - 25.0, b[2] + 10, b[3] + 10))   # adelante abierto
        for poly in ([cerco] if cerco.geom_type == "Polygon" else list(cerco.geoms)):
            if poly.area < 2:
                continue
            e = trimesh.creation.extrude_polygon(poly, CERCO[1])                     # (u=x, v=z, h=y)
            e.apply_transform(np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float))
            e.apply_translation([0, suelo - 0.01, 0])
            cercos.append(a_manifold(e))
        informe.append(f"bolsillo {n}: {b[2] - b[0]:.1f} x {b[3] - b[1]:.1f} mm (con {JUEGO} de juego)")
    piezas += cercos
    # --- dedos de la pared de atras (muslo, canilla, pelvis): llegan a JUEGO de la cara de atras ---
    for s in (1, -1):
        for nombre, (x0, x1, y0, y1) in DEDOS_ATRAS.items():
            xa, xb = sorted((s * x0, s * x1))
            o = np.array([[x, y, PARED_Z] for x in np.linspace(xa + 0.5, xb - 0.5, 7) for y in np.linspace(y0 + 0.5, y1 - 0.5, 7)])
            d = rayos(robot, o, np.array([0, 0, 1.0]))
            frente = PARED_Z + d - JUEGO
            piezas.append(caja(xa, xb, y0, y1, PARED_Z - 0.01, frente))
            informe.append(f"dedo {nombre} {'izq' if s > 0 else 'der'}: apoya en z {frente + JUEGO:.1f} ({d:.1f} mm desde la pared)")
    # --- rodillas: aleta del medio y topes de afuera ---
    y0, y1, z0, z1 = RODILLA
    o_c = np.array([[0.0, y, z] for y in np.linspace(y0 + 0.5, y1 - 0.5, 7) for z in np.linspace(z0 + 0.5, z1 - 0.5, 9)])
    adentro = min(rayos(piernas, o_c, np.array([1.0, 0, 0])), rayos(piernas, o_c, np.array([-1.0, 0, 0])))
    aleta = adentro - JUEGO
    piezas.append(caja(-aleta, aleta, y0, y1, PARED_Z - 0.01, z1))
    informe.append(f"aleta del medio: {2 * aleta:.1f} mm de ancho (rodillas a {adentro:.1f} del centro)")
    for s in (1, -1):
        o = np.array([[s * (ANCHO - 1.0), y, z] for y in np.linspace(y0 + 0.5, y1 - 0.5, 7) for z in np.linspace(z0 + 0.5, z1 - 0.5, 9)])
        d = rayos(piernas, o, np.array([-s * 1.0, 0, 0]))
        cara = s * (ANCHO - 1.0 - d + JUEGO)
        x_pie = max(abs(v) for n_, m in mallas.items() if n_.startswith(("Bracket04_B", "Bracket05_B")) for v in m.bounds[:, 0])
        xp = x_pie + 1.0                                                                 # el poste pasa por fuera del pie
        xa, xb = sorted((cara, s * (xp + POSTE)))
        piezas.append(caja(xa, xb, y0, y1, z0, z1))                                   # tope
        xa, xb = sorted((s * xp, s * (xp + POSTE)))
        piezas.append(caja(xa, xb, suelo - 0.01, y1, z0, z1))                          # poste hasta la base
        informe.append(f"tope de rodilla {'izq' if s > 0 else 'der'}: cara en x {cara:+.1f}")
    molde = mf.Manifold.batch_boolean(piezas, mf.OpType.Add)
    aleta_caja = caja(-aleta, aleta, y0, y1, PARED_Z, z1 + 1.0)        # para partir: arranca justo en la cara de la pared
    # nada del molde puede tocar el robot en la pose recta (salvo el juego de las guias)
    rob = mf.Manifold.batch_boolean([a_manifold(m) for m in mallas.values()], mf.OpType.Add)
    choque = (molde ^ rob).volume()
    k = molde.to_mesh()
    t = trimesh.Trimesh(k.vert_properties[:, :3], k.tri_verts)
    t.export(os.path.join(SALIDA, "Molde_calibrador.stl"))
    mitades = partir(molde, aleta_caja, suelo)
    for lado, m in mitades.items():
        k = m.to_mesh()
        tm = trimesh.Trimesh(k.vert_properties[:, :3], k.tri_verts)
        tm = max(tm.split(only_watertight=False), key=lambda c: abs(c.volume))   # fuera caras sueltas sin volumen
        tm.export(os.path.join(SALIDA, f"Molde_calibrador_{lado}.stl"))
        informe.append(f"mitad {lado}: {np.round(tm.extents, 1).tolist()} mm, {tm.volume / 1000 * 1.24 * 0.4:.0f} g, "
                       f"cuerpos {len(tm.split(only_watertight=False))}, choque con el robot {(m ^ rob).volume():.2f} mm3")
    informe.append(f"las dos mitades se tocan (deberia ser 0): {(mitades['izq'] ^ mitades['der']).volume():.2f} mm3")
    print("\n".join(informe))
    print(f"molde: {t.extents.round(1).tolist()} mm, {t.volume / 1000 * 1.24 * 0.4:.0f} g aprox (15 % de relleno), "
          f"cuerpos {len(t.split(only_watertight=False))}, choque con el robot {choque:.2f} mm3")
    return t, mallas


def cola(eje_extr, centro, t0, t1, juego=0.0, largo=None):
    """cola de milano que sale de la mitad izquierda (x >= 0) hacia x negativo. En la base es un prisma a lo largo
    de y (forma en x-z); en la pared, a lo largo de z (forma en x-y)."""
    cuello, cabeza, largo_def = COLA
    largo = largo or largo_def
    p = Polygon([(0.5, centro - cuello / 2), (0.5, centro + cuello / 2), (-largo, centro + cabeza / 2), (-largo, centro - cabeza / 2)])
    if juego:
        p = p.buffer(juego, join_style=2)
    e = trimesh.creation.extrude_polygon(p, t1 - t0)                      # (u=x, v=centro, h=extrusion)
    if eje_extr == "y":                                                    # forma en x-z
        e.apply_transform(np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float))
        e.apply_translation([0, t0, 0])
    else:                                                                  # forma en x-y, a lo largo de z
        e.apply_translation([0, 0, t0])
    return a_manifold(e)


def partir(molde, aleta_caja, suelo):
    izq_zona = caja(0.0, 200.0, -300.0, 300.0, -100.0, 200.0) - aleta_caja    # la aleta baja con la derecha
    colas, huecos = [], []
    for z in COLAS_BASE_Z:
        colas.append(cola("y", z, suelo - BASE_ESP, suelo, largo=LARGO_COLA_BASE))
        huecos.append(cola("y", z, suelo - BASE_ESP - 1.0, suelo + 1.0, COLA_JUEGO, largo=LARGO_COLA_BASE))
    ancho, largo = LENGUETA
    zc = PARED_Z - PARED_ESP / 2
    colas.append(caja(-largo, 0.5, suelo - BASE_ESP, -1.0, zc - ancho / 2, zc + ancho / 2))
    huecos.append(caja(-largo - COLA_JUEGO, 0.5, suelo - BASE_ESP - 1.0, 0.0, zc - ancho / 2 - COLA_JUEGO, zc + ancho / 2 + COLA_JUEGO))
    colas = mf.Manifold.batch_boolean(colas, mf.OpType.Add)
    huecos = mf.Manifold.batch_boolean(huecos, mf.OpType.Add)
    izq = (molde ^ izq_zona) + (molde ^ colas)
    der = (molde - izq_zona) - huecos
    return {"izq": izq, "der": der}


if __name__ == "__main__":
    main()
