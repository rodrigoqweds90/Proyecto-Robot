"""SEGMENTO: SECUENCIAS DE LA APP (todas las que se usan, en un solo lugar)
Cada secuencia es UN ciclo de paso (izquierdo + derecho) para poner en "Repetir en bucle": la ultima pose lleva a la
primera y la primera se alcanza directo desde Inicio. Al detener, el robot queda a mitad de paso: apretar Inicio.
  rapidas (usar con "Continuo" o "Movimiento sincronizado"): tiempos de cada paso calculados con
    acelerar_secuencias.py (velocidad del servo + equilibrio) y verificadas en modo continuo
  lentas (400 ms por pose): las que ya funcionaban; sirven sin sincronizado y con la bateria baja
Arma las poses (caminata_usuario.py, caminata_costado.py), escribe las secuencias y BORRA de la app las secuencias
y poses que ya no usa ninguna, salvo las "Prueba ..." (respaldo antes de correr esto: copiar %APPDATA%\\RobotControl).
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


def rotar(poses, primera):
    """el mismo ciclo, empezando en 'primera'"""
    i = poses.index(primera)
    return poses[i:] + poses[:i]


def secuencias():
    """{nombre: (poses, categoria, rapida)}. Cada una es UN ciclo (paso izquierdo + paso derecho) para poner en bucle:
    la ultima pose lleva a la primera, y la primera se alcanza directo desde Inicio (solo ladear el cuerpo, o ladear
    y doblar la rodilla de la pierna libre), asi el bucle puede arrancar con el robot parado."""
    return {
        "Adelante paso": (rotar(cu.FLUIDO, "1.6+7 doblada"), "Avanzar", True),
        "Atras paso": (rotar(cu.ATRAS_FLUIDO, "1.6+7 doblada"), "Retroceder", True),
        "Costado izq paso": (cc.ciclo("izq", True), "Otro", True),
        "Costado der paso": (cc.ciclo("der", True), "Otro", True),
        "Adelante paso lento": (rotar(cu.CAMINAR, "1.7"), "Avanzar", False),
        "Atras paso lento": (rotar(cu.ATRAS, "1.13"), "Retroceder", False),
        "Costado izq paso lento": (cc.ciclo("izq", False), "Otro", False),
        "Costado der paso lento": (cc.ciclo("der", False), "Otro", False),
    }


def escribir(nombre, pasos, categoria):
    json.dump({"nombre": nombre, "categoria": categoria, "pasos": pasos},
              open(os.path.join(SEC, nombre + ".json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def escribir_bucle(nombre, poses, categoria, trim):
    """Escribe un ciclo rapido con sus tiempos y lo verifica. Devuelve (pasos, margen sincronizado, sobra del servo,
    margen continuo). Los tiempos se calculan desde una base larga (sin el tope de "lo ya probado") analizando
    Inicio -> ciclo -> primera pose otra vez: la primera pose sirve para entrar desde Inicio y para la vuelta del
    bucle, y se queda con el mayor de los dos tiempos."""
    escribir(nombre, [{"posicion": p, "duracion_ms": 1200} for p in poses + poses[:1]], categoria)
    filas = ac.analizar(nombre, trim, 150)
    tiempos = [max(filas[0]["nuevo"], filas[-1]["nuevo"])] + [f["nuevo"] for f in filas[1:-1]]
    pasos = [{"posicion": p, "duracion_ms": t} for p, t in zip(poses, tiempos)]
    escribir("_verificar", pasos * 3, categoria)            # modo Continuo, 3 vueltas seguidas del bucle
    v, m, _ = ac.verificar_continuo("_verificar", trim)
    os.remove(os.path.join(SEC, "_verificar.json"))
    escribir(nombre, pasos, categoria)
    return pasos, min(f["con_nuevo"] for f in filas), v, m


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
        pasos, quieto, v, m = escribir_bucle(nombre, poses, categoria, trim)
        print(f"{nombre:28s} {len(poses):5d} {sum(p['duracion_ms'] for p in pasos) / 1000:5.1f}s   "
              f"sincronizado: apoyo >= {quieto:.1f} mm | continuo (3 vueltas): apoyo >= {m:.1f} mm, "
              f"servo sobra {v:.0f} grados/s")
    # limpieza: lo que no usa ninguna secuencia final (las "Prueba ..." y sus poses se quedan)
    for f in os.listdir(SEC):
        if f.startswith("Prueba") and f.endswith(".json"):
            usadas.update(p["posicion"] for p in json.load(open(os.path.join(SEC, f), encoding="utf-8"))["pasos"])
        elif f.endswith(".json") and f[:-5] not in finales:
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
