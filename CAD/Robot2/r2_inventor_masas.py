"""ROBOT 2 - MASAS EN INVENTOR: abre Robot2.iam invisible, sobreescribe en memoria la masa de cada pieza
(PLA impreso) y componente (masas reales + cables), lee el centro de gravedad de Inventor y lo compara con
r2_masas_reales. Cierra todo SIN GUARDAR y comprueba que ningun archivo en disco cambio.
Uso: python r2_inventor_masas.py [bateria_g]
"""
import glob
import os
import sys

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import r2_diseno as d  # noqa: E402
import r2_inventor as ri  # noqa: E402
import r2_masas_reales as mr  # noqa: E402

COMPONENTES = os.path.abspath(d.COMPONENTES)


def norm(p):
    return os.path.normcase(os.path.abspath(p))


def tipo_componente(archivo):
    """archivo del componente -> clave de MASAS"""
    for prefijo, clave in (("MG90S", "MG90S"), ("Bateria", "bateria"), ("XL4015", "XL4015"), ("IMU", "IMU"),
                           ("PCA9685", "PCA9685"), ("ESP32", "ESP32")):
        if archivo.startswith(prefijo):
            return clave
    return None


def fotos_disco():
    rutas = glob.glob(os.path.join(BASE, "piezas", "*.ipt")) + [ri.ENSAMBLE] + \
        glob.glob(os.path.join(COMPONENTES, "**", "*.i[pa][tm]"), recursive=True)
    return {r: (os.path.getmtime(r), os.path.getsize(r)) for r in rutas}


# =====================================================================
# SEGMENTO: INVENTOR (todo en memoria)
# =====================================================================
def medir(app, bateria):
    masas = dict(mr.MASAS, bateria=bateria)
    asm = ri.dyn(app.Documents.Open(ri.ENSAMBLE, False))
    occs = asm.ComponentDefinition.Occurrences
    comps = d.componentes()
    hechos, info = {}, []
    for i in range(1, occs.Count + 1):
        o = ri.dyn(occs.Item(i))
        doc = ri.dyn(o.Definition.Document)
        archivo = os.path.basename(doc.FullFileName)
        t = ri.dyn(o.Transformation).Translation
        pos = np.array([t.X, t.Y, t.Z]) * 10.0
        if archivo.startswith("R2_"):
            nombre, clave = os.path.splitext(archivo)[0], "pla"
        else:
            clave = tipo_componente(archivo)
            cand = [(np.linalg.norm(M[:3, 3] - pos), n) for n, ruta, M, _ in comps
                    if os.path.basename(ruta) == archivo]
            nombre = min(cand)[1] if cand else archivo
        if clave is None:
            raise RuntimeError(f"ocurrencia sin masa asignada: {o.Name} ({archivo})")
        mp = ri.dyn(doc.ComponentDefinition.MassProperties)
        if doc.FullFileName not in hechos:
            antes = mp.Mass * 1000
            if clave == "pla":
                nueva = mp.Volume * d.DENSIDAD_PLA * d.RELLENO
            else:
                nueva = masas[clave] * (1 + mr.CABLES)
            mp.Mass = nueva / 1000.0
            hechos[doc.FullFileName] = (antes, nueva, mp.Volume)
        info.append((nombre, o))
    asm.Update()
    mpa = ri.dyn(asm.ComponentDefinition.MassProperties)
    c = ri.dyn(mpa.CenterOfMass)
    total = mpa.Mass * 1000
    cog = np.array([c.X, c.Y, c.Z]) * 10.0
    por_ocurrencia = {}
    for nombre, o in info:
        m = ri.dyn(o.MassProperties)
        p = ri.dyn(m.CenterOfMass)
        por_ocurrencia[nombre] = (m.Mass * 1000, np.array([p.X, p.Y, p.Z]) * 10.0)
    return asm, total, cog, por_ocurrencia, hechos


