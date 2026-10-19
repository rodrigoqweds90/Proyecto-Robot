"""SEGMENTO: SECUENCIAS DE LA APP (todas las que se usan, en un solo lugar)
Cada secuencia arranca erguido (Inicionx25), da 3 pasos y vuelve a erguido: asi se puede poner en bucle sin saltos.
  rapidas (usar con "Continuo" o "Movimiento sincronizado"): tiempos de cada paso calculados con
    acelerar_secuencias.py (velocidad del servo + equilibrio) y verificadas en modo continuo
  lentas (400 ms por pose): las que ya funcionaban; sirven sin sincronizado y con la bateria baja
Arma las poses (caminata_usuario.py, caminata_costado.py), escribe las secuencias y BORRA de la app las secuencias
y poses que ya no usa ninguna (respaldo antes de correr esto: copiar %APPDATA%\\RobotControl).
Uso: python secuencias_finales.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import acelerar_secuencias as ac  # noqa: E402
import caminata_costado as cc  # noqa: E402
import caminata_usuario as cu  # noqa: E402
import simular_caminata as sc  # noqa: E402

POS = os.path.join(cu.DATOS, "posiciones")
SEC = os.path.join(cu.DATOS, "secuencias")
LENTO_MS = 400


def secuencias():
    """{nombre: (poses, categoria, rapida)}"""
    return {
        "Adelante 3 pasos": (cu.FLUIDO_INICIO + cu.FLUIDO + cu.FLUIDO_FINAL, "Avanzar", True),
        "Atras 3 pasos": (cu.ATRAS_FLUIDO_INICIO + cu.ATRAS_FLUIDO + cu.ATRAS_FLUIDO_FINAL, "Retroceder", True),
        "Costado izq 3 pasos": (cc.ciclo("izq", True) * 3 + [cc.nombres_lado("izq")[-1]], "Otro", True),
        "Costado der 3 pasos": (cc.ciclo("der", True) * 3 + [cc.nombres_lado("der")[-1]], "Otro", True),
        "Adelante 3 pasos lento": (cu.INICIO + cu.CAMINAR + cu.FINAL, "Avanzar", False),
        "Atras 3 pasos lento": (cu.ATRAS_INICIO + cu.ATRAS + cu.ATRAS_FINAL, "Retroceder", False),
        "Costado izq 3 pasos lento": (cc.ciclo("izq", False) * 3 + [cc.nombres_lado("izq")[-1]], "Otro", False),
        "Costado der 3 pasos lento": (cc.ciclo("der", False) * 3 + [cc.nombres_lado("der")[-1]], "Otro", False),
    }


def escribir(nombre, pasos, categoria):
    json.dump({"nombre": nombre, "categoria": categoria, "pasos": pasos},
              open(os.path.join(SEC, nombre + ".json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def main():
    cu.guardar_poses()
    cc.guardar_poses()
    ref = ac.angulos(cu.REF)
    trim = {c: ref[c] for c in sc.cn.PIERNAS}
    finales = secuencias()
    usadas = {cu.REF}
    print(f"{'secuencia':28s} {'poses':>5s} {'dura':>6s}   verificacion")
    for nombre, (poses, categoria, rapida) in finales.items():
        usadas.update(poses)
        if not rapida:
            escribir(nombre, [{"posicion": p, "duracion_ms": LENTO_MS} for p in poses], categoria)
            print(f"{nombre:28s} {len(poses):5d} {len(poses) * LENTO_MS / 1000:5.1f}s   (tiempos ya probados)")
            continue
        # tiempos: se calculan desde una base larga (sin el tope de "lo ya probado": la mezcla de poses es nueva)
        escribir(nombre, [{"posicion": p, "duracion_ms": 1200} for p in poses], categoria)
        filas = ac.analizar(nombre, trim, 150)
        escribir(nombre, [{"posicion": f["posicion"], "duracion_ms": f["nuevo"]} for f in filas], categoria)
        v, m, _ = ac.verificar_continuo(nombre, trim)
        quieto = min(f["con_nuevo"] for f in filas)
        print(f"{nombre:28s} {len(poses):5d} {sum(f['nuevo'] for f in filas) / 1000:5.1f}s   "
              f"sincronizado: apoyo >= {quieto:.1f} mm | continuo: apoyo >= {m:.1f} mm, servo sobra {v:.0f} grados/s")
    # limpieza: lo que no usa ninguna secuencia final
    for f in os.listdir(SEC):
        if f.endswith(".json") and f[:-5] not in finales:
            os.remove(os.path.join(SEC, f))
            print("  secuencia borrada:", f[:-5])
    borradas = 0
    archivos_usados = {cu.archivo(p) for p in usadas}
    for f in os.listdir(POS):
        if f.endswith(".json") and f not in archivos_usados:
            os.remove(os.path.join(POS, f))
            borradas += 1
    print(f"  poses borradas: {borradas}")
    carpetas = sorted({json.load(open(os.path.join(POS, f), encoding="utf-8")).get("carpeta", "") for f in os.listdir(POS)} - {""})
    json.dump(carpetas, open(os.path.join(cu.DATOS, "carpetas_poses.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("  carpetas:", ", ".join(carpetas))


if __name__ == "__main__":
    main()
