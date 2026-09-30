"""SEGMENTO: SOPORTES DE ARMADO (poner los horns con las piernas rectas sin medir a ojo)
Con los servos en 90 (comando CENTRAR del firmware) cada articulacion de la pierna tiene que quedar recta.
  - Soporte_pierna_izq / _der: la pierna recta acostada sobre su lado de afuera en un hueco con su forma
    exacta (mapa de alturas: el contorno de afuera de la pierna + 0.3 mm), la cara de adentro queda arriba
    para poner los horns de muslo y rodilla y sus tornillos centrales.
  - Soporte_parado: base con el cerco de los dos pies y una pared entre las piernas que sostiene la pelvis a
    la altura de pierna recta; con las piernas ya en la pelvis se ponen los horns de cadera y tobillo (atras).
Pose recta = servos en 90: muslo y rodilla con los eslabones verticales, cadera y tobillo laterales en 0.
Salida: piezas_soportes/*.stl y .ipt, ensamble Soportes_armado.iam y vistas_torso/soportes_*.png.
"""
import os
import sys

import numpy as np
import trimesh
from scipy import ndimage

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import barrido_movimiento as bm  # noqa: E402
import poses_marcha as pm  # noqa: E402

SALIDA = os.path.join(BASE, "piezas_soportes")
PASO = 0.4                  # mm de la grilla del mapa de alturas
JUEGO = 0.3                 # entre la pieza y el molde
PROFUNDO = 10.0             # cuanto entra la pierna en el molde (desde su punto mas afuera)
PISO = 2.5                  # espesor del molde debajo del punto mas afuera de la pierna
BORDE = 5.0                 # ancho del borde alrededor de la silueta; mas afuera solo queda el piso
AGUJERO_PERNO = 9.2         # agujero pasante del molde en cada perno (rebaje del Pipe 8.6 y cabeza M3 5.7)
# soporte de parado
BASE_PARADO = 4.0           # espesor de la base bajo los pies
CERCO = (2.5, 3.0)          # ancho y alto del cerco alrededor de cada pie
PARED_X = 3.0               # medio ancho de la pared entre las piernas (libre hasta 4 en todo el alto)
PARED_Z = (0.0, 43.0)       # tramo de la pelvis que apoya en la pared (bordes de adelante y atras)


# ---------------------------------------------------------------------------
# SEGMENTO: POSE RECTA
# ---------------------------------------------------------------------------
def pose_recta():
    P, piezas = bm.cargar()
    host, giros, g, raiz, grupos, aristas = bm.estructura(P)
    arts = bm.articulaciones(P, g, raiz, aristas)
    info = pm.calibrar(P, piezas, arts, grupos)
    claves = ("muslo", "rodilla", "cadera (lateral)", "tobillo")
    T = pm.pose(info, grupos, {a["nombre"]: 0.0 for a in info if any(k in a["nombre"] for k in claves)}, len(piezas))
    piernas = {}
    for a in info:
        if "cadera (lateral)" in a["nombre"]:
            piernas[a["lado"]] = sorted(a["idx"])
    pelvis = next(i for i, p in enumerate(P) if p["nombre"] == "Pelvis")
    rectas = []
    for i, m in enumerate(piezas):
        q = m.copy()
        q.apply_transform(T[i])
        rectas.append(q)
    return P, rectas, T, piernas, pelvis


# ---------------------------------------------------------------------------
# SEGMENTO: MALLA DESDE UN MAPA DE ALTURAS (solido cerrado)
# ---------------------------------------------------------------------------
def solido_alturas(Y, Z, arriba, abajo, a_mundo):
    """arriba[j, k] y abajo (escalar) en la coordenada 'u'; a_mundo(u, y, z) -> punto del mundo."""
    ny, nz = arriba.shape
    idx = lambda j, k, cara: (cara * ny + j) * nz + k
    V = np.zeros((2 * ny * nz, 3))
    for cara, u in ((0, arriba), (1, np.full_like(arriba, abajo))):
        for j in range(ny):
            V[cara * ny * nz + j * nz: cara * ny * nz + (j + 1) * nz] = a_mundo(u[j], Y[j], Z)
    F = []
    for j in range(ny - 1):
        for k in range(nz - 1):
            a, b, c, d = idx(j, k, 0), idx(j + 1, k, 0), idx(j + 1, k + 1, 0), idx(j, k + 1, 0)
            F += [(a, b, c), (a, c, d)]
            a, b, c, d = idx(j, k, 1), idx(j + 1, k, 1), idx(j + 1, k + 1, 1), idx(j, k + 1, 1)
            F += [(a, c, b), (a, d, c)]
    borde = [(j, 0) for j in range(ny)] + [(ny - 1, k) for k in range(1, nz)] + \
            [(j, nz - 1) for j in range(ny - 2, -1, -1)] + [(0, k) for k in range(nz - 2, 0, -1)]
    for (j0, k0), (j1, k1) in zip(borde, borde[1:] + borde[:1]):
        a, b = idx(j0, k0, 0), idx(j1, k1, 0)
        c, d = idx(j1, k1, 1), idx(j0, k0, 1)
        F += [(a, d, c), (a, c, b)]
    m = trimesh.Trimesh(V, np.array(F), process=True)
    trimesh.repair.fix_normals(m)
    return m


