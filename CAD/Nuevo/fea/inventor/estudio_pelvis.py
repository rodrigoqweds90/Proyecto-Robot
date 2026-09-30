"""SEGMENTO: ESTUDIO DEL GENERADOR DE FORMA DE LA PELVIS (manejado por la interfaz de Inventor)"""
import os
import sys
import time

import numpy as np

import ui_inv as ui

BASE = r"C:\Users\rodri\Documents\PlatformIO\Projects\Proyecto Robot\CAD\Nuevo"


def preparar():
    app = ui.inventor_com()
    for i in range(app.Documents.Count, 0, -1):
        doc = ui.d(app.Documents.Item(i))
        if doc.FullFileName.lower().endswith("pelvis.ipt"):
            doc.Close(True)                                  # descarta el estudio sin guardar
    doc = ui.d(app.Documents.Open(os.path.join(BASE, "Pelvis.ipt"), True))
    doc.Activate()
    ui.al_frente()
    ui.ejecutar(app, "GddCreateTOCmd", 4)
    dlg = ui.esperar_dialogo("Generador de forma", 3)
    if dlg is not None:
        ui.marcar(dlg, "No volver a mostrar este mensaje", True)
        ui.boton(dlg, "Aceptar")
        time.sleep(2)
    frente_pernos = ([0, 0, -1], [0, -15, 41.6], 70)
    atras_horns = ([0, 0, 1], [0, -15, -0.2], 70)
    arriba = ([0, -1, 0], [0, 0, 21], 70)
    abajo = ([0, 1, 0], [0, -4.88, 21], 70)
    brazos = {}
    for s in (1, -1):
        a = np.array([-0.865 * s, 0.501]); a /= np.linalg.norm(a)
        brazos[s] = a
    print("fija pernos:", ui.restriccion_fija(app, frente_pernos, [[s * 21.0 + 2.4 * s, -25.0, 41.6] for s in (1, -1)]))
    time.sleep(1.5)
    print("fija horns:", ui.restriccion_fija(app, atras_horns, [list(np.r_[np.array([21.0 * s, -25.0]) + brazos[s] * 10.0, -0.2]) for s in (1, -1)]))
    time.sleep(1.5)
    print("fuerza disco:", ui.carga(app, "FeaCreateLoadForceCmd", "Fuerza", arriba, [[14.0, 0.0, 25.35]], (0, -10, 0), "N"))
    print("momento cintura:", ui.carga(app, "FeaCreateLoadMomentCmd", "Momento", abajo, [[15.0, -4.88, 25.35]], (0, 24.5, 0), "N cm"))
    for s in (1, -1):
        print(f"region perno {s}:", ui.region_conservada(app, frente_pernos, [s * 21.0 + 2.4 * s, -25.0, 41.6], [s * 21.0, -25.0, 41.1], [10, 10, 6]))
    for s in (1, -1):
        c = np.array([21.0 * s, -25.0]) + brazos[s] * 7.0
        clic = np.array([21.0 * s, -25.0]) + brazos[s] * 10.0
        print(f"region horn {s}:", ui.region_conservada(app, atras_horns, [clic[0], clic[1], -0.2], [c[0], c[1], -0.6], [24, 18, 4.6]))
    print("region disco:", ui.region_conservada(app, arriba, [14.0, 0.0, 25.35], [0, -1.5, 25.35], [37, 3.2, 37]))
    print("region cruz:", ui.region_conservada(app, abajo, [15.0, -4.88, 25.35], [0, -5.0, 25.35], [41, 4.6, 20]))
    ui.mirar(app, [-1, -0.6, -1], [0, -15, 21], 110)
    img = ui.captura_inventor(os.path.join(os.environ["TEMP"], "ui", "estudio.png"))
    img.thumbnail((1400, 900)); img.save(os.path.join(os.environ["TEMP"], "ui", "estudio_chico.png"))
    print([l.strip() for l in ui.arbol(app) if any(k in l for k in ("Restricción", "Fuerza", "Momento", "Región"))])


if __name__ == "__main__":
    preparar()
