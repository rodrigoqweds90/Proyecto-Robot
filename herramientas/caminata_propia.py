"""SEGMENTO: CAMINATA PROPIA (curvas continuas, con lo aprendido de la del NX25)
Diferencias con la tabla del NX25 (caminata_nx25.py):
  - balanceo lateral con una curva que se SOSTIENE sobre el pie de apoyo mientras el otro esta en el aire
    (tanh de un seno), en vez de tramos rectos
  - pie que avanza: sube y baja con un arco suave (seno) y avanza con una curva coseno; el pie de apoyo empuja hacia
    atras parejo todo el tiempo que esta apoyado (70 % del ciclo: tambien en el doble apoyo)
  - el truco del usuario, simetrico: el pie de apoyo se inclina unos grados extra mientras el peso esta sobre el
    (en la del NX25 lo puso a mano en 4 cuadros y con eso el peso paso al pie de apoyo)
  - el ciclo se arma con el lado izquierdo y el derecho es el mismo medio ciclo despues: simetria exacta
  - secuencias de entrada (de erguido a la postura de caminar) y de salida
Signos, ajustes finos (pose de referencia) y cinematica inversa: los de caminata_nx25.py (probados en el robot).
Uso: python caminata_propia.py [--ref Inicionx25] [--cuadros 24] [--ms 200] [--paso 36] [--sube 18] [--balanceo 20]
     [--apoyo 9] [--sin_escribir]
"""
import json
import math
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import caminata_nx25 as cn  # noqa: E402
import poses_marcha as pm  # noqa: E402

CARPETA = "Caminata propia"
PREFIJO = "Propia"
ALTO = 105.0             # altura de la cadera (pierna estirada 110.4)
AIRE = (0.10, 0.40)      # fraccion del ciclo con el pie IZQUIERDO en el aire (el derecho, medio ciclo despues)
FORMA_BALANCEO = 2.2     # cuanto se "sostiene" el balanceo arriba (0 = seno puro)
LIMITES = {"muslo": (-20.0, 60.0), "canilla": (-60.0, 20.0)}   # sin choques en el CAD


def arg(nombre, defecto):
    return float(sys.argv[sys.argv.index(nombre) + 1]) if nombre in sys.argv else defecto


def pie(t, fase, paso, sube):
    """(X, Y) de un pie respecto de su cadera en el instante t (0..1) del ciclo; fase = 0 izquierdo, 0.5 derecho.
    X adelante, Y hacia abajo (como la cinematica del NX25)."""
    a0, a1 = AIRE
    u = (t - fase) % 1.0
    if a0 <= u <= a1:                                    # en el aire: de atras hacia adelante, en arco
        s = (u - a0) / (a1 - a0)
        x = -paso / 2 + paso * (1 - math.cos(math.pi * s)) / 2
        return x, ALTO - sube * math.sin(math.pi * s), True
    apoyo = 1.0 - (a1 - a0)                              # apoyado: de adelante hacia atras, parejo
    s = ((u - a1) % 1.0) / apoyo
    return paso / 2 - paso * s, ALTO, False


def balanceo(t, amplitud):
    """desplazamiento lateral de los pies respecto de las caderas (+: peso al pie derecho, el izquierdo en el aire)"""
    centro = (AIRE[0] + AIRE[1]) / 2
    v = math.sin(2 * math.pi * (t - centro + 0.25))
    return amplitud * math.tanh(FORMA_BALANCEO * v) / math.tanh(FORMA_BALANCEO)


def cuadro(t, trim, ref, paso, sube, amplitud, apoyo):
    z = balanceo(t, amplitud)
    xi, yi, aire_i = pie(t, 0.0, paso, sube)
    xd, yd, aire_d = pie(t, 0.5, paso, sube)
    a = dict(ref)
    a.update(cn.canales((xd, yd, z), (xi, yi, z), trim))
    # pie de apoyo mas inclinado mientras el peso esta sobre el (simetrico): z > 0 apoya el derecho
    extra = apoyo * (z / amplitud) ** 2 if amplitud else 0.0
    if z > 0:
        a[12] -= extra
    else:
        a[3] += extra
    return a, (xi, yi, xd, yd, z, aire_i, aire_d)