# ---------------------------------------------------------------------------
# SEGMENTO: SOPORTE DE PIERNA
# ---------------------------------------------------------------------------
def ejes_pernos(P, rectas, idx):
    """(y, z) de cada perno de la pierna con eje en x (atraviesa el molde): centro del Pipe_M3."""
    ejes = set()
    for i in idx:
        if not P[i]["nombre"].startswith("Pipe_M3"):
            continue
        m = rectas[i]
        c = m.center_mass
        _, v = np.linalg.eigh(np.cov((m.vertices - c).T))
        if abs(v[0, 0]) > 0.9:
            ejes.add((round(c[1], 1), round(c[2], 1)))
    return sorted(ejes)


def soporte_pierna(rectas, idx, lado, ejes=()):
    """lado +1: pierna izquierda (afuera = +x); -1: derecha.
    ejes: (y, z) de los pernos; el molde lleva un agujero pasante en cada uno, porque la pierna se arma con los
    tornillos ya puestos y sus cabezas (o las del Pipe) chocaban con los bultos del molde dentro de los rebajes."""
    pierna = trimesh.util.concatenate([rectas[i] for i in idx])
    (x0, y0, z0), (x1, y1, z1) = pierna.bounds
    Y = np.arange(y0 - BORDE - 1, y1 + BORDE + 1, PASO)
    Z = np.arange(z0 - BORDE - 1, z1 + BORDE + 1, PASO)
    yy, zz = np.meshgrid(Y, Z, indexing="ij")
    x_lejos = (x1 + 20) if lado > 0 else (x0 - 20)
    origenes = np.c_[np.full(yy.size, x_lejos), yy.ravel(), zz.ravel()]
    dirs = np.tile([-lado, 0.0, 0.0], (yy.size, 1))
    locs, rayos, _ = pierna.ray.intersects_location(origenes, dirs, multiple_hits=False)
    u = np.full(yy.size, -np.inf)                       # u = lado * x: mas grande = mas afuera
    u[rayos] = lado * locs[:, 0]
    u = ndimage.maximum_filter(u.reshape(yy.shape), size=3)   # conservador entre puntos de la grilla
    hay = np.isfinite(u)
    u_max = u[hay].max()
    fondo = u_max + PISO
    borde_libre = u_max - PROFUNDO
    arriba = np.where(hay, np.maximum(u + JUEGO, borde_libre), borde_libre)
    lejos = ndimage.distance_transform_edt(~hay) * PASO > BORDE
    arriba = np.where(lejos, fondo - PISO, arriba)      # lejos de la pierna solo queda el piso
    arriba = np.minimum(arriba, fondo - 0.8)
    a_mundo = lambda uu, y, z: np.c_[lado * uu, np.full_like(z, y), z]
    molde = solido_alturas(Y, Z, arriba, fondo, a_mundo)
    if ejes:
        largo = (fondo - borde_libre) + 20
        x_c = lado * (fondo + borde_libre) / 2
        agujeros = []
        for y, z in ejes:
            c = trimesh.creation.cylinder(radius=AGUJERO_PERNO / 2, height=largo, sections=48)
            c.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
            c.apply_translation([x_c, y, z])
            agujeros.append(c)
        molde = trimesh.boolean.difference([molde, trimesh.util.concatenate(agujeros)], engine="manifold")
    return molde


