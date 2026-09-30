"""SEGMENTO: PRUEBA DE FUERZA (ELEMENTOS FINITOS) DE PIEZAS IMPRESAS
Programas libres: gmsh (malla de tetraedros) + scikit-fem (elasticidad lineal).

Metodo (peor caso, conservador):
  - interfaces de cada pieza: agujeros de pernos M3, tornillos de pestana/horn y rebajes de horn
  - para cada interfaz fija, se carga cada una de las otras con una fuerza en X, Y y Z
    (20 N en agujeros, 30 N en rebajes de horn: 0.245 N*m de bloqueo del MG90S a ~8 mm)
  - envolvente: el maximo von Mises de cada tetraedro sobre todos los casos
Material: PLA impreso. E = 2.8 GPa (con relleno), nu = 0.35.
Admisible: 20 MPa (entre capas, lo mas debil) / factor de seguridad 3 = 6.7 MPa.
Quitable: zonas que en ningun caso pasan de 1 MPa y estan a mas de 3 mm de una interfaz.
Unidades: mm, N, MPa.
"""
import json
import os
import sys

import gmsh
import meshio
import numpy as np
import pypardiso
from scipy.sparse.linalg import splu
from skfem import Basis, ElementTetP1, ElementVector, MeshTet, asm, condense
from skfem.models.elasticity import lame_parameters, linear_elasticity

AQUI = os.path.dirname(os.path.abspath(__file__))
NUEVO = os.path.dirname(AQUI)
sys.path.insert(0, NUEVO)

E_PLA = 2800.0
NU_PLA = 0.35
ADMISIBLE = 20.0 / 3.0
UMBRAL_QUITABLE = 1.0
MARGEN_INTERFAZ = 3.0
F_AGUJERO = 20.0
F_HORN = 30.0


# ---------------------------------------------------------------------------
# SEGMENTO: MALLA
# ---------------------------------------------------------------------------
def mallar(stl, h_max=0.8, h_min=0.3):
    """Malla de tetraedros. Con STEP (solido exacto de Inventor) usa OpenCASCADE; con STL reconstruye superficies."""
    if stl.lower().endswith((".stp", ".step")):
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setString("Geometry.OCCTargetUnit", "MM")
        gmsh.model.occ.importShapes(stl)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", h_max)
        gmsh.option.setNumber("Mesh.MeshSizeMin", h_min)
        gmsh.model.mesh.generate(3)
        ruta = os.path.join(AQUI, f"tmp_{os.getpid()}.msh")
        gmsh.write(ruta)
        gmsh.finalize()
        m = meshio.read(ruta)
        return MeshTet(m.points.T.copy(), m.cells_dict["tetra"].T.copy())
    # STL (mallas cortadas con booleanos): fTetWild, que tolera triangulos defectuosos (gmsh se colgaba)
    import pytetwild
    import trimesh
    tri = trimesh.load(stl, force="mesh")
    nodos, tets = pytetwild.tetrahedralize(np.asarray(tri.vertices, dtype=np.float64), np.asarray(tri.faces, dtype=np.int32),
                                          edge_length_abs=h_max)
    X = nodos[tets]
    det = np.einsum("ij,ij->i", X[:, 1] - X[:, 0], np.cross(X[:, 2] - X[:, 0], X[:, 3] - X[:, 0]))
    tets = tets.copy()
    tets[det < 0, 1], tets[det < 0, 2] = tets[det < 0, 2], tets[det < 0, 1].copy()
    return MeshTet(nodos.T.copy(), tets.T.copy())
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.merge(stl)
    gmsh.model.mesh.classifySurfaces(40 * np.pi / 180, True, True, np.pi)
    gmsh.model.mesh.createGeometry()
    lazo = gmsh.model.geo.addSurfaceLoop([e[1] for e in gmsh.model.getEntities(2)])
    gmsh.model.geo.addVolume([lazo])
    gmsh.model.geo.synchronize()
    gmsh.option.setNumber("Mesh.MeshSizeMax", h_max)
    gmsh.option.setNumber("Mesh.MeshSizeMin", h_min)
    gmsh.model.mesh.generate(3)
    ruta = os.path.join(AQUI, f"tmp_{os.getpid()}.msh")
    gmsh.write(ruta)
    gmsh.finalize()
    m = meshio.read(ruta)
    return MeshTet(m.points.T.copy(), m.cells_dict["tetra"].T.copy())


