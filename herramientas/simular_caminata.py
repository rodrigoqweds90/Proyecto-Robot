"""SEGMENTO: SIMULADOR DE CAMINATA (estatico, cuadro por cuadro)
Toma una secuencia de la app (o una lista de poses), pasa cada pose a la posicion real de los pies con la geometria
del CAD (ensamble Robot_en_soporte) y apoya el robot en el piso como un cuerpo rigido: se inclina hasta que el
centro de masa queda sobre lo que toca el piso. Por cuadro dice:
  - que pie(s) tocan el piso y cuantos mm se despega el otro
  - inclinacion del cuerpo (lateral y adelante-atras)
  - margen del centro de masa: mm que le sobran hasta el borde del pie de apoyo (negativo = se cae hacia ese lado)
  - margen con juego: el mismo, restando lo que se pierde por el juego de los servos de cadera y tobillo
Y dibuja cada cuadro de frente y de costado (PNG por cuadro, hoja de contactos y GIF).
Modelo: cadera y tobillo laterales; femur y tibia mueven eslabones en paralelogramo (el pie queda paralelo a la
pelvis adelante-atras), como la cinematica del NX25. Masas estimadas (no hay balanza del robot armado).
Uso: python simular_caminata.py "Caminar por fases" [--ref Inicionx25] [--juego 2] [--sin_dibujo] [--salida DIR]
     python simular_caminata.py --poses "segundo,tercero,cuarto"
"""
import json
import math
import os
import sys

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import caminata_nx25 as cn  # noqa: E402

# =====================================================================
# SEGMENTO: GEOMETRIA (mm, marco de la pelvis: x lateral + izquierda, y arriba, z adelante; origen = ejes de cadera)
# =====================================================================
CADERA_X = 25.9                     # eje lateral de cada cadera (CAD)
H_CADERA, L1, H_RODILLA, L2, H_TOBILLO = 13.54, 28.7, 25.92, 28.7, 13.54
PLANTA_BAJO_TOBILLO = 22.0          # suela debajo del eje del tobillo
PLANTA_X = (-18.5, 30.3)            # suela respecto del eje del tobillo, hacia afuera + (pie izquierdo)
PLANTA_Z = (-28.0, 45.2)            # suela adelante-atras respecto del eje
# masas en gramos: (g, punto) -- el cuerpo de arriba (torso, brazos, cabeza, bateria, electronica) en un punto
# adelante fisico = + en la cinematica del NX25: lo muestran las poses del usuario ("paso usuario", 2026-10-18):
# femur derecho +40 lleva la pierna derecha adelante y femur izquierdo +40 la izquierda atras (ADELANTE = -1 de
# caminata_nx25 vino de la prueba "camina para atras", hecha cuando el peso todavia no pasaba bien al pie de apoyo)
ADELANTE_FISICO = 1.0
MASA_ARRIBA = (340.0, np.array([0.0, 60.0, 2.0]))
MASA_PIERNA = {"cadera": 25.0, "muslo": 20.0, "rodilla": 15.0, "canilla": 20.0, "pie": 27.0}


def leer(nombre, carpeta):
    archivo = "".join(c if c.isalnum() or c in " _-" else "_" for c in nombre).strip()   # como app/storage.py
    with open(os.path.join(cn.DATOS, carpeta, archivo + ".json"), encoding="utf-8") as f:
        return json.load(f)


def rot_z(a):           # giro lateral (alrededor del eje adelante), + lleva el "abajo" hacia +x
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def rot_x(a):           # giro adelante-atras
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0, 0], [0, c, -s], [0, s, c]])


# =====================================================================
# SEGMENTO: POSE -> ARTICULACIONES -> PUNTOS
# =====================================================================
def articulaciones(ang, trim):
    """grados de la app -> por pierna (cadera lateral, muslo, canilla, tobillo)
    Tobillo: el pie queda plano cuando el tobillo cambia lo MISMO que la cadera (mismo signo). Lo muestra el robot:
    la inclinacion del usuario (cadera +4, tobillo +8) deja los pies planos y su pose 1.1 carga el pie izquierdo.
    En caminata_nx25.canales esta al reves (tobillo = -cadera): con ese signo el simulador cargaba el pie contrario."""
    a = {c: ang.get(c, 0) - 0.0 for c in cn.PIERNAS}
    izq = (a[0] - trim[0], trim[1] - a[1], trim[2] - a[2], a[3] - trim[3])
    der = (a[15] - trim[15], a[14] - trim[14], a[13] - trim[13], a[12] - trim[12])
    return {"izq": izq, "der": der}


