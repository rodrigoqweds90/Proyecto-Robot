"""SEGMENTO: COPIAR PIEZAS ALIGERADAS A para_imprimir
Guarda las versiones anteriores en para_imprimir/sin_aligerar, copia las aligeradas verificadas
y anota en lista.csv cuanto se quito y el factor de seguridad.
"""
import csv
import json
import os
import shutil

import trimesh

AQUI = os.path.dirname(os.path.abspath(__file__))
NUEVO = os.path.dirname(AQUI)
IMPRIMIR = os.path.join(NUEVO, "para_imprimir")
RESPALDO = os.path.join(IMPRIMIR, "sin_aligerar")
PLA = 1.24          # g/cm3


def main():
    res = json.load(open(os.path.join(AQUI, "resultados.json"), encoding="utf-8"))
    os.makedirs(RESPALDO, exist_ok=True)
    tabla = []
    for nombre, r in sorted(res.items()):
        stl = os.path.join(AQUI, "aligeradas", nombre + ".stl")
        if "error" in r or r.get("quitado_mm3", 0) <= 0 or not os.path.exists(stl):
            print(f"{nombre}: sin aligerar ({r.get('error', 'no se quito material')})")
            continue
        m = trimesh.load(stl, force="mesh")
        if not m.is_watertight or len(m.split(only_watertight=False)) != 1:
            print(f"{nombre}: STL aligerado no valido, se deja el anterior")
            continue
        destino = os.path.join(IMPRIMIR, nombre + ".stl")
        if os.path.exists(destino) and not os.path.exists(os.path.join(RESPALDO, nombre + ".stl")):
            shutil.copy2(destino, os.path.join(RESPALDO, nombre + ".stl"))
        shutil.copy2(stl, destino)
        pct = 100 * r["quitado_mm3"] / r["volumen"]
        tabla.append((nombre, pct, r["quitado_mm3"] / 1000 * PLA, r["fs_inicial"], r["fs_final"]))
        print(f"{nombre}: -{pct:.1f}% ({r['quitado_mm3'] / 1000 * PLA:.1f} g macizo), FS {r['fs_inicial']:.2f} -> {r['fs_final']:.2f}")

    ruta = os.path.join(IMPRIMIR, "lista.csv")
    texto = open(ruta, encoding="utf-8").read()
    piezas, resto = texto.split("\n\n", 1) if "\n\n" in texto else (texto, "")
    filas = list(csv.reader(piezas.strip().splitlines()))
    datos = {n: (p, g, fi, ff) for n, p, g, fi, ff in tabla}
    for f in filas[1:]:
        base = f[3].split(" | aligerada")[0]
        if f[0] in datos:
            p, g, fi, ff = datos[f[0]]
            base += f" | aligerada -{p:.0f}% (FS {ff:.1f})"
        f[3] = base
    with open(ruta, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerows(filas)
        fh.write("\n" + resto)


if __name__ == "__main__":
    main()