# ---------------------------------------------------------------------------
# SEGMENTO: INTERFACES
# Cada interfaz: nombre, tipo ('agujero' u 'horn'), nodos seleccionados.
# ---------------------------------------------------------------------------
def nodos_cilindro(p, centro, eje, radio, desde, hasta):
    eje = np.asarray(eje, float) / np.linalg.norm(eje)
    v = p - np.asarray(centro, float)
    axial = v @ eje
    radial = np.linalg.norm(v - np.outer(axial, eje), axis=1)
    return np.where((radial <= radio) & (axial >= desde) & (axial <= hasta))[0]


def interfaces_desde_agujeros(malla, lista):
    """lista: dicts con centro, eje (vector), radio, desde, hasta (a lo largo del eje, relativos al centro), tipo."""
    p = malla.p.T
    salida = []
    for k, it in enumerate(lista):
        if "plano" in it:                 # cara plana: nodos a menos de 0.3 mm del extremo en esa direccion
            n = np.asarray(it["plano"], float) / np.linalg.norm(it["plano"])
            d = p @ n
            nodos = np.where(d >= d.max() - 0.3)[0]
            it = dict(it, centro=p[nodos].mean(axis=0), eje=n)
        else:
            nodos = nodos_cilindro(p, it["centro"], it["eje"], it["radio"], it["desde"], it["hasta"])
        if len(nodos) >= 6:
            salida.append(dict(nombre=it.get("nombre", f"i{k}"), tipo=it["tipo"], nodos=nodos,
                               centro=np.asarray(it["centro"], float), eje=np.asarray(it["eje"], float)))
    return salida


# ---------------------------------------------------------------------------
# SEGMENTO: CALCULO
# ---------------------------------------------------------------------------
def envolvente(malla, interfaces):
    e = ElementVector(ElementTetP1())
    basis = Basis(malla, e)
    lam, mu = lame_parameters(E_PLA, NU_PLA)
    K = asm(linear_elasticity(lam, mu), basis)
    b0 = Basis(malla, ElementTetP1(), intorder=0)
    maximo = np.zeros(malla.t.shape[1])
    casos = 0
    for fija in interfaces:
        dofs_fijos = np.concatenate([basis.nodal_dofs[:, fija["nodos"]].flatten()])
        libres = np.setdiff1d(np.arange(basis.N), dofs_fijos)
        lu = splu(K[libres][:, libres].tocsc())
        for carga in interfaces:
            if carga is fija:
                continue
            f_total = F_HORN if carga["tipo"] == "horn" else F_AGUJERO
            for d in range(3):
                f = np.zeros(basis.N)
                f[basis.nodal_dofs[d, carga["nodos"]]] = f_total / len(carga["nodos"])
                u = np.zeros(basis.N)
                u[libres] = lu.solve(f[libres])
                maximo = np.maximum(maximo, von_mises(malla, basis, u, lam, mu))
                casos += 1
    return maximo, casos


def von_mises(malla, basis, u, lam, mu):
    """von Mises constante por tetraedro (P1)."""
    p = malla.p
    t = malla.t
    U = u[basis.nodal_dofs].T                      # (nodos, 3)
    X = p[:, t]                                    # (3, 4, ntet)
    D = np.stack([X[:, 1] - X[:, 0], X[:, 2] - X[:, 0], X[:, 3] - X[:, 0]], axis=1)   # (3,3,ntet)
    Ue = U[t]                                      # (4, ntet, 3)
    dU = np.stack([Ue[1] - Ue[0], Ue[2] - Ue[0], Ue[3] - Ue[0]], axis=2)               # (ntet, 3, 3)
    Dinv = np.linalg.inv(np.moveaxis(D, 2, 0))     # (ntet, 3, 3)
    G = np.einsum("nij,njk->nik", dU, Dinv)        # gradiente de desplazamiento
    eps = 0.5 * (G + np.transpose(G, (0, 2, 1)))
    tr = np.trace(eps, axis1=1, axis2=2)
    sig = 2 * mu * eps + lam * tr[:, None, None] * np.eye(3)
    s = sig - np.trace(sig, axis1=1, axis2=2)[:, None, None] / 3 * np.eye(3)
    return np.sqrt(1.5 * np.einsum("nij,nij->n", s, s))


