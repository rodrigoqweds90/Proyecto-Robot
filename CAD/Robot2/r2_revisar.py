"""ROBOT 2 - REVISION: mallas de las piezas (de r2_diseno), peso, centro de masa, choques e imagenes.
Uso: python r2_revisar.py [--sin_imagenes]
"""
import itertools
import os
import sys

import manifold3d as mf
import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import r2_diseno as d  # noqa: E402

SALIDA = os.path.join(BASE, "revision")


# =====================================================================
# SEGMENTO: MALLAS
# =====================================================================
def a_manifold(m):
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32), tri_verts=np.asarray(m.faces, np.uint32)))


def a_trimesh(m):
    k = m.to_mesh()
    return trimesh.Trimesh(k.vert_properties[:, :3], k.tri_verts)


def primitiva(p):
    if p[1] == "caja":
        x0, x1, y0, y1, z0, z1 = p[2]
        return mf.Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])
    _, _, eje, (a, b), r, t0, t1 = p
    c = mf.Manifold.cylinder(t1 - t0, r, r, 48)           # a lo largo de z, de 0 a alto
    if eje == "z":
        return c.translate([a, b, t0])
    if eje == "x":                                          # (a, b) = (y, z)
        return c.rotate([0, 90, 0]).translate([t0, a, b])
    return c.rotate([-90, 0, 0]).translate([a, t0, b])     # eje y: (a, b) = (x, z)


def malla_pieza(prims):
    m = mf.Manifold()
    for p in prims:
        g = primitiva(p)
        m = m + g if p[0] == "J" else m - g
    return m


def mallas_componentes():
    servo = trimesh.load(os.path.join(d.COMPONENTES, "MG90S_grabcad_mg90s9.stl"), force="mesh")
    cajas_locales = {"bateria": ((0, 0, 0), (62.0, 23.4, 16.7)), "XL4015": ((0, 0, 0), (52.3, 12.0, 23.5)),
                     "PCA9685": ((-1.9, -6.5, -2.0), (60.3, 18.9, 10.1)), "ESP32": ((-2.4, -3.7, -10.2), (26.6, 49.4, 3.3)),
                     "IMU": ((0, 0, 0), (21.2, 3.0, 16.4))}
    out = []
    for nombre, ruta, M, masa in d.componentes():
        if nombre.startswith("servo"):
            m = servo.copy()
        else:
            lo, hi = cajas_locales[nombre]
            m = trimesh.creation.box(bounds=[lo, hi])
        m.apply_transform(M)
        out.append((nombre, m, masa))
    return out