# ---------------------------------------------------------------------------
# SEGMENTO: SOPORTE DE PARADO
# ---------------------------------------------------------------------------
def soporte_parado(rectas, piernas, pelvis, P):
    import manifold3d as mf
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    pies = [i for lado in piernas for i in piernas[lado] if P[i]["nombre"] in ("Bracket04_B", "Bracket05_B")]
    y_suelo = min(rectas[i].bounds[0][1] for i in pies)
    m = mf.Manifold()
    huellas = []
    for i in pies:
        mm = rectas[i]
        bajo = mm.triangles[mm.triangles[:, :, 1].min(axis=1) < y_suelo + CERCO[1] + 0.5]
        huella = unary_union([Polygon(t[:, [0, 2]]).buffer(0) for t in bajo if Polygon(t[:, [0, 2]]).area > 1e-6])
        huellas.append(huella.buffer(JUEGO + 0.1).simplify(0.05))
    def extruir(poly, y0, y1):
        partes = poly.geoms if hasattr(poly, "geoms") else [poly]
        total = mf.Manifold()
        for g in partes:
            anillos = [np.asarray(g.exterior.coords)[:-1][:, ::-1]] + [np.asarray(r.coords)[:-1][:, ::-1] for r in g.interiors]
            e = mf.Manifold.extrude(mf.CrossSection(anillos, mf.FillRule.EvenOdd), y1 - y0)      # plano (z, x) -> altura
            e = e.transform([[0, 1, 0, 0], [0, 0, 1, y0], [1, 0, 0, 0]])                          # (z, x, h) -> (x, y, z)
            total = total + e
        return total
    # base: rectangulo bajo los dos pies
    todos = unary_union(huellas)
    x0, z0, x1, z1 = todos.bounds
    base_poly = Polygon([(x0 - 6, z0 - 6), (x1 + 6, z0 - 6), (x1 + 6, z1 + 6), (x0 - 6, z1 + 6)])
    m = extruir(base_poly, y_suelo - BASE_PARADO, y_suelo)
    for h in huellas:
        cerco = h.buffer(CERCO[0]).difference(h)
        m = m + extruir(cerco, y_suelo - 0.01, y_suelo + CERCO[1])
    # pared entre las piernas: apoya en los bordes de adelante y de atras de la pelvis (lo mas bajo que tiene entre
    # las piernas); al centro queda libre el horn en cruz de la cintura, que va bajo la placa de arriba
    pel = rectas[pelvis]
    Zs = np.arange(PARED_Z[0], PARED_Z[1] + 0.01, 0.5)
    hits = []
    for z in Zs:
        for x in (-PARED_X, 0.0, PARED_X):
            locs, _, _ = pel.ray.intersects_location([[x, y_suelo, z]], [[0, 1.0, 0]], multiple_hits=False)
            if len(locs):
                hits.append(locs[0][1])
    techo = min(hits) - JUEGO
    perfil = [(Zs[0], y_suelo - 0.01), (Zs[-1], y_suelo - 0.01), (Zs[-1], techo), (Zs[0], techo)]
    anillo = np.array([(y, z) for z, y in perfil])                                                 # (y, z)
    pared = mf.Manifold.extrude(mf.CrossSection([anillo], mf.FillRule.EvenOdd), 2 * PARED_X)      # (y, z, h)
    pared = pared.transform([[0, 0, 1, -PARED_X], [1, 0, 0, 0], [0, 1, 0, 0]])                     # -> (h, y, z)
    m = m + pared
    r = m.to_mesh()
    return trimesh.Trimesh(r.vert_properties[:, :3], r.tri_verts), y_suelo


def horns_pierna(P, T):
    """(lado, centro) del horn de muslo y de rodilla de cada pierna, en la pose recta."""
    _, piezas = bm.cargar()
    host, giros, g, raiz, grupos, aristas = bm.estructura(P)
    fuera = []
    for art in bm.articulaciones(P, g, raiz, aristas):
        nombre = bm.nombre_articulacion(P, None, art)
        if art["tipo"] != "paralelogramo":
            continue
        c = np.asarray(art["u"]["c"], float)
        i = next(iter(bm.transformaciones(art, grupos, 1.0)))       # una pieza que gira con ese horn
        c = T[i][:3, :3] @ c + T[i][:3, 3]
        fuera.append((1 if c[0] > 0 else -1, c))
    return fuera