# ---------------------------------------------------------------------------
# SEGMENTO: RESULTADOS
# ---------------------------------------------------------------------------
def resumen(nombre, malla, vm, interfaces):
    X = malla.p[:, malla.t]
    vol = np.abs(np.linalg.det(np.moveaxis(np.stack([X[:, 1] - X[:, 0], X[:, 2] - X[:, 0], X[:, 3] - X[:, 0]], axis=1), 2, 0))) / 6
    centros = X.mean(axis=1).T
    lejos = np.ones(len(vm), bool)
    for it in interfaces:
        d = np.min(np.linalg.norm(centros[:, None, :] - malla.p[:, it["nodos"]].T[None, :, :], axis=2), axis=1)
        lejos &= d > MARGEN_INTERFAZ
    quitable = (vm < UMBRAL_QUITABLE) & lejos
    p99 = np.percentile(vm, 99.5)
    datos = dict(pieza=nombre, volumen=float(vol.sum()), vm_max=float(vm.max()), vm_p995=float(p99),
                 factor_seguridad=float(20.0 / p99), quitable_pct=float(100 * vol[quitable].sum() / vol.sum()),
                 quitable_mm3=float(vol[quitable].sum()), tetras=int(len(vm)))
    return datos, quitable, centros


def mapa(nombre, malla, vm, quitable, ruta_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import cm, colors
    caras = malla.boundary_facets()
    tri = malla.facets[:, caras].T
    # tetraedro dueno de cada cara de borde
    dueno = malla.f2t[0, caras]
    valor = np.minimum(vm[dueno], ADMISIBLE)
    norma = colors.Normalize(0, ADMISIBLE)
    fig = plt.figure(figsize=(16, 8))
    for k, (elev, azim) in enumerate(((25, 45), (25, 225), (-30, 135))):
        ax = fig.add_subplot(1, 3, k + 1, projection="3d")
        pts = malla.p.T
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        col = Poly3DCollection(pts[tri], facecolors=cm.turbo(norma(valor)), edgecolor="none")
        ax.add_collection3d(col)
        lim = [pts.min(0), pts.max(0)]
        c = (lim[0] + lim[1]) / 2
        r = (lim[1] - lim[0]).max() / 2
        ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
        ax.view_init(elev, azim)
        ax.set_axis_off()
    fig.suptitle(f"{nombre}: von Mises envolvente (azul 0 -> rojo >= {ADMISIBLE:.1f} MPa admisible)")
    sm = cm.ScalarMappable(norm=norma, cmap=cm.turbo)
    fig.colorbar(sm, ax=fig.axes, shrink=0.6, label="MPa")
    plt.savefig(ruta_png, dpi=70)
    plt.close(fig)


# ---------------------------------------------------------------------------
# SEGMENTO: CASOS DE CARGA REALES POR PIEZA
# caso = dict(nombre, fijas=[interfaces], fuerzas=[(interfaces, vector N)], torque=(interfaces, punto, eje, N*mm))
# ---------------------------------------------------------------------------
PESO_DINAMICO = 17.0          # N: 3 x peso del robot (~0.57 kg) apoyado en una pierna
TORQUE_SERVO = 245.0          # N*mm: bloqueo del MG90S a 6 V


def por_nombre(interfaces, nombres):
    nodos = np.concatenate([it["nodos"] for it in interfaces if it["nombre"] in nombres])
    return np.unique(nodos)


def resolver_casos(malla, interfaces, casos):
    e = ElementVector(ElementTetP1())
    basis = Basis(malla, e)
    lam, mu = lame_parameters(E_PLA, NU_PLA)
    K = asm(linear_elasticity(lam, mu), basis)
    maximo = np.zeros(malla.t.shape[1])
    detalle = {}
    p = malla.p.T
    for caso in casos:
        fijos = por_nombre(interfaces, caso["fijas"])
        dofs_fijos = basis.nodal_dofs[:, fijos].flatten()
        libres = np.setdiff1d(np.arange(basis.N), dofs_fijos)
        # PARDISO (MKL): splu llenaba >20 GB en los pies; PARDISO lo resuelve con ~5 GB
        A = K[libres][:, libres].tocsr()
        lu = pypardiso.PyPardisoSolver()
        lu.factorize(A)
        cargas = []
        for nombres, vector in caso.get("fuerzas", []):
            nodos = por_nombre(interfaces, nombres)
            f = np.zeros(basis.N)
            for d in range(3):
                f[basis.nodal_dofs[d, nodos]] = vector[d] / len(nodos)
            cargas.append((f"F{np.round(vector, 1).tolist()}", f, nodos))
        if "torque" in caso:
            nombres, punto, eje, T = caso["torque"]
            nodos = por_nombre(interfaces, nombres)
            a = np.asarray(eje, float) / np.linalg.norm(eje)
            r = p[nodos] - np.asarray(punto, float)
            r -= np.outer(r @ a, a)
            fn = T * np.cross(a, r) / (np.linalg.norm(r, axis=1) ** 2).sum()
            f = np.zeros(basis.N)
            for d in range(3):
                f[basis.nodal_dofs[d, nodos]] = fn[:, d]
            cargas.append(("torque", f, nodos))
        for etiqueta, f, nodos_carga in cargas:
            u = np.zeros(basis.N)
            u[libres] = lu.solve(A, f[libres])
            vm = von_mises(malla, basis, u, lam, mu)
            maximo = np.maximum(maximo, vm)
            detalle[f"{caso['nombre']} {etiqueta}"] = (vm, np.unique(np.concatenate([fijos, nodos_carga])))
        lu.free_memory(everything=True)
    return maximo, detalle


def esfuerzo_util(malla, vm, nodos_interfaz, radio=1.5):
    """Percentil 99.5 del von Mises sin los tetraedros a menos de 'radio' de nodos cargados o fijos."""
    centros = malla.p[:, malla.t].mean(axis=1).T
    from scipy.spatial import cKDTree
    d, _ = cKDTree(malla.p[:, nodos_interfaz].T).query(centros)
    lejos = d > radio
    return float(np.percentile(vm[lejos], 99.5)), float(vm[lejos].max())


# ---------------------------------------------------------------------------
# SEGMENTO: ALIGERADO ESTILO JEAN NOA (ranuras en escalera)
# ---------------------------------------------------------------------------
PASO_VOXEL = 0.5


def dentro_rejilla(malla_tri, ejes):
    """Puntos de la rejilla (ejes x, y, z) dentro de la malla, por paridad de cruces en columnas a lo largo de Z.
    Mucho mas rapido que malla.contains (rayos con rtree: decenas de minutos en los pies)."""
    xs, ys, zs = ejes
    # corrimiento minimo para no caer justo sobre aristas o vertices
    X0, Y0 = xs[0] + 1.37e-5, ys[0] + 2.91e-5
    paso_x = xs[1] - xs[0] if len(xs) > 1 else 1.0
    paso_y = ys[1] - ys[0] if len(ys) > 1 else 1.0
    T = malla_tri.triangles
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    det = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])
    ok = np.abs(det) > 1e-12
    a, b, c, det = a[ok], b[ok], c[ok], det[ok]
    lo, hi = np.minimum(np.minimum(a, b), c), np.maximum(np.maximum(a, b), c)
    i0 = np.clip(np.ceil((lo[:, 0] - X0) / paso_x), 0, len(xs)).astype(int)
    i1 = np.clip(np.floor((hi[:, 0] - X0) / paso_x), -1, len(xs) - 1).astype(int)
    j0 = np.clip(np.ceil((lo[:, 1] - Y0) / paso_y), 0, len(ys)).astype(int)
    j1 = np.clip(np.floor((hi[:, 1] - Y0) / paso_y), -1, len(ys) - 1).astype(int)
    ni, nj = np.maximum(i1 - i0 + 1, 0), np.maximum(j1 - j0 + 1, 0)
    cuenta = np.zeros((len(xs) * len(ys), len(zs) + 1), np.int32)
    tri_id = np.repeat(np.arange(len(a)), ni * nj)
    base = np.repeat(np.cumsum(ni * nj) - ni * nj, ni * nj)
    k = np.arange(len(tri_id)) - base
    ii = i0[tri_id] + k // nj[tri_id]
    jj = j0[tri_id] + k % nj[tri_id]
    px, py = X0 + ii * paso_x, Y0 + jj * paso_y
    A, B, C, D = a[tri_id], b[tri_id], c[tri_id], det[tri_id]
    l1 = ((B[:, 1] - C[:, 1]) * (px - C[:, 0]) + (C[:, 0] - B[:, 0]) * (py - C[:, 1])) / D
    l2 = ((C[:, 1] - A[:, 1]) * (px - C[:, 0]) + (A[:, 0] - C[:, 0]) * (py - C[:, 1])) / D
    l3 = 1 - l1 - l2
    dentro_tri = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
    z = l1 * A[:, 2] + l2 * B[:, 2] + l3 * C[:, 2]
    col = (ii * len(ys) + jj)[dentro_tri]
    kz = np.searchsorted(zs, z[dentro_tri])
    np.add.at(cuenta, (col, kz), 1)
    paridad = (np.cumsum(cuenta, axis=1)[:, :len(zs)] % 2).astype(bool)
    return paridad.reshape(len(xs), len(ys), len(zs))


