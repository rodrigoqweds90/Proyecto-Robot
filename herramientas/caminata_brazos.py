"""SEGMENTO: PRUEBA "ADELANTE 3 PASOS" CON BRAZOS (no toca las poses ni secuencias que ya funcionan)
Sobre las poses de "Adelante 3 pasos" (caminata_usuario.py) agrega:
  - contrapeso: con el peso en un pie, el brazo de ese lado se abre (ABRE grados) y el otro se pega al cuerpo
    (PEGA grados). Simulador: el margen sobre el pie de apoyo pasa de ~6 a ~8.5 mm
  - balanceo: brazo opuesto a la pierna (pierna derecha adelante -> brazo izquierdo adelante), BALANCEO grados
Signos (probados por el usuario el 2026-10-19): hombro izq (6) + atras, der (9) + adelante; "codo" izq (5) + afuera,
der (10) + adentro.
Poses en la carpeta "pruebas brazos"; secuencia "Prueba adelante 3 pasos brazos" (tiempos con acelerar_secuencias).
Uso: python caminata_brazos.py [--abre 60] [--pega 5] [--balanceo 20]
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
NOMBRE = "Prueba adelante 3 pasos brazos"


def estado(pose):
    """(peso, muslo izq, muslo der) de una pose de la caminata (las 'juntas' son como su base)"""
    base = cu.JUNTAS[pose][0] if pose in cu.JUNTAS else pose
    for nombre, peso, i, d in cu.POSES:
        if nombre == base:
            return peso, i, d
    return 0, 0, 0                                          # Inicionx25


def con_brazos(ang, ref, peso, i, d, abre, pega, balanceo):
    a = dict(ang)
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
    abre, pega, balanceo = ac.arg("--abre", 60), ac.arg("--pega", 5), ac.arg("--balanceo", 20)
    cu.guardar_poses()
    ref = ac.angulos(cu.REF)
    trim = {c: ref[c] for c in sc.cn.PIERNAS}
    original = sf.secuencias()["Adelante 3 pasos"][0]
    nombres = []
    for p in original:
        if p == cu.REF:
            nombres.append(p)
            continue
        a = con_brazos(ac.angulos(p), ref, *estado(p), abre, pega, balanceo)
        n = f"{p} brazos"
        json.dump({"nombre": n, "angulos": {str(c): int(round(v)) for c, v in sorted(a.items())}, "carpeta": CARPETA},
                  open(os.path.join(sf.POS, cu.archivo(n)), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        nombres.append(n)
    carpetas = json.load(open(os.path.join(cu.DATOS, "carpetas_poses.json"), encoding="utf-8"))
    if CARPETA not in carpetas:
        json.dump(sorted(carpetas + [CARPETA]), open(os.path.join(cu.DATOS, "carpetas_poses.json"), "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)
    for nombre, poses in ((NOMBRE, nombres), ("Adelante 3 pasos", original)):
        if nombre == NOMBRE:
            sf.escribir(nombre, [{"posicion": p, "duracion_ms": 1200} for p in poses], "Avanzar")
            filas = ac.analizar(nombre, trim, 150)
            sf.escribir(nombre, [{"posicion": f["posicion"], "duracion_ms": f["nuevo"]} for f in filas], "Avanzar")
        else:
            filas = ac.analizar(nombre, trim, 150)
        v, m, _ = ac.verificar_continuo(nombre, trim)
        print(f"{nombre:34s} {sum(f['nuevo'] for f in filas) / 1000:4.1f} s | margen quieto >= "
              f"{min(f['estatico'] for f in filas if f['estatico'] < 25):.1f} mm | continuo: apoyo >= {m:.1f} mm, "
              f"servo sobra {v:.0f} grados/s")


if __name__ == "__main__":
    main()
