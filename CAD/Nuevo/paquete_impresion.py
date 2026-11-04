"""SEGMENTO: PAQUETE DE IMPRESION DEL MODELO B
Junta en imprimir_B/ las piezas que usa el ensamble B (misma fuente que verificar_impresion.py) mas los
soportes de armado, cada una ya acostada sobre la cara que menos volumen de soporte pide (de las 6 caras de su caja) y apoya bien,
con lista.csv (cantidades, cara abajo, soporte, masa), LEEME.txt, y el zip en Descargas.
Uso: ROBOT_VARIANTE=B python paquete_impresion.py
"""
import csv
import glob
import os
import shutil
import sys
import zipfile

import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import verificar_impresion as vi  # noqa: E402

SALIDA = os.path.join(BASE, "imprimir_B")
ZIP = os.path.join(os.path.expanduser("~"), "Downloads", "Robot_B_imprimir.zip")
REPUESTOS = {"Pipe_M3": 4, "Pipe_M3_alto": 2}
VOLADIZO = np.cos(np.radians(45))     # caras que miran hacia abajo a menos de 45 grados piden soporte
# color de PLA: blanco la carroceria (lo que se ve como "cuerpo" del robot), negro la mecanica (brackets,
# eslabones y bujes, que ademas quedan del color de los servos MG90S)
BLANCO = ("Torso_", "Cabeza", "Pelvis", "Spacer01", "Bracket11_B", "Bracket12_B")
NOTAS = {
    "Bracket01_B_cadera": "cadera IZQUIERDA con MG92B (piso rebajado); el Bracket01_B normal va en el tobillo derecho",
    "Bracket03_B_cadera": "cadera DERECHA con MG92B (piso rebajado); el Bracket03_B normal va en el tobillo izquierdo",
    "Pipe_M3": "relleno 100%, 4 paredes, cabeza sobre la cama",
    "Pipe_M3_alto": "relleno 100%, 4 paredes, cabeza sobre la cama",
    "Torso_cuerpo_B": "espalda abajo sobre los 4 postes, soporte de arbol y borde (brim) de 5 mm; imprimir primero y probar las placas",
    "Torso_atras_B": "soporte de arbol y borde (brim) de 5 mm",
    "Cabeza_frente": "parada (cara vertical); el soporte queda adentro bajo el techo y sale por atras",
    "Torso_pecho": "de costado; borde (brim) de 5 mm porque es alta y fina",
    "Pelvis": "boca abajo sobre el disco de la cintura",
    "Bracket11_B": "mano izquierda", "Bracket12_B": "mano derecha",
    "Soporte_pierna_izq": "armado, no va en el robot", "Soporte_pierna_der": "armado, no va en el robot",
    "Soporte_parado": "armado, no va en el robot",
}
def tornillos():
    """los de las 36 articulaciones salen de m3_pernos (piezas_m3/tornillos_m3.json); el resto son fijos."""
    import collections
    import json
    por_largo = collections.Counter()
    for r in json.load(open(os.path.join(BASE, "piezas_m3", "tornillos_m3.json"), encoding="utf-8")):
        por_largo[r["largo"]] += r["cantidad"]
    fijos = [(10, 2, "pecho"), (10, 2, "tapa de la cabeza"), (8, 2, "pared de atras al cuerpo"),
             (6, 2, "giroscopio GY-521")]
    usos = collections.defaultdict(list)
    for largo, cant in sorted(por_largo.items()):
        usos[largo].append(f"{cant} articulaciones")
        por_largo[largo] = cant
    for largo, cant, uso in fijos:
        usos[largo].append(f"{cant} {uso}")
        por_largo[largo] += cant
    filas = [(f"M3x{largo} cabeza boton", por_largo[largo], " + ".join(usos[largo])) for largo in sorted(por_largo)]
    filas += [("M2x8 maquina", 4, "aro de la cintura al torso, desde abajo: roscan directo en agujeros de 1.7"),
              ("M2x6 maquina", 12, "8 pestanas de los 4 servos del torso (cintura, cuello, hombros) + 4 de la pantalla OLED "
                                   "en la cabeza: roscan directo en agujeros de 1.7"),
              ("Tornillos del kit del MG90S", "-", "pestanas de servos de piernas y brazos + horns + 4 del PCA9685")]
    return filas



APOYO_MINIMO = 150.0            # mm2 en la cama (o la mitad del mejor apoyo posible, si la pieza es chica)
# cara abajo elegida a mano donde la cuenta de soporte no alcanza:
#  - torso: espalda abajo; el soporte queda todo afuera, y el interior (guias, postes, repisa) abre hacia
#    arriba sin soportes adentro
#  - frente de la cabeza: parada, la cara sale limpia (boca abajo el marco apoya y la cara queda con marcas)
CARA_FIJA = {"Torso_cuerpo_B": "-z", "Cabeza_frente": "-y"}