def contiene(malla_tri, pts, bloque=5000):
    """malla.contains por bloques: de una vez pedia ~8 GB en piezas grandes (Bracket01)."""
    return np.concatenate([malla_tri.contains(pts[i:i + bloque]) for i in range(0, len(pts), bloque)])
RANURA_ANCHO = 2.5
NERVIO = 2.0
ESPESOR_VENTANA_MAX = 8.0     # mm de material que puede atravesar una ventana
BORDE = 1.2                   # 3 lineas con boquilla 0.4
RANURA_MIN = 2.5


def mapa_cortable(malla_tri, malla_tet, vm, nodos_interfaz, eje, umbral=UMBRAL_QUITABLE, margen=MARGEN_INTERFAZ):
    """Mascara 2D (perpendicular a 'eje') de columnas donde todo el material casi no trabaja."""
    from scipy.spatial import cKDTree
    lo, hi = malla_tri.bounds
    ejes = [np.arange(lo[i] + PASO_VOXEL / 2, hi[i], PASO_VOXEL) for i in range(3)]
    G = np.stack(np.meshgrid(*ejes, indexing="ij"), axis=-1)
    pts = G.reshape(-1, 3)
    dentro = contiene(malla_tri, pts)
    centros = malla_tet.p[:, malla_tet.t].mean(axis=1).T
    _, idx = cKDTree(centros).query(pts[dentro])
    d_int, _ = cKDTree(malla_tet.p[:, nodos_interfaz].T).query(pts[dentro])
    ok = np.zeros(len(pts), bool)
    ok[np.where(dentro)[0]] = (vm[idx] < umbral) & (d_int > margen)
    dentro = dentro.reshape(G.shape[:3])
    ok = ok.reshape(G.shape[:3])
    hay = dentro.any(axis=eje)
    todo_ok = (~dentro | ok).all(axis=eje)
    return hay & todo_ok, [e for i, e in enumerate(ejes) if i != eje]


