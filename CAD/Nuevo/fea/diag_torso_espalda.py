"""Torso con la tapa de la espalda atornillada (se modela pegada en su cara de apoyo)."""
import os, numpy as np, trimesh, fea_pieza as fp, todas
NUEVO = todas.NUEVO
t = trimesh.load(os.path.join(NUEVO, "stl", "Torso_cuerpo.stl"), force="mesh")
e = trimesh.load(os.path.join(NUEVO, "stl", "Torso_espalda.stl"), force="mesh")
e.apply_translation([0, 0, 0.02])            # 0.02 mm de solape para que quede un solo cuerpo
u = trimesh.boolean.union([t, e], engine="manifold")
ruta = os.path.join(fp.AQUI, "tmp_torso_espalda.stl")
u.export(ruta)
print("union valida", u.is_volume, "cuerpos", len(u.split(only_watertight=False)))
L, casos = todas.interfaces_torso()
m = fp.mallar(ruta, 1.0, 0.3)
its = fp.interfaces_desde_agujeros(m, L)
vm, det = fp.resolver_casos(m, its, casos)
for k, (v, n) in det.items():
    mx = fp.esfuerzo_util(m, v, n)[1]
    print(f"{k}: max util {mx:.1f} MPa -> FS {20 / mx:.2f}")
