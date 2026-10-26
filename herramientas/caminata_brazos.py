"""SEGMENTO: PRUEBA "ADELANTE PASO" CON BRAZOS (no toca las poses ni secuencias que ya funcionan)
Sobre las poses de "Adelante paso" (caminata_usuario.py) agrega:
  - contrapeso: con el peso en un pie, el brazo de ese lado se abre (ABRE grados) y el otro se pega al cuerpo
    (PEGA grados; mas de ~5 choca con el torso). Simulador (margen sobre el pie, sin brazos 6.8 mm):
      abre 20 -> 7.5 mm, 30 -> 7.8 mm, 45 -> 8.2 mm (60 -> 8.5 mm pero mas lento y se ve como ala). Por defecto 30.
    Ladear menos el cuerpo y dejar que los brazos compensen (--inclina 0.75) NO sirve: el margen baja a ~4 mm,
    los brazos pesan poco (~45 g cada uno, 8 % del robot)
  - balanceo: brazo opuesto a la pierna (pierna derecha adelante -> brazo izquierdo adelante), BALANCEO grados
Signos (probados por el usuario el 2026-10-19): hombro izq (6) + atras, der (9) + adelante; "codo" izq (5) + afuera,
der (10) + adentro.
Poses en la carpeta "pruebas brazos"; secuencia "Prueba adelante paso brazos" (un ciclo para bucle, tiempos con secuencias_finales.escribir_bucle).
Uso: python caminata_brazos.py [--abre 30] [--pega 5] [--balanceo 20] [--inclina 1]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import acelerar_secuencias as ac  # noqa: E402
import caminata_usuario as cu  # noqa: E402
import secuencias_finales as sf  # noqa: E402
import simular_caminata as sc  # noqa: E402

CARPETA = "pruebas brazos"
NOMBRE = "Prueba adelante paso brazos"


def estado(pose):
    """(peso, muslo izq, muslo der) de una pose de la caminata (las 'juntas' son como su base)"""
    base = cu.JUNTAS[pose][0] if pose in cu.JUNTAS else pose
    for nombre, peso, i, d in cu.POSES:
        if nombre == base:
            return peso, i, d
    return 0, 0, 0                                          # Inicionx25


def con_brazos(ang, ref, peso, i, d, abre, pega, balanceo, inclina=1.0):
    a = dict(ang)
    for c in cu.INCLINAR:                                   # inclina < 1: los brazos hacen parte del ladeo
        a[c] = ref[c] + round((ang[c] - ref[c]) * inclina)
    if peso > 0:                                            # peso en el pie derecho
        a[10] = ref[10] - abre                              # brazo derecho afuera
        a[5] = ref[5] - pega                                # izquierdo pegado al cuerpo
    elif peso < 0:
        a[5] = ref[5] + abre
        a[10] = ref[10] + pega
    adelante_izq = balanceo * (d - i) / 2                   # pierna derecha adelante -> brazo izquierdo adelante
    a[6] = ref[6] - adelante_izq
    a[9] = ref[9] - adelante_izq                            # el derecho, al reves (y + es adelante)
    return a


def main():
    abre, pega, balanceo = ac.arg("--abre", 30), ac.arg("--pega", 5), ac.arg("--balanceo", 20)
    inclina = ac.arg("--inclina", 1.0)
    cu.guardar_poses()
    ref = ac.angulos(cu.REF)
    trim = {c: ref[c] for c in sc.cn.PIERNAS}
    original = sf.secuencias()["Adelante paso"][0]
    nombres = []
    for p in original:
        a = con_brazos(ac.angulos(p), ref, *estado(p), abre, pega, balanceo, inclina)
        n = f"{p} brazos"
        json.dump({"nombre": n, "angulos": {str(c): int(round(v)) for c, v in sorted(a.items())}, "carpeta": CARPETA},
                  open(os.path.join(sf.POS, cu.archivo(n)), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        nombres.append(n)
    carpetas = json.load(open(os.path.join(cu.DATOS, "carpetas_poses.json"), encoding="utf-8"))
    if CARPETA not in carpetas:
        json.dump(sorted(carpetas + [CARPETA]), open(os.path.join(cu.DATOS, "carpetas_poses.json"), "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)
    viejo = os.path.join(sf.SEC, "Prueba adelante 3 pasos brazos.json")    # la version de 3 pasos, reemplazada
    if os.path.exists(viejo):
        os.remove(viejo)
    pasos, quieto, v, m = sf.escribir_bucle(NOMBRE, nombres, "Avanzar", trim)
    print(f"{NOMBRE:34s} {sum(p['duracion_ms'] for p in pasos) / 1000:4.1f} s | sincronizado: apoyo >= {quieto:.1f} mm"
          f" | continuo (3 vueltas): apoyo >= {m:.1f} mm, servo sobra {v:.0f} grados/s")


if __name__ == "__main__":
    main()