def ranuras_en_mascara(mascara, coords):
    """Ranuras de RANURA_ANCHO con nervios NERVIO dentro de cada zona cortable (erosionada BORDE).
    Por zona: las ranuras cruzan su direccion mas larga y arrancan desde el borde de la zona."""
    from scipy import ndimage
    util = ndimage.distance_transform_edt(np.pad(mascara, 1)) [1:-1, 1:-1] * PASO_VOXEL > BORDE
    cu, cv = coords
    ancho = max(1, int(round(RANURA_ANCHO / PASO_VOXEL)))
    paso = max(ancho + 1, int(round((RANURA_ANCHO + NERVIO) / PASO_VOXEL)))
    etiquetas, n = ndimage.label(util)
    rects = []
    for k in range(1, n + 1):
        zona = etiquetas == k
        iu = np.where(zona.any(axis=1))[0]
        iv = np.where(zona.any(axis=0))[0]
        if len(iu) >= len(iv):          # zona larga en u: filas de ranuras que avanzan en u
            for i0 in range(iu[0], iu[-1] - ancho + 2, paso):
                fila = zona[i0:i0 + ancho].all(axis=0)
                rects += [(cu[i0] - PASO_VOXEL / 2, cu[i0 + ancho - 1] + PASO_VOXEL / 2, cv[a] - PASO_VOXEL / 2, cv[b] + PASO_VOXEL / 2)
                          for a, b in tramos(fila) if (b - a + 1) * PASO_VOXEL >= RANURA_MIN]
        else:
            for j0 in range(iv[0], iv[-1] - ancho + 2, paso):
                col = zona[:, j0:j0 + ancho].all(axis=1)
                rects += [(cu[a] - PASO_VOXEL / 2, cu[b] + PASO_VOXEL / 2, cv[j0] - PASO_VOXEL / 2, cv[j0 + ancho - 1] + PASO_VOXEL / 2)
                          for a, b in tramos(col) if (b - a + 1) * PASO_VOXEL >= RANURA_MIN]
    return rects


def tramos(v):
    salida, ini = [], None
    for i, x in enumerate(v):
        if x and ini is None:
            ini = i
        if (not x or i == len(v) - 1) and ini is not None:
            salida.append((ini, i if x else i - 1))
            ini = None
    return salida


def cortar_ranuras(malla_tri, eje, rects):
    import trimesh
    lo, hi = malla_tri.bounds
    cajas = []
    otros = [i for i in range(3) if i != eje]
    for u0, u1, v0, v1 in rects:
        mn, mx = np.zeros(3), np.zeros(3)
        mn[eje], mx[eje] = lo[eje] - 1, hi[eje] + 1
        mn[otros[0]], mx[otros[0]] = u0, u1
        mn[otros[1]], mx[otros[1]] = v0, v1
        b = trimesh.creation.box(extents=mx - mn)
        b.apply_translation((mn + mx) / 2)
        cajas.append(b)
    if not cajas:
        return malla_tri
    return trimesh.boolean.difference([malla_tri, trimesh.boolean.union(cajas, engine="manifold")], engine="manifold")


