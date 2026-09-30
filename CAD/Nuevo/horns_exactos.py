"""SEGMENTO: REBAJE EXACTO DEL HORN EN LAS PIEZAS DEL NX25
La pelvis y la cabeza ya tienen el rebaje con la forma del horn (pelvis.py, cabeza.py). Aca se hace
lo mismo en los otros encastres (muslos, pies, hombros, manos), sobre piezas_m3/*.stl:
  - la altura del horn NO cambia: el fondo queda donde apoyaba el horn en el NX25 (cara de la placa
    o fondo del rebaje viejo), asi el estriado del servo engancha igual
  - horn de 1 brazo (tornillos hacia un solo lado) o doble (hacia los dos lados: base del hombro), orientado segun
    los agujeros de tornillo que ya tenia la pieza
  - se rellena lo viejo (agujero del cubo, rebaje y agujeros) y se corta: forma del horn con 0.15 mm
    por lado, paso del collar O7.1 y agujeros de tornillo en las posiciones medidas del horn
  - orejas gruesas (rebaje viejo de >= 1 mm): el rebaje va dentro de la oreja
  - placas planas: borde de 1.2 mm alrededor de la forma del horn, hacia afuera (como la pelvis)
Correr despues de m3_pernos.py y antes de mano.py.
"""
import os

import manifold3d
import numpy as np
import trimesh
from shapely.geometry import Point, Polygon

import pelvis as pv
import uniones as un

BASE = os.path.dirname(os.path.abspath(__file__))
PIEZAS = os.path.join(BASE, "piezas_m3")
COLLAR = 7.1                       # O6.3 (1 brazo) y O6.8 (cruz) con juego
TORNILLO = 1.8                     # como el NX25: tornillo desde adentro hacia el horn
TORNILLO_CRUZ = (2.5, 4.5, 1.5)    # base del hombro: agujero, avellanado, hondo (como el NX25)
BORDE = (1.2, 1.2)                 # ancho, alto del borde en placas planas
RELLENO = 2.0                      # cuanto se agranda la forma para tapar lo viejo
# horn doble del MG90S (CAD/Componentes/MG90S_horn_doble.stl): collar O6.8, brazos de 2.1 mm hasta 15.5,
# ancho 6.8 en la raiz y 3.2 en la punta, agujeros cada 1.92 desde 4.4 (se usan 8.24 y 12.08)
DOBLE_LARGO = 15.5
DOBLE_RAIZ = 3.4
DOBLE_PUNTA = 1.61
DOBLE_TORNILLOS = (8.24, 12.08)


def contorno_doble(holgura=pv.HOLGURA):
    from shapely.geometry import MultiPoint
    pts = list(Point(0, 0).buffer(DOBLE_RAIZ + holgura, 48).exterior.coords)
    for sx in (1, -1):
        pts += list(Point(sx * (DOBLE_LARGO - DOBLE_PUNTA), 0).buffer(DOBLE_PUNTA + holgura, 24).exterior.coords)
    return MultiPoint(pts).convex_hull


def perfil_material(malla, puntos):
    return malla.contains(np.asarray(puntos))


def medir(malla, c, ol, u, s_vals):
    """Rango (s) con material a 5.5 mm del eje de costado, y maximo s con material sobre el brazo (a 10 mm)."""
    v = np.cross(ol, u)
    def rango(offset):
        """tramo continuo de material mas largo (un punto suelto mal clasificado no lo estira)"""
        dentro = perfil_material(malla, [c + offset + ol * s for s in s_vals])
        mejor, ini = None, None
        for j, ok in enumerate(list(dentro) + [False]):
            if ok and ini is None:
                ini = j
            if not ok and ini is not None:
                if mejor is None or j - ini > mejor[1] - mejor[0]:
                    mejor = (ini, j)
                ini = None
        return (s_vals[mejor[0]], s_vals[mejor[1] - 1]) if mejor else None
    costado = [r for r in (rango(v * 5.5), rango(-v * 5.5)) if r]
    brazo = [r for r in (rango(u * 10.0 + v * 1.6), rango(u * 10.0 - v * 1.6)) if r]
    s_in = min(r[0] for r in costado)
    s_out = max(r[1] for r in costado)
    s_brazo = max(r[1] for r in brazo) if brazo else s_out
    return s_in, s_out, s_brazo


def extruir(poligono, c, u, v, ol, s0, s1):
    m = trimesh.creation.extrude_polygon(poligono, s1 - s0)
    T = np.eye(4)
    T[:3, :3] = np.column_stack([u, v, ol])
    T[:3, 3] = c + ol * s0
    m.apply_transform(T)
    return m


def cilindros(c, u, v, ol, puntos, radio, s0, s1):
    return [trimesh.creation.cylinder(radius=radio, segment=[c + u * x + v * y + ol * s0, c + u * x + v * y + ol * s1], sections=32)
            for x, y in puntos]


def limpiar(malla):
    partes = malla.split(only_watertight=False)
    malla = max(partes, key=lambda p: abs(p.volume))
    malla.merge_vertices(digits_vertex=4)
    m = manifold3d.Manifold(manifold3d.Mesh(vert_properties=np.asarray(malla.vertices, np.float32),
                                            tri_verts=np.asarray(malla.faces, np.uint32))).to_mesh()
    return trimesh.Trimesh(m.vert_properties[:, :3], m.tri_verts)


