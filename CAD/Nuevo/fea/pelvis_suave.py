"""Pelvis: ventanas solo donde el esfuerzo es muy bajo (1.0 / 0.7 MPa); con 2 MPa bajaba el FS a 1.3-2.7."""
import json, os, time
import fea_pieza as fp, todas
lista, casos = todas.interfaces_pelvis()
t0 = time.time()
r = fp.aligerar_ventanas("Pelvis", os.path.join(todas.NUEVO, "step", "Pelvis.stp"), lista, casos, h=1.0,
                         umbrales=(1.0, 0.7), margenes=(3.0,), carpeta_salida=os.path.join(todas.AQUI, "pelvis_suave"), max_pruebas=2)
r["segundos"] = round(time.time() - t0)
print(json.dumps(r), flush=True)
json.dump(r, open(os.path.join(todas.AQUI, "pelvis_suave.json"), "w", encoding="utf-8"), indent=1)