class Voxeles:
    """Clasificacion de la pieza en voxeles, una sola vez para todas las direcciones y umbrales."""

    def __init__(self, malla_tri, malla_tet, vm, nodos_interfaz, paso=PASO_VOXEL):
        from scipy.spatial import cKDTree
        lo, hi = malla_tri.bounds
        self.ejes = [np.arange(lo[i] + paso / 2, hi[i], paso) for i in range(3)]
        G = np.stack(np.meshgrid(*self.ejes, indexing="ij"), axis=-1)
        pts = G.reshape(-1, 3)
        dentro = dentro_rejilla(malla_tri, self.ejes).reshape(-1)
        centros = malla_tet.p[:, malla_tet.t].mean(axis=1).T
        _, idx = cKDTree(centros).query(pts[dentro])
        d_int, _ = cKDTree(malla_tet.p[:, nodos_interfaz].T).query(pts[dentro])
        self.forma = G.shape[:3]
        self.dentro = dentro.reshape(self.forma)
        self.vm = np.full(len(pts), np.inf)
        self.vm[np.where(dentro)[0]] = vm[idx]
        self.vm = self.vm.reshape(self.forma)
        self.dist = np.zeros(len(pts))
        self.dist[np.where(dentro)[0]] = d_int
        self.dist = self.dist.reshape(self.forma)
        self.paso = paso

    def mascara(self, eje, umbral, margen):
        ok = self.dentro & (self.vm < umbral) & (self.dist > margen)
        hay = self.dentro.any(axis=eje)
        todo_ok = (~self.dentro | ok).all(axis=eje)
        # solo atravesar paredes delgadas: sin esto salian tuneles a lo largo de placas (suela del pie)
        delgada = self.dentro.sum(axis=eje) * self.paso <= ESPESOR_VENTANA_MAX
        return hay & todo_ok & delgada, [e for i, e in enumerate(self.ejes) if i != eje]


def aligerar(nombre, stl, lista_interfaces, casos, h=0.8, umbrales=(2.0, 1.5, 1.0), margenes=(2.5, 3.0),
             carpeta_salida=None, fs_objetivo=3.0):
    """Calcula, corta ranuras donde se puede y verifica. Devuelve dict con resultados."""
    import trimesh
    tri = trimesh.load(stl, force="mesh")
    malla = mallar(stl, h, 0.3)
    its = interfaces_desde_agujeros(malla, lista_interfaces)
    vm, det = resolver_casos(malla, its, casos)
    todas = np.unique(np.concatenate([it["nodos"] for it in its]))
    fs_ini = min(20.0 / esfuerzo_util(malla, v, n)[1] for v, n in det.values())
    mapa(nombre, malla, vm, None, os.path.join(AQUI, f"{nombre}_esfuerzo.png"))
    vox = Voxeles(tri, malla, vm, todas)
    intentos = []
    for umbral in umbrales:
        for margen in margenes:
            for eje in range(3):
                mask, coords = vox.mascara(eje, umbral, margen)
                rects = ranuras_en_mascara(mask, coords)
                if rects:
                    intentos.append((umbral, margen, eje, rects))
    # probar de mayor a menor material quitado; el primero que cumple el factor de seguridad gana
    candidatos = []
    for umbral, margen, eje, rects in intentos:
        area = sum((u1 - u0) * (v1 - v0) for u0, u1, v0, v1 in rects)
        candidatos.append((area, umbral, margen, eje, rects))
    candidatos.sort(key=lambda c: -c[0])
    resultado = dict(pieza=nombre, volumen=float(tri.volume), fs_inicial=float(fs_ini), quitado_mm3=0.0, fs_final=float(fs_ini),
                     ranuras=0, eje=None)
    probados = set()
    for area, umbral, margen, eje, rects in candidatos[:6]:
        clave = (eje, round(area))
        if clave in probados:
            continue
        probados.add(clave)
        nueva = cortar_ranuras(tri, eje, rects)
        if nueva.is_empty or not nueva.is_watertight:
            continue
        tmp = os.path.join(AQUI, f"tmp_aligerada_{os.getpid()}.stl")
        nueva.export(tmp)
        try:
            m2 = mallar(tmp, h, 0.3)
        except Exception:
            continue
        its2 = interfaces_desde_agujeros(m2, lista_interfaces)
        if len(its2) != len(its):
            continue                      # una ranura comio una interfaz
        vm2, det2 = resolver_casos(m2, its2, casos)
        fs = min(20.0 / esfuerzo_util(m2, v, n)[1] for v, n in det2.values())
        if fs >= fs_objetivo:
            resultado.update(quitado_mm3=float(tri.volume - nueva.volume), fs_final=float(fs), ranuras=len(rects),
                             eje="XYZ"[eje], umbral=umbral, margen=margen)
            destino = os.path.join(carpeta_salida or AQUI, f"{nombre}.stl")
            nueva.export(destino)
            mapa(nombre + " aligerada", m2, vm2, None, os.path.join(AQUI, f"{nombre}_aligerada_esfuerzo.png"))
            break
    return resultado