def main():
    bateria = float(sys.argv[1]) if len(sys.argv) > 1 else mr.MASAS["bateria"]
    app = ri.inventor()
    propios = (norm(BASE), norm(COMPONENTES))
    abiertos = {norm(ri.dyn(app.Documents.Item(i)).FullFileName) for i in range(1, app.Documents.Count + 1)}
    choque = [p for p in abiertos if p.startswith(propios)]
    if choque:
        sys.exit("Cierra en Inventor estos documentos antes de correr el script:\n  " + "\n  ".join(choque))
    disco = fotos_disco()
    asm = None
    app.SilentOperation = True
    try:
        asm, total, cog, occ, hechos = medir(app, bateria)
    finally:
        if asm is not None:
            asm.Close(True)                                 # True = sin guardar
        for i in range(app.Documents.Count, 0, -1):         # referencias que quedaron cargadas por el ensamble
            doc = ri.dyn(app.Documents.Item(i))
            if norm(doc.FullFileName) not in abiertos and norm(doc.FullFileName).startswith(propios):
                doc.Close(True)
        app.SilentOperation = False

    # =====================================================================
    # SEGMENTO: CORRECCIONES SIN MODELO PROPIO Y COMPARACION
    # =====================================================================
    # las caderas usan el mismo .ipt que el MG90S (un solo override por archivo): se suma la diferencia del MG92B
    # en el CdG que Inventor da para esas ocurrencias; OLED e interruptor no tienen modelo en el ensamble
    extra = [((mr.MASAS["MG92B"] - mr.MASAS["MG90S"]) * (1 + mr.CABLES), occ[f"servo_cadera_{l}"][1]) for l in ("izq", "der")]
    extra += [(mr.MASAS[n] * (1 + mr.CABLES), np.array(p, float)) for n, _, p in d.EXTRAS if n in mr.MASAS]
    m_inv = total + sum(m for m, _ in extra)
    c_inv = (total * cog + sum(m * p for m, p in extra)) / m_inv

    r, cs = mr.analizar(bateria)
    c_py = np.array(r["cdm_mm"])
    print(f"Override en memoria de {len(hechos)} documentos (PLA {d.DENSIDAD_PLA} g/cm3 x {d.RELLENO}, electronica +{mr.CABLES:.0%})")
    print(f"\n{'':22s}{'masa g':>9s}{'X':>8s}{'Y':>8s}{'Z':>8s}")
    print(f"{'Inventor (ensamble)':22s}{total:9.1f}" + "".join(f"{v:8.1f}" for v in cog))
    print(f"{'Inventor + correcc.':22s}{m_inv:9.1f}" + "".join(f"{v:8.1f}" for v in c_inv))
    print(f"{'Python (mallas)':22s}{r['total_g']:9.1f}" + "".join(f"{v:8.1f}" for v in c_py))
    dif = c_inv - c_py
    print(f"{'diferencia':22s}{m_inv - r['total_g']:9.1f}" + "".join(f"{v:8.1f}" for v in dif) + f"   |d| = {np.linalg.norm(dif):.2f} mm")
    print(f"altura del CdG sobre el piso (Inventor): {c_inv[1] - d.SUELA_Y:.1f} mm")

    print("\nCuerpos con diferencia > 0.5 mm o > 2 % de masa (Inventor vs Python):")
    py = {n: (m, p) for n, m, p, _ in cs}
    hay = False
    for n, (m, p) in occ.items():
        if n not in py:
            continue
        mp_, pp = py[n]
        dist = np.linalg.norm(p - pp)
        if n.startswith("servo_cadera"):
            mp_ = mr.MASAS["MG90S"] * (1 + mr.CABLES)        # Inventor usa la masa del MG90S en las caderas
        if dist > 0.5 or abs(m - mp_) > 0.02 * mp_:
            hay = True
            print(f"  {n:26s} masa {m:6.1f} vs {mp_:6.1f} g   CdG desplazado {dist:5.1f} mm  {np.round(p - pp, 1).tolist()}")
    if not hay:
        print("  ninguno")
    print("\nMasa que Inventor tenia antes del override (material del archivo):")
    for ruta, (antes, nueva, vol) in sorted(hechos.items()):
        print(f"  {os.path.basename(ruta):40s} {antes:7.1f} g -> {nueva:6.1f} g   ({vol:6.2f} cm3)")

    cambiados = [r_ for r_, v in disco.items() if not os.path.exists(r_) or (os.path.getmtime(r_), os.path.getsize(r_)) != v]
    print("\nArchivos en disco modificados:", cambiados or "ninguno")


if __name__ == "__main__":
    main()