def encastres():
    """(pieza, centro local, eje hacia el horn, direccion del brazo, tipo, radio de los tornillos viejos) sin repetir."""
    import json
    P = un.piezas()
    host = un.rigidas(P)
    agujeros = json.load(open(un.AGUJEROS, encoding="utf-8"))
    lista, vistos = [], set()
    for g in un.uniones_giratorias(P, host):
        if g["tipo"] != "horn":
            continue
        a, b = g["a"], g["b"]
        n = P[a]["nombre"]
        if n not in ("Bracket01_B", "Bracket03_B", "Bracket04_B", "Bracket05_B", "Bracket07_B", "Bracket08_B", "Bracket11_B", "Bracket12_B"):
            continue
        M, t = P[a]["M"], P[a]["t"]
        c = M.T @ (g["c"] - t)
        ol = M.T @ P[b]["M"][:, 1]                   # el eje del servo apunta hacia el lado del horn
        ol /= np.linalg.norm(ol)
        clave = (n, tuple(np.round(c, 1)))
        if clave in vistos:
            continue
        vistos.add(clave)
        dirs, radios = [], []
        for h in agujeros.get(n, []):
            if abs(abs(un.EJES[h["eje"]] @ ol) - 1) > 0.05 or not 0.6 < h["r"] < 1.4:
                continue
            w = np.asarray(h["centro"], float) - c
            w -= (w @ ol) * ol
            if 7.0 < np.linalg.norm(w) < 13.5:
                dirs.append(w / np.linalg.norm(w))
                radios.append(h["r"])
        u = dirs[0]
        doble = any(d @ u < -0.9 for d in dirs)
        c = c - ol * (c @ ol) + ol * (c @ ol)       # centro sobre el eje (ya lo esta)
        lista.append(dict(pieza=n, c=c, ol=ol, u=u, tipo="doble" if doble else "brazo", r_tornillo=max(radios)))
    return lista


def main():
    s_vals = np.arange(-8.0, 8.0, 0.05)
    por_pieza = {}
    for e in encastres():
        por_pieza.setdefault(e["pieza"], []).append(e)
    for pieza, lista in sorted(por_pieza.items()):
        malla = trimesh.load(os.path.join(PIEZAS, pieza + ".stl"), force="mesh")
        for e in lista:
            c, ol, u = e["c"], e["ol"], e["u"]
            v = np.cross(ol, u)
            s_in, s_out, s_brazo = medir(malla, c, ol, u, s_vals)
            oreja = s_out - s_brazo >= 0.8
            piso = s_brazo if oreja else s_out
            if e["tipo"] == "brazo":
                forma = Polygon(pv.contorno_horn((1.0, 0.0)))
                tornillos = [(d, 0.0) for d in pv.TORNILLOS_HORN]
            else:
                forma = contorno_doble()
                tornillos = [(sx * d, 0.0) for sx in (1, -1) for d in DOBLE_TORNILLOS]
            # 1) rellenar lo viejo dentro de la zona del horn (de la cara de adentro al piso, o a la cara de afuera en orejas)
            relleno = forma.buffer(RELLENO).union(Point(0, 0).buffer(COLLAR / 2 + RELLENO))
            nuevas = [extruir(relleno, c, u, v, ol, s_in, s_out if oreja else piso)]
            # 2) borde en placas planas
            if not oreja:
                nuevas.append(extruir(forma.buffer(BORDE[0], join_style=1), c, u, v, ol, piso - 0.2, piso + BORDE[1]))
            malla = trimesh.boolean.union([malla] + nuevas, engine="manifold")
            # 3) cortes: forma del horn, collar pasante y tornillos
            cortes = [extruir(forma, c, u, v, ol, piso, s_out + BORDE[1] + 1.0)]
            cortes += cilindros(c, u, v, ol, [(0.0, 0.0)], COLLAR / 2, s_in - 1.0, piso + 0.01)
            if e["r_tornillo"] > 1.0:          # base del hombro: agujero con avellanado del lado de adentro
                cortes += cilindros(c, u, v, ol, tornillos, TORNILLO_CRUZ[0] / 2, s_in - 1.0, piso + 0.01)
                cortes += cilindros(c, u, v, ol, tornillos, TORNILLO_CRUZ[1] / 2, s_in - 1.0, s_in + TORNILLO_CRUZ[2])
            else:
                cortes += cilindros(c, u, v, ol, tornillos, TORNILLO / 2, s_in - 1.0, piso + 0.01)
            malla = trimesh.boolean.difference([malla, trimesh.boolean.union(cortes, engine="manifold")], engine="manifold")
            print(f"{pieza}: horn {e['tipo']:5s} en {np.round(c, 1).tolist()} | {'oreja' if oreja else 'placa'} "
                  f"de {s_in:+.2f} a {s_out:+.2f}, fondo del horn en {piso:+.2f} (rebaje de {s_out - piso:.2f})")
        malla = limpiar(malla)
        malla.export(os.path.join(PIEZAS, pieza + ".stl"))
        r = trimesh.load(os.path.join(PIEZAS, pieza + ".stl"), force="mesh")
        print(f"   -> {pieza}.stl valido {r.is_volume}, cuerpos {len(r.split(only_watertight=False))}")


if __name__ == "__main__":
    main()