# ---------------------------------------------------------------------------
# SEGMENTO: VENTANAS (zonas cortables con borde de 1.2 mm, partidas por nervios si son largas)
# ---------------------------------------------------------------------------
VENTANA_AREA_MIN = 6.0        # mm2
VENTANA_ANCHO_MIN = 2.0       # mm (abertura minima imprimible)
VENTANA_LARGO_MAX = 10.0      # mm: las mas largas se parten con nervios de NERVIO


def ventanas_en_mascara(mascara, coords):
    from scipy import ndimage
    from shapely.geometry import box
    from shapely.ops import unary_union
    d = ndimage.distance_transform_edt(np.pad(mascara, 1))[1:-1, 1:-1] * PASO_VOXEL
    util = d > BORDE
    cu, cv = coords
    h = PASO_VOXEL / 2
    etiquetas, n = ndimage.label(util)
    poligonos = []
    for k in range(1, n + 1):
        zona = etiquetas == k
        if zona.sum() * PASO_VOXEL ** 2 < VENTANA_AREA_MIN:
            continue
        # abertura minima: la zona tiene que tener un punto a >= ancho/2 de su propio borde
        if ndimage.distance_transform_edt(np.pad(zona, 1)).max() * PASO_VOXEL < VENTANA_ANCHO_MIN / 2:
            continue
        iu, iv = np.where(zona)
        forma = unary_union([box(cu[i] - h, cv[j] - h, cu[i] + h, cv[j] + h) for i, j in zip(iu, iv)])
        forma = forma.buffer(-0.3, join_style=1).buffer(0.3, join_style=1).simplify(0.15)
        if forma.is_empty:
            continue
        partes = [forma] if forma.geom_type == "Polygon" else list(forma.geoms)
        for p in partes:
            if p.area < VENTANA_AREA_MIN:
                continue
            minx, miny, maxx, maxy = p.bounds
            largo_u, largo_v = maxx - minx, maxy - miny
            if max(largo_u, largo_v) > VENTANA_LARGO_MAX:
                # nervios cruzados a la direccion larga
                n_trozos = int(np.ceil(max(largo_u, largo_v) / VENTANA_LARGO_MAX))
                for t in range(1, n_trozos):
                    if largo_u >= largo_v:
                        c = minx + largo_u * t / n_trozos
                        p = p.difference(box(c - NERVIO / 2, miny - 1, c + NERVIO / 2, maxy + 1))
                    else:
                        c = miny + largo_v * t / n_trozos
                        p = p.difference(box(minx - 1, c - NERVIO / 2, maxx + 1, c + NERVIO / 2))
            sub = [p] if p.geom_type == "Polygon" else list(p.geoms)
            poligonos += [q for q in sub if q.area >= VENTANA_AREA_MIN]
    return poligonos


def cortar_ventanas(malla_tri, eje, poligonos):
    import trimesh
    if not poligonos:
        return malla_tri
    lo, hi = malla_tri.bounds
    otros = [i for i in range(3) if i != eje]
    herramientas = []
    for p in poligonos:
        ex = trimesh.creation.extrude_polygon(p, hi[eje] - lo[eje] + 2)
        # extrude_polygon: (u, v) en x,y y altura en z -> llevar a (otros[0], otros[1], eje)
        M = np.zeros((4, 4))
        M[otros[0], 0] = 1
        M[otros[1], 1] = 1
        M[eje, 2] = 1
        M[eje, 3] = lo[eje] - 1
        M[3, 3] = 1
        ex.apply_transform(M)             # trimesh ya invierte las caras si la matriz es un reflejo
        if ex.is_volume:
            herramientas.append(ex)
    if not herramientas:
        return malla_tri
    return trimesh.boolean.difference([malla_tri, trimesh.boolean.union(herramientas, engine="manifold")], engine="manifold")


