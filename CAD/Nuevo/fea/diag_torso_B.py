import os, numpy as np, fea_pieza as fp, todas
import torso as to
L, casos = todas.interfaces_torso()
print("CUBIERTA", to.CUBIERTA, "BAT", to.BAT, "Y_PISO", to.Y_PISO)
m = fp.mallar(os.path.join(todas.NUEVO, "step", "Torso_cuerpo_B.stp"), 1.0, 0.3)
its = fp.interfaces_desde_agujeros(m, L)
for it in its:
    P = m.p[:, it["nodos"]]
    print(it["nombre"], len(it["nodos"]), "nodos, caja", np.round(P.min(1), 1), np.round(P.max(1), 1))
vm, det = fp.resolver_casos(m, its, casos)
centros = m.p[:, m.t].mean(axis=1).T
for k, (v, n) in det.items():
    p995, mx = fp.esfuerzo_util(m, v, n)
    from scipy.spatial import cKDTree
    d, _ = cKDTree(m.p[:, n].T).query(centros)
    lejos = np.where(d > 1.5)[0]
    top = lejos[np.argsort(-v[lejos])[:5]]
    print(f"{k}: max util {mx:.1f} MPa -> FS {20/mx:.2f}; lugares", np.round(centros[top], 1).tolist())
