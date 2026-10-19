"""SEGMENTO: VISTA 3D DEL VISOR (piezas reales del CAD movidas con los angulos de la pose)
Usa datos_robot3d/modelo.npz (armar_modelo_3d.py): cada grupo de piezas se mueve como lo mueve su servo:
  cadera  : gira de costado alrededor del eje de cadera (y con ella toda la pierna)
  muslo A/B, canilla A/B : las barras del paralelogramo giran adelante-atras alrededor de su perno de arriba
  rodilla, tobillo : se trasladan (el paralelogramo las mantiene derechas)
  pie     : gira de costado alrededor del eje del tobillo
Despues todo el robot se apoya en el piso con la inclinacion que da el simulador (simular_caminata.analizar).
"""
import math
import os

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor

import simular_caminata as sc

MODELO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos_robot3d", "modelo.npz")
# pernos de arriba de cada barra (y, z) en el marco del simulador, y eje del tobillo
PERNO = {"muslo A": (-19.0, 0.0), "muslo B": (-13.5, 15.0), "canilla A": (-62.7, 0.0), "canilla B": (-68.2, 15.0)}
TOBILLO_Y = -110.4
COLOR = {"pieza": "#f2f2f2", "servo": "#2b2b2b", "izq": "#93c5fd", "der": "#fca5a5"}


def mat(R=None, t=(0.0, 0.0, 0.0)):
    M = np.eye(4)
    if R is not None:
        M[:3, :3] = R
    M[:3, 3] = t
    return M


def girar_en(R, punto):
    p = np.asarray(punto, dtype=float)
    return mat(t=p) @ mat(R) @ mat(t=-p)


def transformaciones(ang, trim, res):
    """matriz 4x4 de cada grupo (grupo, lado) para la pose, ya apoyado en el piso"""
    art = sc.articulaciones(ang, trim)
    f = sc.ADELANTE_FISICO
    rl, rf = res["inc"]
    R = sc.rot_x(rf) @ sc.rot_z(rl)
    piso = (R @ np.array([sc.CADERA_X, 0.0, 0.0]))[1] - res["mundo"]["izq"][0][0][1]
    mundo = mat(R, (0.0, -piso, 0.0))
    out = {("cuerpo", ""): mundo}
    for lado, sx in (("izq", 1.0), ("der", -1.0)):
        lat, mus, can, tob = art[lado]
        m, r = math.radians(mus), math.radians(can)
        cadera = mundo @ girar_en(sc.rot_z(math.radians(lat)), (sx * sc.CADERA_X, 0.0, 0.0))
        rodilla = (0.0, sc.L1 * (1 - math.cos(m)), f * sc.L1 * math.sin(m))
        tobillo = tuple(a + b for a, b in zip(rodilla, (0.0, sc.L2 * (1 - math.cos(r)), f * sc.L2 * math.sin(r))))
        out[("cadera", lado)] = cadera
        for barra in ("muslo A", "muslo B"):
            out[(barra, lado)] = cadera @ girar_en(sc.rot_x(-f * m), (0.0, *PERNO[barra]))
        out[("rodilla", lado)] = cadera @ mat(t=rodilla)
        for barra in ("canilla A", "canilla B"):
            out[(barra, lado)] = cadera @ mat(t=rodilla) @ girar_en(sc.rot_x(-f * r), (0.0, *PERNO[barra]))
        out[("tobillo", lado)] = cadera @ mat(t=tobillo)
        out[("pie", lado)] = cadera @ mat(t=tobillo) @ girar_en(sc.rot_z(-math.radians(tob)), (sx * sc.CADERA_X, TOBILLO_Y, 0.0))
    return out


class Vista3D(QtInteractor):
    def __init__(self, parent=None):
        super().__init__(parent)
        datos = np.load(MODELO)
        claves = sorted({k.rsplit("|", 1)[0] for k in datos.files})
        self.actores = {}
        for clave in claves:
            grupo, lado, tipo = clave.split("|")
            v, f = datos[clave + "|v"], datos[clave + "|f"]
            malla = pv.PolyData(v, np.hstack([np.full((len(f), 1), 3), f]).ravel())
            actor = self.add_mesh(malla, color=COLOR[tipo], smooth_shading=True, specular=0.2)
            self.actores[(grupo, lado, tipo)] = actor
        self.add_mesh(pv.Plane(center=(0, 0, 0), direction=(0, 1, 0), i_size=500, j_size=500, i_resolution=20,
                               j_resolution=20), color="#4b5563", style="wireframe", opacity=0.5)
        self.com = self.add_mesh(pv.Sphere(radius=5), color="#22c55e")
        self.com_linea = self.add_mesh(pv.Line((0, 0, 0), (0, 1, 0)), color="#22c55e", line_width=2)
        self.set_background("#111827")
        self.camera_position = [(340, 240, 460), (0, 80, 10), (0, 1, 0)]
        self.add_axes()

    def mostrar(self, ang, trim, res):
        T = transformaciones(ang, trim, res)
        for (grupo, lado, tipo), actor in self.actores.items():
            actor.user_matrix = T[(grupo, lado)]
            if grupo == "pie" and tipo == "pieza":     # el pie que apoya se pinta de su color (azul izq, rojo der)
                actor.prop.color = COLOR[lado] if lado in res["toca"] else COLOR["pieza"]
        c = res["com"]
        self.com.user_matrix = mat(t=c)
        self.com_linea.user_matrix = mat(np.diag([1.0, max(c[1], 1.0), 1.0]), (c[0], 0.0, c[2]))
        self.render()