def aligerar_ventanas(nombre, stl, lista_interfaces, casos, h=0.8, umbrales=(2.0, 1.5, 1.0), margenes=(2.5, 3.0),
                      carpeta_salida=None, fs_objetivo=3.0, max_pruebas=2):
    import trimesh
    # STEP: la malla de superficie para voxeles y cortes sale del STL exportado de Inventor
    superficie = stl
    if stl.lower().endswith((".stp", ".step")):
        superficie = os.path.join(NUEVO, "stl", os.path.splitext(os.path.basename(stl))[0] + ".stl")
    tri = trimesh.load(superficie, force="mesh")
    malla = mallar(stl, h, 0.3)
    its = interfaces_desde_agujeros(malla, lista_interfaces)
    vm, det = resolver_casos(malla, its, casos)
    todas = np.unique(np.concatenate([it["nodos"] for it in its]))
    fs_ini = min(20.0 / esfuerzo_util(malla, v, n)[1] for v, n in det.values())
    mapa(nombre, malla, vm, None, os.path.join(AQUI, f"{nombre}_esfuerzo.png"))
    vox = Voxeles(tri, malla, vm, todas)
    # piezas que ya salen bajo 3 con este modelo conservador (y funcionan en el NX25):
    # solo se acepta aligerar si no empeoran mas de 5%
    fs_objetivo = min(fs_objetivo, 0.95 * fs_ini)
    candidatos = []
    for umbral in umbrales:
        for margen in margenes:
            # combinar las 3 direcciones: se cortan en orden y cada una respeta lo que ya se corto
            pols = {eje: ventanas_en_mascara(*vox.mascara(eje, umbral, margen)) for eje in range(3)}
            area = sum(p.area for ps in pols.values() for p in ps)
            if area > 0:
                candidatos.append((area, umbral, margen, pols))
    candidatos.sort(key=lambda c: -c[0])
    print(f"  {nombre}: {len(candidatos)} candidatos, areas {[round(c[0]) for c in candidatos]}", flush=True)
    res = dict(pieza=nombre, volumen=float(tri.volume), fs_inicial=float(fs_ini), quitado_mm3=0.0, fs_final=float(fs_ini), ventanas=0)
    vistos = set()
    for area, umbral, margen, pols in candidatos[:max_pruebas]:
        if round(area) in vistos:
            continue
        vistos.add(round(area))
        # probar primero las 3 direcciones juntas; si no cumple, cada direccion sola
        opciones = [pols] + [{e: pols[e]} for e in range(3) if pols[e]]
        for op in opciones:
            nueva = tri
            for eje, ps in op.items():
                nueva = cortar_ventanas(nueva, eje, ps)
            if nueva.is_empty or not nueva.is_watertight or nueva.volume >= tri.volume - 1:
                print(f"  {nombre} umbral {umbral} margen {margen} {list(op)}: corte invalido", flush=True)
                continue
            tmp = os.path.join(AQUI, f"tmp_aligerada_{os.getpid()}.stl")
            nueva.export(tmp)
            try:
                m2 = mallar(tmp, h, 0.3)
            except Exception:
                continue
            its2 = interfaces_desde_agujeros(m2, lista_interfaces)
            if len(its2) != len(its):
                print(f"  {nombre} umbral {umbral} margen {margen} {list(op)}: se perdio una interfaz", flush=True)
                continue
            vm2, det2 = resolver_casos(m2, its2, casos)
            fs = min(20.0 / esfuerzo_util(m2, v, n)[1] for v, n in det2.values())
            quita = tri.volume - nueva.volume
            print(f"  {nombre} umbral {umbral} margen {margen} {list(op)}: -{quita:.0f} mm3, FS {fs:.2f} (objetivo {fs_objetivo:.2f})", flush=True)
            if fs >= fs_objetivo and quita > res["quitado_mm3"]:
                res.update(quitado_mm3=float(quita), fs_final=float(fs), ventanas=sum(len(ps) for ps in op.values()),
                           direcciones="".join("XYZ"[e] for e in op), umbral=umbral, margen=margen)
                nueva.export(os.path.join(carpeta_salida or AQUI, f"{nombre}.stl"))
                mapa(nombre + " aligerada", m2, vm2, None, os.path.join(AQUI, f"{nombre}_aligerada_esfuerzo.png"))
                break
        if res["quitado_mm3"] > 0:
            break
    return res
