"""SEGMENTO: CHOQUES EN LA MARCHA DEL NX25 (todas las articulaciones a la vez, cuadro por cuadro)
Toma la caminata hacia adelante del codigo original del NX25 (RoboTakao/NX25, fwd_bk_step: 22 cuadros, su
cinematica inversa con L1 = L2 = 28.7 y H1+H2+H3 = 53) y la aplica a nuestro robot:
  - piernas: cadera lateral = atan(Z/Y); muslo = 90 - Theta1 y rodilla = 90 - (Theta1 + Theta2) (angulos del
    eslabon respecto de la vertical, adelante positivo: el servo va en 90 + eso); tobillo = -cadera lateral
    (pie plano) + 30 grados extra en el pie que sube (cuadros 4 y 15)
  - brazos: hombro adelante-atras = ArmStt +- balanceo, hombro abierto = ArmAng, codo = ElbAng
Como el sentido fisico de ArmStt y ElbAng no esta en el codigo (depende del montaje), se prueban los signos.
Reporta, cuadro por cuadro, los choques nuevos respecto de la pose del ensamble.
"""
import itertools
import math
import os
import sys

import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import barrido_movimiento as bm  # noqa: E402

L1 = L2 = 28.7
H123 = 13.54 + 25.92 + 13.54
LIMITE_MUSLO = (-20.0, 60.0)       # adelante positivo (barrido: -25 a +65)
LIMITE_RODILLA = (-60.0, 20.0)     # adelante positivo (barrido: -65 a +25)
MARCHA = dict(Fws=10.0, ArmSwg=20.0, SideS=20.0, CenterX=-8.0, H0=100.0, Up=20.0, ArmStt=20.0, ArmAng=20.0,
              ElbAng=60.0, ankle=30.0)


# ---------------------------------------------------------------------------
# SEGMENTO: MARCHA DEL NX25 (tabla Step_base de fwd_bk_step)
# ---------------------------------------------------------------------------
def cuadros(m):
    F, S, C, H, U = m["Fws"], m["SideS"], m["CenterX"], m["H0"], m["Up"]
    s6, s3 = math.sin(math.pi / 6), math.sin(math.pi / 3)
    # (X, Y, Z) pie derecho, (X, Y, Z) pie izquierdo, balanceo de brazos (fraccion de ArmSwg con signo)
    T = [
        (F + C, H, 0), (-F + C, H, 0), -1.0,
        (F / 3 * 2 + C, H, S * s6), (-F / 3 * 4 + C, H, S * s6), -5 / 6,
        (F / 3 + C, H, S * s3), (-F / 3 * 5 + C, H, S * s3), -4 / 6,
        (C, H, S), (-2 * F + C, H, S), -3 / 6,
        (C, H, S), (-2 * F + C, H - U, S), -2 / 6,
        (C, H, S), (-2 * F + C, H - U, S), -1 / 6,
        (C, H, S), (C, H - U, S), 0.0,
        (C, H, S), (2 * F + C, H - U, S), 1 / 5,
        (C, H, S), (2 * F + C, H, S), 2 / 5,
        (-F / 3 + C, H, S * s3), (F / 3 * 5 + C, H, S * s3), 3 / 5,
        (-F / 3 * 2 + C, H, S * s6), (F / 3 * 4 + C, H, S * s6), 4 / 5,
        (-F + C, H, 0), (F + C, H, 0), 1.0,
        (-F / 3 * 4 + C, H, -S * s6), (F / 3 * 2 + C, H, -S * s6), 5 / 6,
        (-F / 3 * 5 + C, H, -S * s3), (F / 3 + C, H, -S * s3), 4 / 6,
        (-2 * F + C, H, -S), (C, H, -S), 3 / 6,
        (-2 * F + C, H - U, -S), (C, H, -S), 2 / 6,
        (-2 * F + C, H - U, -S), (C, H, -S), 1 / 6,
        (C, H - U, -S), (C, H, -S), 0.0,
        (2 * F + C, H - U, -S), (C, H, -S), -1 / 5,
        (2 * F + C, H, -S), (C, H, -S), -2 / 5,
        (F / 3 * 5 + C, H, -S * s3), (-F / 3 + C, H, -S * s3), -3 / 5,
        (F / 3 * 4 + C, H, -S * s6), (-F / 3 * 2 + C, H, -S * s6), -4 / 5,
    ]
    return [(T[3 * k], T[3 * k + 1], T[3 * k + 2]) for k in range(22)]


# marcha propia: la del NX25 con el pie que avanza subiendo en arco (altura maxima bajo la cadera), paso de
# 16 mm, pie centrado y piernas un poco menos agachadas -> pide como mucho muslo 50 y rodilla -50 (limites 60)
MARCHA_ARCO = dict(MARCHA, Fws=8.0, Up=15.0, CenterX=0.0, H0=105.0)
ARCO_S = (0.2, 0.4, 0.6, 0.8)       # avance del pie en los 4 cuadros en el aire (sube con sin(pi s))


