"""SEGMENTO: BRACKET02 CON PASO DE BRIDA (pieza piloto, version simple)
Solo cortes sobre el STL del NX25:
  - rebaje de salida del cable del servo (hecho por cables_salida.py, en stl_con_canales)
  - canaleta de 1 mm en la cara de arriba de la base, desde cada ranura original del NX25
    (z 23..28, x +-2.5..4.5) hasta el borde: bajo el servo solo hay 1 mm y la brida de
    2.5 mm mide ~1 mm de espesor.
La brida entra por la ranura, sale por la canaleta al costado y abraza el mazo de cables,
que va pegado al costado de atras del servo. Una sola version sirve en las 4 posiciones.
Coordenadas locales de Bracket02 (mm): ancho x -6..6, base y 0..4, largo z 0..43.7.
"""
import os

import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
ENTRADA = os.path.join(BASE, "stl_con_canales", "Bracket02_W.stl")
SALIDA = os.path.join(BASE, "piezas_canales", "Bracket02_W_brida.stl")

BRIDA_ANCHO = 2.5
CANALETA = dict(y=(3.0, 4.1), z=(25.5 - (BRIDA_ANCHO + 0.5) / 2, 25.5 + (BRIDA_ANCHO + 0.5) / 2))   # 1 mm de hondo, 3 de ancho


def caja(x, y, z):
    b = trimesh.creation.box(extents=[x[1] - x[0], y[1] - y[0], z[1] - z[0]])
    b.apply_translation([(x[0] + x[1]) / 2, (y[0] + y[1]) / 2, (z[0] + z[1]) / 2])
    return b


def main():
    pieza = trimesh.load(ENTRADA, force="mesh")
    cortes = [caja((2.4, 6.2), **CANALETA), caja((-6.2, -2.4), **CANALETA)]
    nueva = trimesh.boolean.difference([pieza, trimesh.boolean.union(cortes, engine="manifold")], engine="manifold")
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    nueva.export(SALIDA)
    original = trimesh.load(os.path.join(os.path.dirname(BASE), "NX25_original", "stl", "Bracket02_W.stl"), force="mesh")
    dv = nueva.volume - original.volume
    print(f"Bracket02_W_brida: {dv:+.0f} mm3 respecto del original ({dv * 1.24 * 0.75 / 1000:+.2f} g) | estanco {nueva.is_watertight}")


if __name__ == "__main__":
    main()
