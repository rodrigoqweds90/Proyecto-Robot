"""SEGMENTO: PASO DE COSTADO "CANGREJO" (misma logica que caminata_usuario.py: un solo cambio por pose)
Hacia la izquierda (la derecha es el espejo):
  peso al pie derecho -> doblar la pierna izquierda (sube el pie) -> abrir la cadera izquierda -> estirarla (apoya
  afuera) -> peso al centro -> peso al pie izquierdo -> doblar la derecha -> cerrar su cadera -> estirarla (pies
  juntos) -> centro
  La pierna de apoyo no se mueve mientras la otra esta en el aire.
  Pie plano: tobillo con el MISMO signo que la cadera de esa pierna (asi lo muestra la inclinacion del usuario,
  cadera +4 y tobillo +8 con los pies planos; en caminata_nx25.canales esta al reves y no vale).
Modo fluido: sin "peso al centro" (de "apoya afuera" a "peso al otro pie" directo) y sin "centro" entre pasos.
El giro (pasos desiguales) se saco: no giraba. Queda pendiente rehacerlo.
Signos (de las poses del usuario): cadera izq (0) + abre, der (15) + cierra; femur izq (1) + atras, der (14) +
  adelante; tibia izq (2) + lleva el pie atras, der (13) espejo.
Uso: python caminata_costado.py [--abre 12] [--dobla 25]   (solo poses; las secuencias: secuencias_finales.py)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import caminata_usuario as cu  # noqa: E402

CARPETA = "paso de costado"
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


def nombres_lado(lado):
    """nombres de las 10 poses de un paso hacia ese lado, en orden"""
    n = [p for p, _ in costado_izq(12, 25)]
    if lado == "der":
        n = [p.replace("izquierd", "XX").replace("derech", "izquierd").replace("XX", "derech") for p in n]
    return [f"lado {lado} {k + 1:02d} {p}" for k, p in enumerate(n)]


def ciclo(lado, fluido):
    """un paso de costado (empieza y termina con los pies juntos; sin la ultima 'centro', que va al final)"""
    n = nombres_lado(lado)
    return [p for p in n[:-1] if not (fluido and " 05 " in p)]


def guardar_poses(abre=12, dobla=25):
    pos = os.path.join(cu.DATOS, "posiciones")
    ref = {int(k): v for k, v in json.load(open(os.path.join(pos, cu.REF + ".json"), encoding="utf-8"))["angulos"].items()}
    for lado, cambios in (("izq", [c for _, c in costado_izq(abre, dobla)]),
                          ("der", [espejo(c) for _, c in costado_izq(abre, dobla)])):
        for nombre, c in zip(nombres_lado(lado), cambios):
            a = dict(ref)
            for canal, v in c.items():
                a[canal] = ref[canal] + v
            json.dump({"nombre": nombre, "angulos": {str(k): int(round(v)) for k, v in sorted(a.items())},
                       "carpeta": CARPETA},
                      open(os.path.join(pos, cu.archivo(nombre)), "w", encoding="utf-8"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    guardar_poses(arg("--abre", 12), arg("--dobla", 25))
    print("poses de costado guardadas; las secuencias las arma secuencias_finales.py")