# =====================================================================
# SEGMENTO: PESO Y CENTRO DE MASA
# =====================================================================
def main():
    os.makedirs(SALIDA, exist_ok=True)
    piezas = {}
    print("PIEZAS (PLA, relleno efectivo %.0f %%)" % (d.RELLENO * 100))
    problemas = []
    for nombre, prims in d.piezas().items():
        m = malla_pieza(prims)
        t = a_trimesh(m)
        cuerpos = len(t.split(only_watertight=False))
        g = m.volume() / 1000 * d.DENSIDAD_PLA * d.RELLENO
        piezas[nombre] = (m, t, g)
        t.export(os.path.join(SALIDA, nombre + ".stl"))
        aviso = "" if cuerpos == 1 else f"   <-- {cuerpos} CUERPOS"
        if cuerpos != 1:
            problemas.append(f"{nombre}: {cuerpos} cuerpos")
        print(f"  {nombre:24s} {g:6.1f} g  caja {np.round(t.extents, 1).tolist()}{aviso}")
    comp = mallas_componentes()
    masa_plastico = sum(g for _, _, g in piezas.values())
    masa_comp = sum(m for _, _, m in comp) + sum(m for _, m, _ in d.EXTRAS)
    total = masa_plastico + masa_comp
    momento = sum(t.center_mass * g for _, t, g in piezas.values()) + sum(m.center_mass * g for _, m, g in comp) + \
        sum(np.asarray(p) * g for _, g, p in d.EXTRAS)
    cdm = momento / total
    todas = [t for _, t, _ in piezas.values()] + [m for _, m, _ in comp]
    lo = np.min([t.bounds[0] for t in todas], axis=0)
    hi = np.max([t.bounds[1] for t in todas], axis=0)
    print(f"\nPESO: plastico {masa_plastico:.0f} g + componentes {masa_comp:.0f} g = {total:.0f} g")
    print(f"MEDIDAS: ancho {hi[0] - lo[0]:.0f} x alto {hi[1] - lo[1]:.0f} x fondo {hi[2] - lo[2]:.0f} mm")
    alto_cdm = cdm[1] - lo[1]
    print(f"CENTRO DE MASA: x {cdm[0]:+.1f}  z {cdm[2]:+.1f} (adelante +)  | a {alto_cdm:.0f} mm del piso "
          f"({100 * alto_cdm / (hi[1] - lo[1]):.0f} % de la altura)")
    x0, x1, z0, z1 = d.PIE
    print(f"PIES: {x1 - x0:.0f} x {z1 - z0:.0f} mm cada uno; apoyo total x {-x1:.0f}..{x1:.0f}, z {z0:.0f}..{z1:.0f}; "
          f"margen del CDM: adelante {z1 - cdm[2]:.0f}, atras {cdm[2] - z0:.0f} mm")

    # =====================================================================
    # SEGMENTO: CHOQUES (piezas entre si y con los componentes)
    # =====================================================================
    objetos = [(n, m) for n, (m, _, _) in piezas.items()] + [(n, a_manifold(t)) for n, t, _ in comp]
    cajas = {n: (np.array(m.bounding_box()[:3]), np.array(m.bounding_box()[3:])) for n, m in objetos}
    print("\nCHOQUES (> 0.5 mm3):")
    hay = False
    for (na, ma), (nb, mb) in itertools.combinations(objetos, 2):
        la, ha = cajas[na]
        lb, hb = cajas[nb]
        if np.any(ha < lb) or np.any(hb < la):
            continue
        v = (ma ^ mb).volume()
        if v > 0.5:
            hay = True
            print(f"  {na} <-> {nb}: {v:.1f} mm3")
            problemas.append(f"choque {na} / {nb}: {v:.1f} mm3")
    if not hay:
        print("  ninguno")
    with open(os.path.join(SALIDA, "resumen.txt"), "w", encoding="utf-8") as f:
        f.write(f"peso {total:.0f} g (plastico {masa_plastico:.0f}, componentes {masa_comp:.0f})\n")
        f.write(f"centro de masa {np.round(cdm, 1).tolist()} -> {alto_cdm:.0f} mm del piso\n")
        f.write("\n".join(problemas) + "\n")
    if "--sin_imagenes" not in sys.argv:
        imagenes(piezas, comp, cdm)


def imagenes(piezas, comp, cdm):
    import pyvista as pv
    colores = {"servo": "#262626", "bateria": "#c8a400", "XL4015": "#2a6fbf", "PCA9685": "#2e8b57", "ESP32": "#333366", "IMU": "#7a1f8f"}
    pl = pv.Plotter(off_screen=True, window_size=(2100, 1100), shape=(1, 3), border=False)
    todas = [t for _, t, _ in piezas.values()]
    c = np.mean([t.bounds.mean(0) for t in todas], axis=0)
    vistas = [((0, 0.05, 1), "Frente"), ((1, 0.05, 0), "Costado"), ((0.8, 0.45, 1.0), "3/4")]
    for k, (dv, tit) in enumerate(vistas):
        pl.subplot(0, k)
        pl.set_background("#eef2f6", top="#a9bccf")
        for n, (_, t, _) in piezas.items():
            pl.add_mesh(pv.wrap(t), color="#f2f2ef", specular=0.2, opacity=0.55 if n == "R2_tapa_torso" else 1.0)
        for n, t, _ in comp:
            pl.add_mesh(pv.wrap(t), color=next((v for k_, v in colores.items() if n.startswith(k_)), "#555"))
        pl.add_mesh(pv.Sphere(radius=5, center=cdm), color="red")
        pl.add_text(tit + "  (punto rojo = centro de masa)", font_size=10, color="black")
        dv = np.array(dv, float); dv /= np.linalg.norm(dv)
        pl.camera_position = [tuple(c + dv * 650), tuple(c), (0, 1, 0)]
    pl.screenshot(os.path.join(SALIDA, "robot2_vistas.png"))
    print("imagenes en", SALIDA)


if __name__ == "__main__":
    main()
