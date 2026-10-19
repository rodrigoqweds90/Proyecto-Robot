"""SEGMENTO: CAMINATA POR FASES (idea del usuario, 2026-10-18)
Pasos separados y claros, como camina una persona despacio:
  1. pasar el peso al pie de apoyo moviendo la pelvis de costado (el cuerpo queda derecho)
  2. levantar la otra pierna
  3. llevarla adelante en el aire
  4. apoyarla adelante
  5. pasar el peso a esa pierna: RECIEN ACA avanza el cuerpo (los dos pies se corren medio paso atras)
  6. lo mismo con la otra pierna
Mientras un pie esta en el aire la pierna de apoyo queda quieta.
v2 (revisada con simular_caminata.py): la v1 pasaba el peso inclinando el tobillo de apoyo 9 grados todo el tiempo,
y eso ladeaba el robot entero 9 grados de un lado al otro (se veia "tirarse para un lado") y el pie bajaba sin llegar
al piso hasta que el robot se volvia a ladear; ademas el paso era de 18 mm (un cuarto del pie) y casi no se veia.
Ahora: balanceo de pelvis mas grande (cuerpo derecho), unos pocos grados de tobillo SOLO con el pie en el aire (se
sacan antes de apoyar, asi el pie llega plano), y paso de 44 mm (22 mm de avance por paso).
Signos, ajustes finos y cinematica: los de caminata_nx25.py (probados en el robot).
Uso: python caminata_fases.py [--ref Inicionx25] [--ms 200] [--paso 44] [--sube 14] [--balanceo 32] [--apoyo 4]
     [--ciclos 4] [--sin_escribir]
"""
import json
import math
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import caminata_nx25 as cn  # noqa: E402
import poses_marcha as pm  # noqa: E402

CARPETA = "Caminata por fases"
PREFIJO = "Fases"
ALTO = 100.0             # altura de la cadera: con 105 el pie no llega a +-25 mm (eslabones de 28.7)
CUADROS = {"peso": 4, "sube": 2, "adelante": 4, "baja": 2}   # cuadros de cada fase (por paso)
SUBE_ANTES = 0.6         # en "sube" el pie llega a esta fraccion de la altura; el maximo es a mitad de "adelante"
TOBILLO = {"sube": (0.5, 1.0), "adelante": (1.0, 1.0), "baja": (0.5, 0.0)}   # fraccion del tobillo extra por fase
LIMITES = {"muslo": (-20.0, 60.0), "canilla": (-60.0, 20.0)}


def arg(nombre, defecto):
    return float(sys.argv[sys.argv.index(nombre) + 1]) if nombre in sys.argv else defecto


def suave(s):
    return s * s * (3 - 2 * s)


def estados(paso, sube, amplitud):
    """cuadros de un ciclo (dos pasos) como (z, xi, yi, xd, yd, tobillo, fase). z > 0: peso en el pie derecho;
    tobillo: fraccion (0..1) del extra en el tobillo de apoyo"""
    h, p2, A = ALTO, paso / 2, amplitud
    out = []

    def tramo(n, de, a, fase, t=(0.0, 0.0)):
        for j in range(1, n + 1):
            f = suave(j / n)
            out.append(tuple(x + (y - x) * f for x, y in zip(de, a)) + (t[0] + (t[1] - t[0]) * j / n, fase))

    def paso_pierna(lado):
        # lado = +1: pierna izquierda en el aire (peso a la derecha, z = +A)
        # 1. pasar el peso al pie de apoyo y avanzar el cuerpo: los dos pies medio paso atras
        if lado > 0:
            ini = (-A, 0.0, h, p2, h)            # venia de apoyar el derecho adelante
            fin = (A, -p2, h, 0.0, h)
        else:
            ini = (A, p2, h, 0.0, h)
            fin = (-A, 0.0, h, -p2, h)
        tramo(CUADROS["peso"], ini, fin, "peso")
        z, xi, yi, xd, yd = fin

        # 2-4. el pie libre sube, va adelante en arco y baja; el de apoyo no se mueve
        def libre(x, y):
            return (z, x, y, xd, yd) if lado > 0 else (z, xi, yi, x, y)
        x0 = xi if lado > 0 else xd
        tramo(CUADROS["sube"], libre(x0, h), libre(x0, h - sube * SUBE_ANTES), "sube", TOBILLO["sube"])
        n = CUADROS["adelante"]
        for j in range(1, n + 1):
            s = j / n
            x = -p2 + paso * s                    # parejo: con suave() el muslo saltaba 30 grados en un cuadro
            y = h - sube * max(SUBE_ANTES * (1 - s), math.sin(math.pi * s), SUBE_ANTES * s)   # arco, arriba a mitad
            out.append(libre(x, y) + (1.0, "adelante"))
        tramo(CUADROS["baja"], libre(p2, h - sube * SUBE_ANTES), libre(p2, h), "baja", TOBILLO["baja"])

    paso_pierna(+1)
    paso_pierna(-1)
    return out