def pierna(lado, lat, mus, can, tob):
    """puntos de una pierna en el marco de la pelvis: cadena, masas y las 4 esquinas de la suela"""
    sx = 1.0 if lado == "izq" else -1.0
    m, r, fi = math.radians(mus), math.radians(can), math.radians(lat)
    # en el plano de la pierna: (adelante, abajo); adelante fisico = ADELANTE * X de la cinematica del NX25
    f = ADELANTE_FISICO
    p = [(0.0, 0.0), (0.0, H_CADERA)]
    p.append((p[-1][0] + f * L1 * math.sin(m), p[-1][1] + L1 * math.cos(m)))
    p.append((p[-1][0], p[-1][1] + H_RODILLA))
    p.append((p[-1][0] + f * L2 * math.sin(r), p[-1][1] + L2 * math.cos(r)))
    p.append((p[-1][0], p[-1][1] + H_TOBILLO))
    R = rot_z(fi)
    cadera = np.array([sx * CADERA_X, 0.0, 0.0])
    cadena = [cadera + R @ np.array([0.0, -d, z]) for z, d in p]
    tobillo = cadena[-1]
    Rp = R @ rot_z(-math.radians(tob))          # el tobillo gira el pie respecto de la pierna
    esquinas = [tobillo + Rp @ np.array([sx * x, -PLANTA_BAJO_TOBILLO, z]) for x in PLANTA_X for z in PLANTA_Z]
    masas = [(MASA_PIERNA["cadera"], (cadena[0] + cadena[1]) / 2), (MASA_PIERNA["muslo"], (cadena[1] + cadena[2]) / 2),
             (MASA_PIERNA["rodilla"], (cadena[2] + cadena[3]) / 2), (MASA_PIERNA["canilla"], (cadena[3] + cadena[4]) / 2),
             (MASA_PIERNA["pie"], tobillo + Rp @ np.array([sx * 6.0, -10.0, 8.0]))]
    return cadena, np.array(esquinas), masas


def cuerpo(ang, trim):
    art = articulaciones(ang, trim)
    out = {}
    masas = [MASA_ARRIBA]
    for lado in ("izq", "der"):
        cadena, esq, ms = pierna(lado, *art[lado])
        out[lado] = (cadena, esq)
        masas += ms
    g = sum(m for m, _ in masas)
    com = sum(m * p for m, p in masas) / g
    return out, com, art


# =====================================================================
# SEGMENTO: APOYO EN EL PISO (cuerpo rigido, cuasi estatico)
# =====================================================================
def altura_com(rl, rf, piernas, com):
    R = rot_x(rf) @ rot_z(rl)
    pts = np.vstack([R @ e for _, esq in piernas.values() for e in esq])
    return (R @ com)[1] - pts[:, 1].min()


def apoyar(piernas, com, previo=(0.0, 0.0)):
    """busca la inclinacion (lateral, adelante) donde el centro de masa queda lo mas bajo posible partiendo de la
    anterior: asi un robot que no tiene el peso sobre un pie se ladea hasta que el otro toca el piso"""
    rl, rf = previo
    paso = math.radians(2.0)
    h = altura_com(rl, rf, piernas, com)
    while paso > math.radians(0.01):
        mejor = None
        for dl, df in ((paso, 0), (-paso, 0), (0, paso), (0, -paso)):
            hh = altura_com(rl + dl, rf + df, piernas, com)
            if hh < h - 1e-6 and (mejor is None or hh < mejor[0]):
                mejor = (hh, dl, df)
        if mejor:
            h, rl, rf = mejor[0], rl + mejor[1], rf + mejor[2]
        else:
            paso /= 2
    return rl, rf


def analizar(ang, trim, previo, juego):
    piernas, com, art = cuerpo(ang, trim)
    rl, rf = apoyar(piernas, com, previo)
    R = rot_x(rf) @ rot_z(rl)
    mundo = {l: ([R @ p for p in c], np.array([R @ e for e in esq])) for l, (c, esq) in piernas.items()}
    piso = min(esq[:, 1].min() for _, esq in mundo.values())
    for l in mundo:
        c, esq = mundo[l]
        mundo[l] = ([p - [0, piso, 0] for p in c], esq - [0, piso, 0])
    comw = R @ com - [0, piso, 0]
    alto = {l: esq[:, 1].min() for l, (_, esq) in mundo.items()}
    toca = [l for l in alto if alto[l] < 0.5]
    # margen lateral: distancia del centro de masa al borde de lo que toca el piso (solo lateral, en x)
    xs = np.concatenate([mundo[l][1][mundo[l][1][:, 1] < 0.5, 0] for l in toca])
    margen = min(comw[0] - xs.min(), xs.max() - comw[0])
    # con juego: el cuerpo se ladea 'juego' grados mas hacia el lado que no esta apoyado
    perdida = comw[1] * math.tan(math.radians(juego)) if len(toca) == 1 else 0.0
    return {"mundo": mundo, "com": comw, "toca": toca, "alto": alto, "lat": math.degrees(rl), "adel": math.degrees(rf),
            "margen": margen, "margen_juego": margen - perdida, "art": art, "inc": (rl, rf)}


