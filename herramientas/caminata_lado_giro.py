"""SEGMENTO: PASO DE COSTADO Y GIRO (misma logica que caminata_usuario.py: un solo cambio por pose)
De costado (hacia la izquierda; la derecha es el espejo):
  peso al pie derecho -> doblar la pierna izquierda (sube el pie) -> abrir la cadera izquierda -> estirarla (apoya
  afuera) -> peso al centro -> peso al pie izquierdo -> doblar la derecha -> cerrar su cadera -> estirarla (pies
  juntos) -> centro
  La pierna de apoyo no se mueve mientras la otra esta en el aire.
  Pie plano: tobillo con el MISMO signo que la cadera de esa pierna (asi lo muestra la inclinacion del usuario,
  cadera +4 y tobillo +8 con los pies planos; en caminata_nx25.canales esta al reves y no vale).
Giro (hacia la izquierda; la derecha es el espejo): la caminata del usuario con pasos desiguales, la pierna de
  afuera da el paso entero (femur 40) y la de adentro uno corto. Las piernas no tienen servo de giro, asi que gira
  por la diferencia de largo de paso: unos grados por paso, segun el piso.
Signos (de las poses del usuario): cadera izq (0) + abre, der (15) + cierra; femur izq (1) + atras, der (14) +
  adelante; tibia izq (2) + lleva el pie atras, der (13) espejo.
Uso: python caminata_lado_giro.py [--ms 400] [--abre 12] [--dobla 25] [--corto 20] [--pasos 3]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import caminata_usuario as cu  # noqa: E402

PIERNAS = (0, 1, 2, 3, 12, 13, 14, 15)
INCLINAR = cu.INCLINAR                    # peso al pie derecho: cadera 4, tobillo 8 (probado por el usuario)


def arg(nombre, defecto):
    return float(sys.argv[sys.argv.index(nombre) + 1]) if nombre in sys.argv else defecto


def espejo(d):
    """cambios de la pierna izquierda <-> derecha (mismo movimiento del otro lado)"""
    m = {0: 15, 15: 0, 3: 12, 12: 3, 1: 14, 14: 1, 2: 13, 13: 2}
    return {m[c]: -v for c, v in d.items()}


def suma(*ds):
    out = {}
    for d in ds:
        for c, v in d.items():
            out[c] = out.get(c, 0) + v
    return out


# =====================================================================
# SEGMENTO: DE COSTADO
# =====================================================================
def costado_izq(abre, dobla):
    """cambios respecto de Inicionx25, un paso hacia la izquierda"""
    peso_der = dict(INCLINAR)
    peso_izq = espejo(INCLINAR)
    dobla_izq = {1: -dobla, 2: dobla}               # muslo adelante y canilla atras: la pierna se acorta
    abre_izq = {0: abre, 3: abre}                   # cadera abre y el tobillo acompana (pie plano)
    pies_abiertos = {0: abre / 2, 3: abre / 2, 15: -abre / 2, 12: -abre / 2}   # mismo ancho, peso al centro
    return [
        ("peso al pie derecho", peso_der),
        ("sube el pie izquierdo", suma(peso_der, dobla_izq)),
        ("abre la pierna izquierda", suma(peso_der, dobla_izq, abre_izq)),
        ("apoya el izquierdo afuera", suma(peso_der, abre_izq)),
        ("peso al centro", pies_abiertos),
        ("peso al pie izquierdo", suma(pies_abiertos, peso_izq, {0: -abre / 2, 3: -abre / 2, 15: -abre / 2, 12: -abre / 2})),
        ("sube el pie derecho", suma(peso_izq, espejo(abre_izq), espejo(dobla_izq))),
        ("cierra la pierna derecha", suma(peso_izq, espejo(dobla_izq))),
        ("apoya el derecho junto", peso_izq),
        ("centro", {}),
    ]


# =====================================================================
# SEGMENTO: GIRO
# =====================================================================
def giro_izq(corto):
    """la caminata del usuario (caminata_usuario.POSES) con la pierna izquierda dando pasos cortos"""
    out = []
    for nombre, peso, i, d in cu.POSES:
        cambios = {c: round(v * peso) for c, v in INCLINAR.items()}
        cambios[1] = -corto * i                     # izquierda: paso corto
        cambios[14] = cu.FEMUR * d                  # derecha: paso entero
        out.append((nombre, cambios))
    return out


# =====================================================================
# SEGMENTO: ESCRIBIR EN LA APP
# =====================================================================
def main():
    ms = int(arg("--ms", 400))
    abre, dobla, corto = arg("--abre", 12), arg("--dobla", 25), arg("--corto", 20)
    repetir = int(arg("--pasos", 3))
    pos, sec = os.path.join(cu.DATOS, "posiciones"), os.path.join(cu.DATOS, "secuencias")
    ref = {int(k): v for k, v in json.load(open(os.path.join(pos, cu.REF + ".json"), encoding="utf-8"))["angulos"].items()}

    def guardar_pose(nombre, cambios, carpeta):
        a = dict(ref)
        for c, v in cambios.items():
            a[c] = ref[c] + v
        json.dump({"nombre": nombre, "angulos": {str(c): int(round(v)) for c, v in sorted(a.items())}, "carpeta": carpeta},
                  open(os.path.join(pos, cu.archivo(nombre)), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"  {nombre:28s} " + " ".join(f"{c}:{round(a[c]):>4}" for c in PIERNAS))
        return nombre

    def guardar_secuencia(nombre, pasos, categoria):
        json.dump({"nombre": nombre, "categoria": categoria, "pasos": [{"posicion": p, "duracion_ms": ms} for p in pasos]},
                  open(os.path.join(sec, nombre + ".json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"secuencia '{nombre}': {len(pasos)} poses de {ms} ms")

    carpetas = ["paso de costado", "giro"]
    # de costado: cada pose numerada, "lado izq 01 peso al pie derecho" -> se ve en orden en la lista
    for lado, poses in (("izq", costado_izq(abre, dobla)), ("der", [(n.replace("izquierd", "XX").replace("derech", "izquierd")
                                                                       .replace("XX", "derech"), espejo(c))
                                                                      for n, c in costado_izq(abre, dobla)])):
        print(f"de costado hacia la {lado}:")
        nombres = [guardar_pose(f"lado {lado} {k + 1:02d} {n}", c, "paso de costado") for k, (n, c) in enumerate(poses)]
        guardar_secuencia(f"Costado {lado} completo", nombres * repetir, f"Costado {lado}")
    # giro: inicio, varias vueltas y final en una sola secuencia (como la caminata)
    for lado, poses in (("izq", giro_izq(corto)), ("der", [(n, espejo(c)) for n, c in giro_izq(corto)])):
        print(f"giro hacia la {lado}:")
        nombres = [guardar_pose(f"giro {lado} {n}", c, "giro") for n, c in poses]
        inicio, caminar = nombres[:4], nombres[4:]
        final = [f"giro {lado} 1.5", f"giro {lado} 1.6", f"giro {lado} 1.7", cu.REF]
        categoria = "Girar Izquierda" if lado == "izq" else "Girar Derecha"
        guardar_secuencia(f"Giro {lado} completo", inicio + caminar * repetir + final, categoria)
    ruta_c = os.path.join(cu.DATOS, "carpetas_poses.json")
    actuales = json.load(open(ruta_c, encoding="utf-8"))
    json.dump(sorted(set(actuales) | set(carpetas)), open(ruta_c, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