def cuadros_arco(m):
    """22 cuadros como fwd_bk_step, pero el pie en el aire sigue un arco; el balanceo de brazos es el mismo."""
    F, S, C, H, U = m["Fws"], m["SideS"], m["CenterX"], m["H0"], m["Up"]
    s6, s3 = math.sin(math.pi / 6), math.sin(math.pi / 3)
    sw = [c[2] for c in cuadros(m)]
    fr = [((F + C, H, 0), (-F + C, H, 0)), ((F / 3 * 2 + C, H, S * s6), (-F / 3 * 4 + C, H, S * s6)),
          ((F / 3 + C, H, S * s3), (-F / 3 * 5 + C, H, S * s3)), ((C, H, S), (-2 * F + C, H, S))]
    fr += [((C, H, S), (-2 * F + 4 * F * s + C, H - U * math.sin(math.pi * s), S)) for s in ARCO_S]
    fr += [((C, H, S), (2 * F + C, H, S)), ((-F / 3 + C, H, S * s3), (F / 3 * 5 + C, H, S * s3)),
           ((-F / 3 * 2 + C, H, S * s6), (F / 3 * 4 + C, H, S * s6))]
    fr += [((-F + C, H, 0), (F + C, H, 0)), ((-F / 3 * 4 + C, H, -S * s6), (F / 3 * 2 + C, H, -S * s6)),
           ((-F / 3 * 5 + C, H, -S * s3), (F / 3 + C, H, -S * s3)), ((-2 * F + C, H, -S), (C, H, -S))]
    fr += [((-2 * F + 4 * F * s + C, H - U * math.sin(math.pi * s), -S), (C, H, -S)) for s in ARCO_S]
    fr += [((2 * F + C, H, -S), (C, H, -S)), ((F / 3 * 5 + C, H, -S * s3), (-F / 3 + C, H, -S * s3)),
           ((F / 3 * 4 + C, H, -S * s6), (-F / 3 * 2 + C, H, -S * s6))]
    return [(pd, pi, w) for (pd, pi), w in zip(fr, sw)]


def ik(X, Y, Z):
    """cinematica inversa del NX25 -> (cadera lateral, muslo, rodilla) en grados, angulos fisicos."""
    t3 = math.atan2(Z, Y)
    Y2 = Y / math.cos(t3) - H123
    r = math.hypot(X, Y2)
    t1 = -math.acos(min(1.0, (X * X + Y2 * Y2 + L1 * L1 - L2 * L2) / (2 * L1 * r))) + math.atan2(Y2, X)
    t2 = math.atan2(Y2 - L1 * math.sin(t1), X - L1 * math.cos(t1)) - t1
    return math.degrees(t3), 90 - math.degrees(t1), 90 - math.degrees(t1 + t2)


# ---------------------------------------------------------------------------
# SEGMENTO: NUESTRO ROBOT (articulaciones y signos fisicos)
# ---------------------------------------------------------------------------
def afectadas(art, grupos):
    T = bm.transformaciones(art, grupos, 1.0)
    return set(T)


def calibrar(P, piezas, arts, grupos):
    """para cada articulacion: rol, lado y signo que lleva el angulo fisico al giro del ensamble."""
    info = []
    for art in arts:
        nombre = bm.nombre_articulacion(P, None, art)
        lado = 1 if art["u"]["c"][0] > 1 else (-1 if art["u"]["c"][0] < -1 else 0)
        idx = sorted(afectadas(art, grupos))
        if art["tipo"] == "paralelogramo":
            d = art["eje"] / np.linalg.norm(art["eje"])
            v = art["punta"] - art["pivote"]
            fisico = math.degrees(math.atan2(v[2], -v[1]))          # adelante positivo
            phi = bm.angulo_actual(art)
            info.append(dict(art=art, nombre=nombre, lado=lado, signo=np.sign(phi) * np.sign(fisico), actual=phi, idx=idx))
            continue
        # punto de referencia: el centro de lo que mueve (lo mas lejano: mano, pie)
        pts = np.vstack([piezas[i].vertices for i in idx])
        ref = pts[np.argmax(np.linalg.norm(pts - art["u"]["c"], axis=1))]
        R = bm.rotacion(art["u"]["d"], 5.0, art["u"]["c"])
        delta = R[:3, :3] @ ref + R[:3, 3] - ref
        if "tobillo" in nombre or "cadera (lateral)" in nombre:
            signo = np.sign(delta[0])                          # positivo: hacia +x
        elif "abrir" in nombre:
            signo = np.sign(delta[0]) * lado                   # positivo: hacia afuera
        elif "hombro" in nombre or "codo" in nombre:
            signo = np.sign(delta[2])                          # positivo: hacia adelante
        else:
            signo = 1.0
        info.append(dict(art=art, nombre=nombre, lado=lado, signo=signo, actual=0.0, idx=idx))
    info.sort(key=lambda a: -len(a["idx"]))                    # padres primero
    return info