def main():
    os.makedirs(SALIDA, exist_ok=True)
    P, rectas, T, piernas, pelvis = pose_recta()
    salida = {}
    for lado, sufijo in ((1, "izq"), (-1, "der")):
        s = soporte_pierna(rectas, piernas[lado], lado, ejes_pernos(P, rectas, piernas[lado]))
        salida[f"Soporte_pierna_{sufijo}"] = s
    parado, y_suelo = soporte_parado(rectas, piernas, pelvis, P)
    salida["Soporte_parado"] = parado
    for nombre, m in salida.items():
        m.export(os.path.join(SALIDA, nombre + ".stl"))
        # que no choque con la pierna recta
        otras = [rectas[i] for lado in piernas for i in piernas[lado]] + ([rectas[pelvis]] if nombre == "Soporte_parado" else [])
        choque = sum(trimesh.boolean.intersection([m, o], engine="manifold").volume for o in otras
                     if bm.cajas_se_tocan(m.bounds, o.bounds))
        print(f"{nombre}: valido {m.is_volume} | {m.volume / 1000:.1f} cm3 (~{m.volume / 1000 * 1.24 * 0.35:.0f} g al 15%) | "
              f"caja {np.round(m.extents, 1).tolist()} | choque con el robot {choque:.2f} mm3")
    np.save(os.path.join(SALIDA, "pose_recta.npy"), np.array(T))




# ---------------------------------------------------------------------------
# SEGMENTO: VISTAS EN INVENTOR (piernas rectas con sus soportes)
# ---------------------------------------------------------------------------
def vistas():
    import pythoncom
    import pywintypes
    from win32com.client import dynamic, gencache
    import torso_estudio as te
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    k = __import__("win32com.client", fromlist=["constants"]).constants
    tg = app.TransientGeometry
    P, rectas, T, piernas, pelvis = pose_recta()
    rutas = [n for n, _, _ in te.ensamble()]
    ipts = {}
    for nombre in ("Soporte_pierna_izq", "Soporte_pierna_der", "Soporte_parado"):
        d = dynamic.Dispatch(app.Documents.Open(os.path.join(SALIDA, nombre + ".stl"), False)._oleobj_)
        ruta = os.path.join(SALIDA, nombre + ".ipt")
        if os.path.exists(ruta):
            os.remove(ruta)
        d.SaveAs(ruta, False)
        d.Close(True)
        ipts[nombre] = ruta
    for escena, soportes in (("soportes_pierna", ("Soporte_pierna_izq", "Soporte_pierna_der")), ("soporte_parado", ("Soporte_parado",))):
        doc = dynamic.Dispatch(app.Documents.Add(k.kAssemblyDocumentObject, app.FileManager.GetTemplateFile(
            k.kAssemblyDocumentObject, k.kMetricSystemOfMeasure), True)._oleobj_)
        occs = doc.ComponentDefinition.Occurrences
        indices = sorted({i for l in piernas for i in piernas[l]} | ({pelvis} if escena == "soporte_parado" else set()))
        for i in indices:
            M = T[i] @ np.block([[P[i]["M"], P[i]["t"][:, None]], [np.zeros((1, 3)), np.ones((1, 1))]])
            m = tg.CreateMatrix()
            m.SetCoordinateSystem(tg.CreatePoint(*(M[:3, 3] / 10)), tg.CreateVector(*M[:3, 0]), tg.CreateVector(*M[:3, 1]), tg.CreateVector(*M[:3, 2]))
            occs.Add(bm.ruta_ipt(rutas[i]), m)
        for s in soportes:
            occs.Add(ipts[s], tg.CreateMatrix())
        v = app.ActiveView
        for nombre, ojo in (("frente", (260.0, 40.0, 330.0)), ("atras", (-260.0, 60.0, -300.0))):
            cam = v.Camera
            cam.Eye = tg.CreatePoint(ojo[0] / 10, (ojo[1] - 80) / 10, ojo[2] / 10)
            cam.Target = tg.CreatePoint(0.0, -8.5, 2.5)
            cam.UpVector = tg.CreateUnitVector(0, 1, 0)
            cam.SetExtents(21.0, 21.0)
            cam.Apply()
            v.SaveAsBitmap(os.path.join(BASE, "vistas_torso", f"{escena}_{nombre}.png"), 800, 800)
        doc.SaveAs(os.path.join(BASE, f"{escena}.iam"), False)


if __name__ == "__main__":
    if "--vistas" in sys.argv:
        vistas()
    else:
        main()