# =====================================================================
# SEGMENTO: DIBUJO
# =====================================================================
def dibujar(res, titulo, ruta):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.2, 4.2))
    colores = {"izq": "#1f77b4", "der": "#d62728"}
    for ax, (i, nombre) in ((a1, (0, "de frente (su izquierda, azul, a la derecha)")), (a2, (2, "de costado (adelante a la derecha)"))):
        ax.axhline(0, color="#888", lw=1)
        for l, (c, esq) in res["mundo"].items():
            xs = [p[0] if i == 0 else p[2] for p in c]
            ax.plot(xs, [p[1] for p in c], "-o", color=colores[l], lw=3, ms=3)
            px = esq[:, 0] if i == 0 else esq[:, 2]
            orden = [0, 1, 3, 2, 0]
            ax.plot(px[orden], esq[orden, 1], "-", color=colores[l], lw=2)
        hx = [res["mundo"]["izq"][0][0][0], res["mundo"]["der"][0][0][0]] if i == 0 else \
             [res["mundo"]["izq"][0][0][2], res["mundo"]["der"][0][0][2]]
        hy = [res["mundo"]["izq"][0][0][1], res["mundo"]["der"][0][0][1]]
        ax.plot(hx, hy, "-", color="#333", lw=4)
        cx = res["com"][0] if i == 0 else res["com"][2]
        ax.plot([cx, cx], [0, res["com"][1]], ":", color="#2ca02c")
        ax.plot(cx, res["com"][1], "o", color="#2ca02c", ms=8)
        ax.set_xlim(-110, 110)
        ax.set_ylim(-5, 175)
        ax.set_aspect("equal")
        ax.set_title(nombre, fontsize=8)
        ax.tick_params(labelsize=7)
    alto = res["alto"]
    fig.suptitle(f"{titulo}\napoya: {'+'.join(res['toca'])}   pie izq {alto['izq']:.0f} mm, der {alto['der']:.0f} mm del piso   "
                 f"margen {res['margen']:.0f} mm (con juego {res['margen_juego']:.0f})", fontsize=8)
    fig.tight_layout()
    fig.savefig(ruta, dpi=90)
    plt.close(fig)


# =====================================================================
# SEGMENTO: PROGRAMA
# =====================================================================
def simular(poses, trim, juego=2.0):
    previo = (0.0, 0.0)
    out = []
    for nombre, ang in poses:
        r = analizar(ang, trim, previo, juego)
        previo = r["inc"]
        out.append((nombre, r))
    return out


def main():
    ref_nombre = sys.argv[sys.argv.index("--ref") + 1] if "--ref" in sys.argv else "Inicionx25"
    juego = float(sys.argv[sys.argv.index("--juego") + 1]) if "--juego" in sys.argv else 2.0
    ref = {int(k): v for k, v in leer(ref_nombre, "posiciones")["angulos"].items()}
    trim = {c: ref.get(c, 0) for c in cn.PIERNAS}
    if "--poses" in sys.argv:
        nombres = sys.argv[sys.argv.index("--poses") + 1].split(",")
        titulo = "poses"
    else:
        titulo = next(a for a in sys.argv[1:] if not a.startswith("--") and sys.argv[sys.argv.index(a) - 1] not in
                      ("--ref", "--juego", "--salida"))
        nombres = [p["posicion"] for p in leer(titulo, "secuencias")["pasos"]]
    poses = [(n, {int(k): v for k, v in leer(n, "posiciones")["angulos"].items()}) for n in nombres]
    res = simular(poses, trim, juego)
    print(f"{titulo}: {len(res)} cuadros, juego supuesto {juego:.0f} grados (cadera + tobillo del pie de apoyo)")
    print(f"{'pose':22s} apoya    pie izq  pie der   ladeo  adel   margen  con juego")
    for n, r in res:
        print(f"{n:22s} {'+'.join(r['toca']):8s} {r['alto']['izq']:6.1f}  {r['alto']['der']:6.1f}  {r['lat']:6.1f} {r['adel']:5.1f}"
              f"  {r['margen']:6.1f}  {r['margen_juego']:7.1f}")
    if "--sin_dibujo" in sys.argv:
        return
    salida = sys.argv[sys.argv.index("--salida") + 1] if "--salida" in sys.argv else os.path.join(BASE, "simulacion", titulo)
    os.makedirs(salida, exist_ok=True)
    rutas = []
    for k, (n, r) in enumerate(res):
        rutas.append(os.path.join(salida, f"{k + 1:02d}.png"))
        dibujar(r, f"{titulo} - {k + 1}/{len(res)}: {n}", rutas[-1])
    from PIL import Image
    ims = [Image.open(p).convert("RGB") for p in rutas]
    ims[0].save(os.path.join(salida, "animacion.gif"), save_all=True, append_images=ims[1:], duration=400, loop=0)
    col = 4
    w, h = ims[0].size
    hoja = Image.new("RGB", (w * col, h * math.ceil(len(ims) / col)), "white")
    for k, im in enumerate(ims):
        hoja.paste(im, ((k % col) * w, (k // col) * h))
    hoja.save(os.path.join(salida, "hoja.png"))
    print("dibujos en", salida)


if __name__ == "__main__":
    main()