def pose(info, grupos, angulos, n):
    """angulos: nombre -> angulo fisico. Devuelve la matriz de cada pieza (padres primero)."""
    T = [np.eye(4) for _ in range(n)]
    for a in info:
        clave = a["nombre"]
        if clave not in angulos:
            continue
        dtheta = a["signo"] * angulos[clave] - a["actual"]
        for i, M in bm.transformaciones(a["art"], grupos, dtheta).items():
            T[i] = T[i] @ M
    return T


def choques(P, base_m, cajas0, base_v, T):
    n = len(base_m)
    movidas, cajas = [], []
    for i in range(n):
        M = T[i]
        if np.allclose(M, np.eye(4)):
            movidas.append(base_m[i])
            cajas.append((cajas0[i][0], cajas0[i][1]))
        else:
            movidas.append(base_m[i].transform(M[:3, :4]))
            c = trimesh.bounds.corners(cajas0[i]) @ M[:3, :3].T + M[:3, 3]
            cajas.append((c.min(0), c.max(0)))
    clave = [tuple(np.round(M, 4).ravel()) for M in T]
    pares = [(i, j) for i in range(n) for j in range(i + 1, n) if clave[i] != clave[j]]
    v = bm.volumenes(movidas, cajas, pares)
    return sorted([(P[i]["nombre"], P[j]["nombre"], round(vol - base_v.get((i, j), 0.0), 1))
                   for (i, j), vol in v.items() if bm.es_choque(vol, base_v.get((i, j), 0.0))], key=lambda x: -x[2])


def main():
    P, piezas = bm.cargar()
    host, giros, g, raiz, grupos, aristas = bm.estructura(P)
    arts = bm.articulaciones(P, g, raiz, aristas)
    info = calibrar(P, piezas, arts, grupos)
    n = len(piezas)
    base_m = [bm.a_manifold(m) for m in piezas]
    cajas0 = [m.bounds for m in piezas]
    todos = [(i, j) for i in range(n) for j in range(i + 1, n)]
    base_v = bm.volumenes(base_m, cajas0, todos)
    nombres = {a["nombre"] for a in info}
    print("articulaciones:", sorted(nombres))
    marcha = dict(MARCHA_ARCO if "--arco" in sys.argv else MARCHA)
    if "--up15" in sys.argv:
        marcha["Up"] = 15.0
    fr = cuadros_arco(marcha) if "--arco" in sys.argv else cuadros(marcha)
    extremos = [ik(*p)[1:] for c in fr for p in c[:2]]
    print(f"angulos pedidos: muslo {min(e[0] for e in extremos):.0f} a {max(e[0] for e in extremos):.0f}, "
          f"rodilla {min(e[1] for e in extremos):.0f} a {max(e[1] for e in extremos):.0f}")
    for s_stt, s_elb in itertools.product((1, -1), (1, -1)):
        print(f"\n== brazos: ArmStt {'adelante' if s_stt > 0 else 'atras'} {marcha['ArmStt']:.0f}, "
              f"codo {'adelante' if s_elb > 0 else 'atras'} {marcha['ElbAng']:.0f}, abiertos {marcha['ArmAng']:.0f}; "
              f"pie sube {marcha['Up']:.0f} mm")
        total = 0
        for k, (pd, pi, sw) in enumerate(fr):
            ang = {}
            for pie, lado in ((pd, -1), (pi, 1)):
                t3, a1, a2 = ik(*pie)
                if "--limitar" in sys.argv:     # rango seguro medido en el barrido (5 grados de margen)
                    a1 = min(max(a1, LIMITE_MUSLO[0]), LIMITE_MUSLO[1])
                    a2 = min(max(a2, LIMITE_RODILLA[0]), LIMITE_RODILLA[1])
                sufijo = "izq" if lado > 0 else "der"
                ang[f"cadera (lateral) {sufijo}"] = t3
                ang[f"muslo (cadera adelante-atras) {sufijo}"] = a1
                ang[f"rodilla {sufijo}"] = a2
                extra = 0.0
                if (k == 4 and lado > 0) or (k == 15 and lado < 0):
                    extra = marcha["ankle"]
                ang[f"tobillo (lateral) {sufijo}"] = -t3 + extra * (1 if lado > 0 else -1)
            for lado, sufijo in ((-1, "der"), (1, "izq")):
                balanceo = marcha["ArmSwg"] * sw * (1 if lado < 0 else -1)
                ang[f"hombro (adelante-atras) {sufijo}"] = s_stt * marcha["ArmStt"] + balanceo
                ang[f"hombro (abrir brazo) {sufijo}"] = marcha["ArmAng"]
                ang[f"codo {sufijo}"] = s_elb * marcha["ElbAng"]
            ang = {k2: v2 for k2, v2 in ang.items() if k2 in nombres}
            c = choques(P, base_m, cajas0, base_v, pose(info, grupos, ang, n))
            if c:
                total += 1
                print(f"  cuadro {k:2d}: " + "; ".join(f"{a} con {b} ({v} mm3)" for a, b, v in c[:4]), flush=True)
        print(f"  cuadros con choque: {total} de {len(fr)}", flush=True)


if __name__ == "__main__":
    main()