def generar(ref, paso, sube, amplitud, apoyo):
    """poses del ciclo (grados de la app) y rangos de muslo y canilla"""
    trim = {c: ref.get(c, 0) for c in cn.PIERNAS}
    ciclo, mus, rod = [], [], []
    for z, xi, yi, xd, yd, t, _ in estados(paso, sube, amplitud):
        a = dict(ref)
        a.update(cn.canales((xd, yd, z), (xi, yi, z), trim))
        if z > 0:                              # tobillo de apoyo un poco mas inclinado con el otro pie en el aire
            a[12] -= apoyo * t
        else:
            a[3] += apoyo * t
        ciclo.append(a)
        for x, y in ((xi, yi), (xd, yd)):
            _, m_, r_ = pm.ik(cn.ADELANTE * x, y, z)
            mus.append(m_); rod.append(r_)
    return ciclo, mus, rod


def main():
    ref_nombre = sys.argv[sys.argv.index("--ref") + 1] if "--ref" in sys.argv else "Inicionx25"
    ms = int(arg("--ms", 200))
    paso, sube = arg("--paso", 44.0), arg("--sube", 14.0)
    amplitud, apoyo = arg("--balanceo", 32.0), arg("--apoyo", 4.0)
    ciclos = int(arg("--ciclos", 4))
    ref = {int(k): v for k, v in json.load(open(os.path.join(cn.DATOS, "posiciones", ref_nombre + ".json"),
                                                 encoding="utf-8"))["angulos"].items()}
    ciclo, mus, rod = generar(ref, paso, sube, amplitud, apoyo)
    n = len(ciclo)
    print(f"caminata por fases: {n} cuadros de {ms} ms ({n * ms / 2000:.1f} s por paso, avanza {paso / 2:.0f} mm por paso); "
          f"pie sube {sube:.0f} mm, balanceo {amplitud:.0f} mm, tobillo de apoyo +{apoyo:.0f} grados en el aire")
    print(f"muslo {min(mus):.1f}..{max(mus):.1f} (limite {LIMITES['muslo']}), canilla {min(rod):.1f}..{max(rod):.1f} "
          f"(limite {LIMITES['canilla']})")
    if min(mus) < LIMITES["muslo"][0] or max(mus) > LIMITES["muslo"][1] or min(rod) < LIMITES["canilla"][0] or max(rod) > LIMITES["canilla"][1]:
        print("FUERA DEL RANGO SIN CHOQUES: no se escribe nada")
        return
    fases = [e[-1] for e in estados(paso, sube, amplitud)]
    print("cuadro  " + " ".join(f"{c:>4}" for c in cn.PIERNAS) + "   fase")
    for k, a in enumerate(ciclo):
        lado = "izq" if k < n // 2 else "der"
        print(f"{k + 1:>6}  " + " ".join(f"{round(a[c]):>4}" for c in cn.PIERNAS) + f"   {fases[k]} ({lado})")
    if "--sin_escribir" in sys.argv:
        return
    import caminata_propia as cp
    cp.CARPETA, cp.PREFIJO = CARPETA, PREFIJO
    # entrada: de erguido al ultimo cuadro del ciclo (peso a la izquierda, derecho adelante), asi arranca pasando el peso
    entrada = [{c: ref.get(c, 0) + (ciclo[-1][c] - ref.get(c, 0)) * j / 4 for c in ciclo[-1]} for j in range(1, 5)]
    salida = list(reversed(entrada[:-1])) + [dict(ref)]
    cp.escribir(ciclo, entrada, salida, ms, ("Empezar por fases", "Caminar por fases", "Terminar por fases"), ultimo=-1)
    # una sola secuencia lista para darle play: entrada, varios ciclos y salida
    pasos = [{"posicion": f"{PREFIJO} entrada {j}", "duracion_ms": 300} for j in range(1, 5)]
    pasos += [{"posicion": f"{PREFIJO} {k:02d}", "duracion_ms": ms} for _ in range(ciclos) for k in range(1, n + 1)]
    pasos += [{"posicion": f"{PREFIJO} salida {j}", "duracion_ms": 300} for j in range(1, 5)]
    nombre = "Caminata por fases completa"
    with open(os.path.join(cn.DATOS, "secuencias", nombre + ".json"), "w", encoding="utf-8") as f:
        json.dump({"nombre": nombre, "categoria": "Caminar", "pasos": pasos}, f, indent=2, ensure_ascii=False)
    print(f"secuencia '{nombre}': entrada + {ciclos} ciclos ({ciclos * 2} pasos) + salida, {len(pasos)} pasos")


if __name__ == "__main__":
    main()