def main():
    ref_nombre = sys.argv[sys.argv.index("--ref") + 1] if "--ref" in sys.argv else "Inicionx25"
    n = int(arg("--cuadros", 24))
    ms = int(arg("--ms", 200))
    paso, sube = arg("--paso", 36.0), arg("--sube", 18.0)
    amplitud, apoyo = arg("--balanceo", 20.0), arg("--apoyo", 9.0)
    ref = {int(k): v for k, v in json.load(open(os.path.join(cn.DATOS, "posiciones", ref_nombre + ".json"),
                                                 encoding="utf-8"))["angulos"].items()}
    trim = {c: ref.get(c, 0) for c in cn.PIERNAS}
    ciclo, info = [], []
    for k in range(n):
        a, d = cuadro(k / n, trim, ref, paso, sube, amplitud, apoyo)
        ciclo.append(a)
        info.append(d)
    # rango de muslo y canilla (sin trims): que no se salga de lo verificado sin choques
    mus, rod = [], []
    for xi, yi, xd, yd, z, _, _ in info:
        for x, y in ((xi, yi), (xd, yd)):
            _, m_, r_ = pm.ik(cn.ADELANTE * x, y, z)
            mus.append(m_); rod.append(r_)
    print(f"caminata propia: {n} cuadros de {ms} ms ({n * ms / 2000:.1f} s por paso); pie +-{paso / 2:.0f} mm, sube {sube:.0f} mm, "
          f"balanceo {amplitud:.0f} mm, tobillo de apoyo +{apoyo:.0f} grados; referencia '{ref_nombre}'")
    print(f"muslo {min(mus):.1f}..{max(mus):.1f} (limite {LIMITES['muslo']}), canilla {min(rod):.1f}..{max(rod):.1f} "
          f"(limite {LIMITES['canilla']})")
    fuera = min(mus) < LIMITES["muslo"][0] or max(mus) > LIMITES["muslo"][1] or min(rod) < LIMITES["canilla"][0] or max(rod) > LIMITES["canilla"][1]
    if fuera:
        print("FUERA DEL RANGO SIN CHOQUES: no se escribe nada")
        return
    # entrada y salida: de la referencia (erguido) a la postura del primer cuadro en 4 pasos
    entrada = []
    for j in range(1, 5):
        f = j / 4
        entrada.append({c: ref.get(c, 0) + (ciclo[0][c] - ref.get(c, 0)) * f for c in ciclo[0]})
    salida = list(reversed(entrada[:-1])) + [dict(ref)]
    salto = max(max(abs(ciclo[(k + 1) % n][c] - ciclo[k][c]) for c in cn.PIERNAS) for k in range(n))
    vel = salto * (1950 / 180) / (ms / 15) * 1.3
    print(f"mayor salto entre cuadros: {salto:.1f} grados -> velocidad de la app recomendada: {math.ceil(vel)} o mas")
    print("cuadro  " + " ".join(f"{c:>4}" for c in cn.PIERNAS) + "   pies en el aire")
    for k, (a, d) in enumerate(zip(ciclo, info)):
        aire = ("izq" if d[5] else "") + ("der" if d[6] else "")
        print(f"{k + 1:>6}  " + " ".join(f"{round(a[c]):>4}" for c in cn.PIERNAS) + f"   {aire}")
    if "--sin_escribir" in sys.argv:
        return
    escribir(ciclo, entrada, salida, ms)


def escribir(ciclo, entrada, salida, ms, secuencias=("Empezar a caminar", "Caminar propia", "Terminar de caminar"),
             ultimo=0):
    """ultimo: cuadro del ciclo donde queda el robot al terminar (desde ahi arranca la salida)"""
    pos = os.path.join(cn.DATOS, "posiciones")
    sec = os.path.join(cn.DATOS, "secuencias")
    os.makedirs(pos, exist_ok=True)
    os.makedirs(sec, exist_ok=True)

    def guardar_pose(nombre, a):
        with open(os.path.join(pos, nombre + ".json"), "w", encoding="utf-8") as f:
            json.dump({"nombre": nombre, "angulos": {str(c): int(round(v)) for c, v in sorted(a.items())}, "carpeta": CARPETA},
                      f, indent=2, ensure_ascii=False)

    def guardar_secuencia(nombre, pasos):
        with open(os.path.join(sec, nombre + ".json"), "w", encoding="utf-8") as f:
            json.dump({"nombre": nombre, "categoria": "Caminar", "pasos": pasos}, f, indent=2, ensure_ascii=False)

    nombres = []
    for k, a in enumerate(ciclo):
        nombres.append(f"{PREFIJO} {k + 1:02d}")
        guardar_pose(nombres[-1], a)
    ent = []
    for j, a in enumerate(entrada):
        ent.append(f"{PREFIJO} entrada {j + 1}")
        guardar_pose(ent[-1], a)
    sal = []
    for j, a in enumerate(salida):
        sal.append(f"{PREFIJO} salida {j + 1}")
        guardar_pose(sal[-1], a)
    empezar, caminar, terminar = secuencias
    guardar_secuencia(caminar, [{"posicion": p, "duracion_ms": ms} for p in nombres])
    guardar_secuencia(empezar, [{"posicion": p, "duracion_ms": 300} for p in ent])
    guardar_secuencia(terminar, [{"posicion": p, "duracion_ms": 300} for p in [nombres[ultimo]] + sal])
    ruta_c = os.path.join(cn.DATOS, "carpetas_poses.json")
    carpetas = json.load(open(ruta_c, encoding="utf-8")) if os.path.exists(ruta_c) else []
    if CARPETA not in carpetas:
        with open(ruta_c, "w", encoding="utf-8") as f:
            json.dump(sorted(carpetas + [CARPETA]), f, indent=2, ensure_ascii=False)
    print(f"\n{len(nombres) + len(ent) + len(sal)} poses en '{CARPETA}'; secuencias '{empezar}', '{caminar}' y "
          f"'{terminar}' en {cn.DATOS}")


if __name__ == "__main__":
    main()