def orientar(m, fija=None):
    """de las 6 caras de la caja, la que pide menos volumen de soporte (cada cara en voladizo hasta lo que tiene
    debajo: la misma pieza o la cama), entre las que apoyan bien en la cama."""
    opciones = []
    for eje in range(3):
        for signo in (1, -1):
            abajo = np.zeros(3)
            abajo[eje] = signo
            R = trimesh.geometry.align_vectors(abajo, [0, 0, -1])
            q = m.copy()
            q.apply_transform(R)
            q.apply_translation(-q.bounds[0])
            nz, c = q.face_normals[:, 2], q.triangles_center
            cama = (nz < -0.996) & (c[:, 2] < 0.05)
            vol = (nz < -VOLADIZO) & ~cama
            apoyo = q.area_faces[cama].sum()
            soporte = 0.0
            if vol.any():
                if len(q.faces) > 50000:            # soportes de armado: solidos de alturas, basta con el area
                    soporte = float(q.area_faces[vol].sum() * 10)
                else:
                    o = c[vol] - [0, 0, 0.01]
                    d = c[vol, 2].copy()
                    hits, rays, _ = q.ray.intersects_location(o, np.tile([0, 0, -1.0], (len(o), 1)), multiple_hits=False)
                    if len(rays):
                        d[rays] = o[rays, 2] - hits[:, 2]
                    soporte = float((q.area_faces[vol] * -nz[vol] * d).sum())
            nombre = ("-" if signo < 0 else "+") + "xyz"[eje]
            opciones.append((soporte, apoyo, q, nombre))
    if fija:
        soporte, apoyo, q, nombre = next(o for o in opciones if o[3] == fija)
        return q, nombre, soporte, apoyo
    minimo = min(APOYO_MINIMO, 0.5 * max(o[1] for o in opciones))
    soporte, apoyo, q, nombre = min((o for o in opciones if o[1] >= minimo), key=lambda o: o[0])
    return q, nombre, soporte, apoyo


def main():
    if os.path.exists(SALIDA):
        shutil.rmtree(SALIDA)
    os.makedirs(SALIDA)
    _, _, cuenta, origen = vi.lista_impresas()
    # versiones con MG92B para las caderas (m3_pernos.py): reemplazan una de las copias de la pieza base
    for s in sorted(glob.glob(os.path.join(BASE, "piezas_m3", "*_cadera.stl"))):
        n = os.path.splitext(os.path.basename(s))[0]
        cuenta[n[:-len("_cadera")]] -= 1
        cuenta[n], origen[n] = 1, s
    for s in sorted(glob.glob(os.path.join(BASE, "piezas_soportes", "*.stl"))):
        n = os.path.splitext(os.path.basename(s))[0]
        cuenta[n], origen[n] = 1, s
    filas, total, por_color = [], 0.0, {}
    for nombre in sorted(cuenta, key=lambda n: (n.startswith("Soporte"), n)):
        m = trimesh.load(origen[nombre], force="mesh")
        q, cara, soporte, apoyo = orientar(m, CARA_FIJA.get(nombre))
        q.export(os.path.join(SALIDA, nombre + ".stl"))
        cant = cuenta[nombre] + REPUESTOS.get(nombre, 0)
        g = m.volume / 1000 * vi.DENSIDAD
        if not nombre.startswith("Soporte"):
            total += g * cant
        color = "blanco" if nombre.startswith(BLANCO) else ("el que sea" if nombre.startswith("Soporte") else "negro")
        filas.append([nombre, cant, nombre + ".stl", color, cara, round(soporte / 1000, 1), round(apoyo / 100, 1),
                      round(g, 1), "x".join(f"{e:.0f}" for e in q.extents), NOTAS.get(nombre, "")])
        por_color[color] = por_color.get(color, 0.0) + g * cant
        print(f"{nombre:20s} x{cant:<3d} cara abajo {cara}  soporte {soporte / 1000:5.1f} cm3  apoyo {apoyo / 100:5.1f} cm2  {g:5.1f} g")
    with open(os.path.join(SALIDA, "lista.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["pieza", "cantidad a imprimir", "archivo", "color de PLA", "cara del modelo que va abajo (ya acostada)",
                    "soporte cm3 aprox (0 = sin soportes)", "apoyo en la cama cm2", "g aprox c/u", "caja mm", "notas"])
        w.writerows(filas)
        w.writerow([])
        w.writerow(["tornillo", "cantidad", "uso"])
        w.writerows(tornillos())
    shutil.copy(os.path.join(BASE, "LEEME_imprimir_B.txt"), os.path.join(SALIDA, "LEEME.txt"))
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(SALIDA)):
            z.write(os.path.join(SALIDA, f), f)
    print("plastico por color:", {k: f"{v:.0f} g" for k, v in sorted(por_color.items())})
    print(f"plastico del robot: ~{total:.0f} g | zip: {ZIP} ({os.path.getsize(ZIP) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
