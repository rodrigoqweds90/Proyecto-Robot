"""SEGMENTO: REVISION DE TODOS LOS STL DEL PAQUETE (imprimir_B)
Para cada archivo que se va a imprimir:
  - malla cerrada, normales coherentes, un solo cuerpo y volumen positivo
  - sin triangulos degenerados ni vertices repetidos sueltos
  - apoyada en z = 0 y dentro de la cama de la A1 (256 mm)
  - el mismo volumen que su STL de origen (solo cambia la orientacion)
  - los mismos archivos que el zip de Descargas y que lista.csv
Uso: ROBOT_VARIANTE=B python verificar_stl.py
"""
import csv
import glob
import os
import sys
import zipfile

import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import paquete_impresion as pq  # noqa: E402
import verificar_impresion as vi  # noqa: E402

CAMA = 256.0
TOL_VOLUMEN = 0.5       # mm3 de diferencia admitida contra el STL de origen


def fuentes():
    _, _, cuenta, origen = vi.lista_impresas()
    for s in sorted(glob.glob(os.path.join(BASE, "piezas_soportes", "*.stl"))):
        origen[os.path.splitext(os.path.basename(s))[0]] = s
    return origen


def revisar(ruta, origen):
    m = trimesh.load(ruta, force="mesh")
    fallas = []
    if not m.is_watertight:
        fallas.append("abierta")
    if not m.is_winding_consistent:
        fallas.append("normales cruzadas")
    cuerpos = len(m.split(only_watertight=False))
    if cuerpos != 1:
        fallas.append(f"{cuerpos} cuerpos")
    if m.volume <= 0:
        fallas.append("volumen negativo (normales al reves)")
    degeneradas = int((m.area_faces < 1e-8).sum())
    if degeneradas:
        fallas.append(f"{degeneradas} triangulos degenerados")
    if not np.isfinite(m.vertices).all():
        fallas.append("vertices no finitos")
    lo, hi = m.bounds
    if abs(lo[2]) > 0.01:
        fallas.append(f"no apoya en z=0 (z min {lo[2]:.2f})")
    if max(m.extents) > CAMA:
        fallas.append(f"no entra en la cama ({max(m.extents):.0f} mm)")
    if origen:
        o = trimesh.load(origen, force="mesh")
        if abs(o.volume - m.volume) > TOL_VOLUMEN:
            fallas.append(f"volumen distinto al de origen ({o.volume:.1f} vs {m.volume:.1f} mm3)")
        if not np.allclose(sorted(o.extents), sorted(m.extents), atol=0.01):
            fallas.append("medidas distintas a las de origen")
    return m, cuerpos, fallas


def main():
    origen = fuentes()
    archivos = sorted(glob.glob(os.path.join(pq.SALIDA, "*.stl")))
    print(f"{'archivo':22s} {'caras':>7s} {'cerrada':>7s} {'cuerpos':>7s} {'cm3':>7s} {'caja mm':>16s}  estado")
    malos = []
    for ruta in archivos:
        nombre = os.path.splitext(os.path.basename(ruta))[0]
        m, cuerpos, fallas = revisar(ruta, origen.get(nombre))
        caja = "x".join(f"{e:.0f}" for e in m.extents)
        print(f"{nombre:22s} {len(m.faces):7d} {str(m.is_watertight):>7s} {cuerpos:7d} {m.volume / 1000:7.2f} {caja:>16s}  "
              f"{'OK' if not fallas else ', '.join(fallas)}")
        if fallas:
            malos.append((nombre, fallas))
        if nombre not in origen:
            print(f"    (sin STL de origen para comparar: {nombre})")
    # lista.csv y zip
    with open(os.path.join(pq.SALIDA, "lista.csv"), encoding="utf-8-sig") as f:
        filas = [r for r in csv.reader(f) if r and r[2:3] and r[2].endswith(".stl")]
    en_lista = {r[2] for r in filas}
    en_carpeta = {os.path.basename(a) for a in archivos}
    with zipfile.ZipFile(pq.ZIP) as z:
        en_zip = {n for n in z.namelist() if n.endswith(".stl")}
    print(f"\npiezas: {len(archivos)} archivos, {sum(int(r[1]) for r in filas)} impresiones en total")
    for etiqueta, falta in (("no estan en lista.csv", en_carpeta - en_lista), ("estan en lista.csv pero no en la carpeta", en_lista - en_carpeta),
                            ("no estan en el zip", en_carpeta - en_zip), ("estan en el zip pero no en la carpeta", en_zip - en_carpeta)):
        if falta:
            print(f"  ojo, {etiqueta}: {sorted(falta)}")
            malos.append((etiqueta, sorted(falta)))
    print(f"\nSTL revisados: {len(archivos)} | con problema: {len(malos)}")
    for nombre, fallas in malos:
        print("  ", nombre, fallas)


if __name__ == "__main__":
    main()
