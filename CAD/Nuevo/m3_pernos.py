"""SEGMENTO: PIPE IMPRESO + TORNILLO M3 EN VEZ DE Pipe_B + M2
Antes (NX25): buje Pipe_B de O5 en agujero de O5.5 (0.25 mm de juego por lado) y un M2
autorroscante en un agujero de O1.8 de la otra pieza (se barre en PLA). Ademas la cabeza del
Pipe_B apoya en el rebaje de la pieza que gira: al apretar, esa pieza queda prensada.
Primer cambio (OldVersions/m3_sin_pipe): el M3 como eje directo; la rosca lija el agujero y al
apretar se prensa la union (lo senalo el usuario, que propuso volver al pipe con paso para M3).
Ahora:
  - Pipe_M3 (impreso, uno igual para todas las uniones): cuerpo O6 x 3.2, cabeza O8.3 x 2.8 con rebaje O6.1 x 1.8
    donde se hunde la cabeza del M3 (como el Pipe_B), paso O3.0 justo para el tornillo
  - v5 (2026-09-19): el v4 habia engordado el cuerpo a O7.6 para que la cabeza del M3 apoyara directo sobre el, y
    con eso el agujero de la pieza que gira (O7.9) dejaba 1 mm de pared en la rodilla. Se vuelve al cuerpo O6 con
    piso de 1 mm, y la cabeza baja de O9 a O8.3 para que la oreja conserve su anillo. Sobresale un poco mas
  - el pipe apoya en la pieza que sujeta y el M3 lo aprieta ahi (agujero O2.7: el M3 corta rosca)
  - la pieza que gira lo hace sobre el cuerpo liso del pipe: agujero O6.3 (0.15 mm por lado) y el
    fondo de su rebaje de O8.6 queda 0.2 mm debajo de la cabeza del pipe, asi no se prensa
Coordenadas locales de cada pieza, a partir de los agujeros detectados en los STL.
"""
import collections
import json
import os
import sys

import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import cables_salida as cs  # noqa: E402

nx = cs.nx
AGUJEROS = os.path.join(os.environ["TEMP"], "claude", "c--Users-rodri-Documents-Proyecto-c--",
                        "22d632c2-4356-4bbd-907c-dd3ee2e82679", "scratchpad", "nx25", "agujeros.json")
SALIDA = os.path.join(BASE, "piezas_m3")

AGARRA_DIAM = 2.7
ROSCA_OBJETIVO = 5.0             # mm de rosca en el plastico: con eso el M3 agarra de sobra (la carga la toma el pipe)
LARGOS_M3 = (6, 8, 10, 12, 14, 16, 20, 25)
EJES = {"X": np.array([1.0, 0, 0]), "Y": np.array([0, 1.0, 0]), "Z": np.array([0, 0, 1.0])}

PIPE_DIAM = 6.0                  # v5: vuelve a O6 para no comerse la pared de la oreja (con O7.6 quedaba 1 mm en la rodilla)
PIPE_LARGO = 1.6                 # v7: cuerpo corto, la cabeza ancha hace de buje adentro del rebaje
PIPE_PASO = 3.0                  # justo para el M3 (antes 3.4: al imprimirlo el pipe quedaba suelto en el tornillo y se corria de costado)
PIPE_CABEZA = (10.0, 2.8)        # v7: cabeza ancha, llena el rebaje O10.3 y hace de buje; asi se hunde en la oreja
# rebaje en la cabeza del pipe para hundir la cabeza boton del M3 (O5.7 x 1.65), como el Pipe_B del NX25
# (que tenia O4.5 para el M2): el tornillo empuja sobre el escalon PIPE_PISO por encima del cuerpo
PIPE_ASIENTO = (6.1, 1.8)        # la cabeza del M3 se hunde entera aca y apoya en el piso de 1 mm (el de 0.6 se partia)
PIPE_PISO = PIPE_CABEZA[1] - PIPE_ASIENTO[1]   # 1.0 mm de piso bajo la cabeza del tornillo
GIRA_PIPE = 6.3                  # agujero de la pieza que gira (0.15 por lado): deja 1.8 mm de pared en la rodilla
ROSCA_MINIMA = 4.0               # si la pared de agarre no da esto, se le agrega un boton atras (si hay lugar)
BOTON_DIAMS = (7.0, 5.5)         # se prueba el ancho y, si choca con un servo, uno mas angosto
BOTON_MAX = 2.0
PUNTA_ASOMA_MAX = 1.5            # si no hay lugar para boton: la punta puede asomar por dentro si no toca ninguna pieza ni servo
PISO_ALTO = 2.0                  # ultimo recurso (servo pegado atras): Pipe_M3_alto, el M3 apoya 1 mm mas arriba que el normal
REBAJE_DIAM = 10.0
COLLAR_RADIOS = (6.35, 5.9, 5.45)  # radios de collar a probar (el ultimo apenas cubre el rebaje O10.3)
COLLAR_PARED = 1.2               # v6: anillo de material alrededor del rebaje. La oreja del NX25 es mas delgada que
COLLAR_TAPA = 0.1                # la cabeza del pipe, asi que se le agrega un collar hasta que la cabeza entra al ras
COLLAR_LABIO = 0.4               # el collar pasa apenas la cara de la oreja, para tapar su labio redondeado
JUEGO_CABEZA = 0.2
S_PRUEBA = np.arange(-3.0, 6.01, 0.05)


def tramos_con_pared(malla, h, paso=0.2):
    """Tramos (desde, hasta) del eje de un agujero donde hay pared de plastico a radio r."""
    eje = EJES[h["eje"]]
    k = "XYZ".index(h["eje"])
    otros = [e for e in EJES.values() if abs(e @ eje) < 0.5]
    dirs = []
    for ang in np.linspace(0, 2 * np.pi, 8, endpoint=False):
        dirs.append(np.cos(ang) * otros[0] + np.sin(ang) * otros[1])
    posiciones = np.arange(h["desde"] + paso / 2, h["hasta"], paso)
    origenes, direcciones, clave = [], [], []
    for j, v in enumerate(posiciones):
        p = np.array(h["centro"], float)
        p[k] = v
        for d in dirs:
            origenes.append(p)
            direcciones.append(d)
            clave.append(j)
    hits, idx, _ = malla.ray.intersects_location(np.array(origenes), np.array(direcciones), multiple_hits=False)
    dist = np.full(len(origenes), np.inf)
    for hp, i in zip(hits, idx):
        dist[i] = min(dist[i], np.linalg.norm(hp - origenes[i]))
    pared = np.zeros(len(posiciones), bool)
    clave = np.array(clave)
    for j in range(len(posiciones)):
        dd = dist[clave == j]
        pared[j] = np.mean(np.abs(dd - h["r"]) < 0.35) >= 0.75
    tramos, ini = [], None
    for j, ok in enumerate(pared):
        if ok and ini is None:
            ini = j
        if (not ok or j == len(pared) - 1) and ini is not None:
            fin = j if ok else j - 1
            if (fin - ini + 1) * paso >= 0.6:
                tramos.append((posiciones[ini] - paso / 2, posiciones[fin] + paso / 2))
            ini = None
    return tramos


def emparejar():
    agujeros = json.load(open(AGUJEROS, encoding="utf-8"))
    piezas = [(n, e, t) for n, e, t in cs.te.ensamble() if not os.path.isabs(n)]
    mallas = {}
    mundo = []
    for i, (n, ejes, t) in enumerate(piezas):
        if n == "Pipe_B":
            continue
        if n not in mallas:
            mallas[n] = trimesh.load(os.path.join(nx.BASE, "stl", n + ".stl"), force="mesh")
            mallas[n + "_tramos"] = {k: tramos_con_pared(mallas[n], h) for k, h in enumerate(agujeros.get(n, []))
                                     if 0.8 < h["r"] < 1.0 or 2.6 < h["r"] < 2.8 or 4.4 < h["r"] < 4.6}
        M = np.column_stack([np.asarray(e, float) for e in ejes])
        t = np.asarray(t, float)
        for k, tramos in mallas[n + "_tramos"].items():
            h = agujeros[n][k]
            eje = EJES[h["eje"]]
            ci = h["centro"]["XYZ".index(h["eje"])]
            for tr in tramos:
                ext = [M @ (np.array(h["centro"]) + eje * (lim - ci)) + t for lim in tr]
                mundo.append(dict(pieza=n, inst=i, idx=k, tramo=tr, r=h["r"], d=M @ eje, ext=ext))
    uniones = []
    for i, (n, ejes, t) in enumerate(piezas):
        if n != "Pipe_B":
            continue
        M = np.column_stack([np.asarray(e, float) for e in ejes])
        d, t = M @ np.array([0, 1.0, 0]), np.asarray(t, float)
        cerca = []
        for h in mundo:
            if abs(abs(h["d"] @ d) - 1) > 0.02:
                continue
            s = sorted(((p - t) @ d for p in h["ext"]))
            c = (h["ext"][0] + h["ext"][1]) / 2 - t
            if np.linalg.norm(c - (c @ d) * d) < 0.6 and s[1] > -8 and s[0] < 8:
                cerca.append((s, h))
        gira = [(s, h) for s, h in cerca if 2.6 < h["r"] < 2.8 and s[1] > 0.0 and s[0] < 4.0]
        asiento = [(s, h) for s, h in cerca if 4.4 < h["r"] < 4.6 and s[1] > 0.0]
        agarra = [(s, h) for s, h in cerca if 0.8 < h["r"] < 1.0 and s[1] <= 1.2]
        if not (gira and agarra):
            print(f"perno #{i}: no se pudo emparejar ({[(round(h['r'], 2), np.round(s, 1).tolist()) for s, h in cerca]})")
            continue
        s_g, h_g = min(gira, key=lambda x: abs(x[0][0]))
        s_a, h_a = max(agarra, key=lambda x: x[0][1])
        asiento_s = min(asiento, key=lambda x: abs(x[0][0] - s_g[1]))[0][0] if asiento else s_g[1]
        uniones.append(dict(perno=i, gira=h_g, agarra=h_a, asiento=asiento_s, fondo=s_a[0], agarre_ini=s_a[1], t=t, d=d))
    return uniones


# ---------------------------------------------------------------------------
# SEGMENTO: PIPE M3 EN CADA UNION
# s = coordenada a lo largo del eje (0 = origen del Pipe_B del NX25, positivo hacia afuera).
# ---------------------------------------------------------------------------
def caras(u, mallas_nx, P):
    """Cara de la pieza que sujeta, fondo del rebaje y cara interior de la que gira (s), midiendo material alrededor del eje."""
    t, d = u["t"], u["d"]
    aux = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    w = np.cross(d, aux)
    w /= np.linalg.norm(w)
    v = np.cross(d, w)

    def perfil(parte, r):
        n, e, tt = P[parte["inst"]]
        M = np.column_stack([np.asarray(x, float) for x in e])
        pts = [M.T @ (t + d * s_ + r * (np.cos(a) * w + np.sin(a) * v) - np.asarray(tt, float))
               for s_ in S_PRUEBA for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)]
        return mallas_nx[n].contains(np.array(pts)).reshape(len(S_PRUEBA), 8).mean(1) > 0.5

    agarre = perfil(u["agarra"], 2.0)
    pared = perfil(u["gira"], 4.2)
    cara_agarre = S_PRUEBA[np.where(agarre)[0].max()] + 0.025
    fondo_rebaje = S_PRUEBA[np.where(pared)[0].max()] + 0.025
    # cara de afuera de la oreja: hay que medirla por fuera del rebaje viejo (O9), donde todavia hay material
    afuera = fondo_rebaje + 1.5
    for r_ in (4.6, 4.75, 4.9, 5.1, 5.4):
        borde = perfil(u["gira"], r_)
        if borde[S_PRUEBA > fondo_rebaje].any():
            afuera = S_PRUEBA[np.where(borde)[0].max()] + 0.025
            break
    interior_giro = S_PRUEBA[np.where(pared)[0].min()] - 0.025
    return cara_agarre, fondo_rebaje, interior_giro, afuera


def a_local(P, inst, puntos):
    n, e, tt = P[inst]
    M = np.column_stack([np.asarray(x, float) for x in e])
    return [M.T @ (p - np.asarray(tt, float)) for p in puntos]


def pipe_malla(piso=None):
    """Pipe_M3 con el mismo marco que el Pipe_B: eje +Y, y = 0 en la punta del cuerpo, cabeza arriba.
    piso: mm entre el cuerpo y el rebaje del tornillo (0 = normal, PISO_ALTO = Pipe_M3_alto)."""
    piso = PIPE_PISO if piso is None else piso
    alto = PIPE_ASIENTO[1] + piso
    cuerpo = trimesh.creation.annulus(r_min=PIPE_PASO / 2, r_max=PIPE_DIAM / 2, height=PIPE_LARGO + 0.02, sections=64)
    cuerpo.apply_translation([0, 0, PIPE_LARGO / 2])
    partes = [cuerpo]
    if piso > 0:
        base = trimesh.creation.annulus(r_min=PIPE_PASO / 2, r_max=PIPE_CABEZA[0] / 2, height=piso + 0.02, sections=64)
        base.apply_translation([0, 0, PIPE_LARGO + piso / 2])
        partes.append(base)
    aro = trimesh.creation.annulus(r_min=PIPE_ASIENTO[0] / 2, r_max=PIPE_CABEZA[0] / 2, height=PIPE_ASIENTO[1], sections=64)
    aro.apply_translation([0, 0, PIPE_LARGO + piso + PIPE_ASIENTO[1] / 2 - 0.01])
    partes.append(aro)
    m = trimesh.boolean.union(partes, engine="manifold")
    m.apply_transform([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]])   # eje Z -> Y
    return m


def main():
    cs.te.ensamble = nx.ensamble          # el emparejado usa las posiciones del Pipe_B del NX25
    uniones = emparejar()
    P = [(n, e, t) for n, e, t in nx.ensamble() if not os.path.isabs(n)]
    mallas_nx = {n: trimesh.load(os.path.join(nx.BASE, "stl", n + ".stl"), force="mesh") for n in {p[0] for p in P}}
    mundo = [(n, m) for n, m in cs.piezas_impresas() if not n.startswith("Pipe_B")]
    # servos (MG90S simplificado: cuerpo, pestanas y torre) para que el boton de atras no choque con ninguno
    for k_, (_, e_, t_) in enumerate(nx.servos([p_ for p_ in nx.ensamble() if not os.path.isabs(p_[0])])):
        partes_ = [trimesh.creation.box(bounds=[[-11.4, 0, -6.1], [11.4, 22.8, 6.1]]),
                   trimesh.creation.box(bounds=[[-16.1, 17.0, -6.1], [16.1, 19.5, 6.1]])]
        torre_ = trimesh.creation.cylinder(radius=5.9, segment=[[-5.5, 22.8, 0], [-5.5, 28.5, 0]])
        servo_ = trimesh.boolean.union(partes_ + [torre_], engine="manifold")
        T_ = np.eye(4); T_[:3, :3] = np.column_stack([np.asarray(x, float) for x in e_]); T_[:3, 3] = t_
        servo_.apply_transform(T_)
        mundo.append((f"MG90S#{k_}", servo_))
    agujeros = json.load(open(AGUJEROS, encoding="utf-8"))
    cambios = collections.defaultdict(list)       # pieza -> [(tipo, radio, p0 local, p1 local)]
    tabla = collections.Counter()
    collares = collections.Counter()
    radios = collections.Counter()
    pipes = []
    for u in uniones:
        cara, fondo_viejo, interior, afuera = caras(u, mallas_nx, P)
        t, d = u["t"], u["d"]
        fondo_nuevo = cara + PIPE_LARGO - JUEGO_CABEZA       # fondo del rebaje de O9: 0.2 mm debajo de la cabeza del pipe
        cabeza_arriba = cara + PIPE_LARGO + PIPE_PISO        # donde apoya la cabeza del M3 (fondo del rebaje del pipe)
        g, a = u["gira"], u["agarra"]

        def punto(s_):
            return t + d * s_
        # pieza que gira: collar hasta donde la cabeza del pipe entra al ras. Si enfrente hay otra pieza (union
        # en horquilla, como el hombro), se lo recorta hasta donde entra sin tocarla.
        # el collar ensancha la oreja, pero NO sube por encima de la cara que ya tenia (el usuario no quiere torres):
        # la cabeza del pipe sigue asomando un poco, como antes
        ideal = min(fondo_nuevo + JUEGO_CABEZA + PIPE_CABEZA[1] + COLLAR_TAPA, afuera + COLLAR_LABIO)
        otros_g = [(n_, m_) for n_, m_ in mundo if not n_.startswith(g["pieza"])]
        base_collar = min(fondo_viejo, fondo_nuevo) - 0.3      # el rebaje nuevo baja mas que el del NX25
        collar, collar_r = base_collar, REBAJE_DIAM / 2 + 0.15 + COLLAR_PARED
        for r_ in COLLAR_RADIOS:          # el mas grueso que entre; en las horquillas el de al lado no deja
            for prueba in np.arange(ideal, base_collar, -0.2):
                cil = trimesh.creation.cylinder(radius=r_, segment=[punto(base_collar), punto(prueba)])
                if not cs.volumen_choque(cil, otros_g):
                    if prueba > collar:
                        collar, collar_r = prueba, r_
                    break
            if collar >= ideal - 0.01:
                break
        collares[round(fondo_nuevo + JUEGO_CABEZA + PIPE_CABEZA[1] - collar, 1)] += 1   # cuanto asoma la cabeza
        radios[round(collar_r * 2, 1)] += 1
        cambios[g["pieza"]].append(("union", collar_r, *a_local(P, g["inst"], [punto(base_collar), punto(collar)])))
        cambios[g["pieza"]].append(("corte", GIRA_PIPE / 2, *a_local(P, g["inst"], [punto(interior - 0.5), punto(fondo_nuevo + 0.3)])))
        # radios bien distintos de los del STL viejo (O9): si casi coinciden quedan astillas en el booleano
        cambios[g["pieza"]].append(("corte", REBAJE_DIAM / 2 + 0.15, *a_local(P, g["inst"], [punto(fondo_nuevo), punto(collar + 8.0)])))
        # tornillo: la punta tiene que quedar DENTRO de la pieza que agarra (profundizar el agujero perforaba aire
        # en las paredes delgadas y la punta salia del otro lado). El mas corto con ROSCA_OBJETIVO de rosca; si la
        # pared no alcanza, el mas largo que entre.
        entran = [l for l in LARGOS_M3 if l <= cabeza_arriba - u["fondo"] + 0.3]
        largo = min((l for l in entran if l - (cabeza_arriba - cara) >= ROSCA_OBJETIVO), default=max(entran, default=None))
        extra = 0.0
        rosca = (largo - (cabeza_arriba - cara)) if largo else 0
        boton = 0.0
        if rosca < ROSCA_MINIMA:
            # pared delgada: boton detras del agujero para que un tornillo mas largo quede cubierto (si no choca con nada)
            for l in LARGOS_M3:
                if l - (cabeza_arriba - cara) < ROSCA_MINIMA:
                    continue
                need = u["fondo"] - (cabeza_arriba - l) + 0.4
                if need > BOTON_MAX:
                    break
                otros = [(n_, m_) for n_, m_ in mundo if not n_.startswith(a["pieza"])]
                for diam in BOTON_DIAMS:
                    cil = trimesh.creation.cylinder(radius=diam / 2, segment=[punto(u["fondo"] - 0.05), punto(u["fondo"] - need)])
                    if not cs.volumen_choque(cil, otros):
                        boton, extra, largo = need, need, l
                        rosca = l - (cabeza_arriba - cara)
                        cambios[a["pieza"]].append(("union", diam / 2, *a_local(P, a["inst"], [punto(u["fondo"] + 0.3), punto(u["fondo"] - need)])))
                        break
                break
        asoma = 0.0
        if rosca < ROSCA_MINIMA and not boton:
            # sin lugar para un boton (servo pegado atras): la punta puede asomar hacia adentro si no toca nada
            for l in sorted(LARGOS_M3, reverse=True):
                punta_s = cabeza_arriba - l
                sobra = u["fondo"] - punta_s
                if sobra > PUNTA_ASOMA_MAX or l - (cabeza_arriba - cara) < ROSCA_MINIMA:
                    continue
                cil = trimesh.creation.cylinder(radius=1.6, segment=[punto(u["fondo"] - 0.05), punto(punta_s - 0.3)])
                otros = [(n_, m_) for n_, m_ in mundo if not n_.startswith(a["pieza"])]
                if not cs.volumen_choque(cil, otros):
                    largo, asoma = l, sobra
                    rosca = l - (cabeza_arriba - cara)
                    break
        tipo_pipe = "normal"
        if rosca < ROSCA_MINIMA and not boton and not asoma:
            apoyo = cara + PIPE_LARGO + PISO_ALTO
            entran_alto = [l for l in LARGOS_M3 if l <= apoyo - u["fondo"] + 0.1]
            if entran_alto and max(entran_alto) - (apoyo - cara) > rosca:
                tipo_pipe, largo = "alto", max(entran_alto)
                rosca = largo - (apoyo - cara)
        estado = ("OK" if rosca >= 3.5 else "REVISAR") + (f" (boton de {boton:.1f} mm atras)" if boton else "") +                  (" (Pipe_M3_alto)" if tipo_pipe == "alto" else "") +                  (f" (la punta asoma {asoma:.1f} mm hacia adentro, sin tocar nada)" if asoma else "")
        h = agujeros[a["pieza"]][a["idx"]]
        k = "XYZ".index(h["eje"])
        lim = (a["tramo"][0] - 0.01 - extra, a["tramo"][1] + 0.01 + extra)
        cambios[a["pieza"]].append(("corte", AGARRA_DIAM / 2, *[np.where(np.arange(3) == k, x, np.asarray(h["centro"], float)) for x in lim]))
        tabla[(largo, g["pieza"], a["pieza"], round(rosca, 1), estado)] += 1
        n, e, tt = P[a["inst"]]
        M = np.column_stack([np.asarray(x, float) for x in e])
        pipes.append(dict(agarra=a["pieza"], gira=g["pieza"], origen=(M.T @ (punto(cara) - np.asarray(tt, float))).tolist(),
                          eje=(M.T @ d).tolist(), agarra_t_nx=np.asarray(tt, float).tolist(),
                          agarra_ejes_nx=[list(map(float, x)) for x in e], tornillo=largo, tipo=tipo_pipe,
                          subio_rebaje=round(float(fondo_nuevo - fondo_viejo), 2)))
    resumen = []
    print(f"{'M3 x':>5} {'cant':>4}  {'gira en':12s} {'agarra en':12s} {'rosca en plastico':>18}")
    for (largo, g, a, rosca, estado), n in sorted(tabla.items(), key=lambda x: (x[0][0] or 0)):
        print(f"{largo!s:>5} {n:>4}  {g:12s} {a:12s} {rosca:>15.1f} mm  {estado}")
        resumen.append(dict(largo=largo, cantidad=n, gira=g, agarra=a, rosca=rosca, estado=estado))
    print("cuanto asoma la cabeza del pipe sobre la cara de la oreja (mm):", dict(sorted(collares.items())))
    print("diametro del collar que entro (mm):", dict(sorted(radios.items())))
    print("uniones:", len(uniones), "| cambio del fondo del rebaje (mm):", sorted({p["subio_rebaje"] for p in pipes}))

    os.makedirs(SALIDA, exist_ok=True)
    json.dump(resumen, open(os.path.join(SALIDA, "tornillos_m3.json"), "w", encoding="utf-8"), indent=1)
    json.dump(pipes, open(os.path.join(SALIDA, "pipes_m3.json"), "w", encoding="utf-8"), indent=1)
    pipe_malla().export(os.path.join(SALIDA, "Pipe_M3.stl"))
    pipe_malla(PISO_ALTO).export(os.path.join(SALIDA, "Pipe_M3_alto.stl"))
    for pieza, lista in sorted(cambios.items()):
        # las piezas que se usan dos veces (izq/der) repiten los mismos cortes: quitar duplicados
        lista = list({(tipo, round(r, 2), tuple(np.round(p0, 1)), tuple(np.round(p1, 1))): (tipo, r, p0, p1)
                     for tipo, r, p0, p1 in lista}.values())
        brida = os.path.join(BASE, "piezas_canales", pieza + "_brida.stl")
        malla = trimesh.load(brida if os.path.exists(brida) else os.path.join(nx.BASE, "stl", pieza + ".stl"), force="mesh")
        rellenos = [trimesh.creation.cylinder(radius=r, segment=[p0, p1], sections=48) for tipo, r, p0, p1 in lista if tipo == "union"]
        if rellenos:
            malla = trimesh.boolean.union([malla] + rellenos, engine="manifold")
        cortes = [trimesh.creation.cylinder(radius=r, segment=[p0, p1], sections=48) for tipo, r, p0, p1 in lista if tipo == "corte"]
        malla = trimesh.boolean.difference([malla, trimesh.boolean.union(cortes, engine="manifold")], engine="manifold")
        # quedarse con el cuerpo principal: los cortes al ras de caras viejas dejan astillas de volumen ~0
        partes = malla.split(only_watertight=False)
        malla = max(partes, key=lambda c: abs(c.volume))
        malla.remove_unreferenced_vertices()
        malla.merge_vertices(digits_vertex=4)          # vertices a <0.0001 mm: sin esto el STL no cierra al recargar
        # pasada por manifold3d: descarta triangulos degenerados sueltos que al recargar el STL aparecen como "cuerpos" de volumen 0
        import manifold3d
        limpia = manifold3d.Manifold(manifold3d.Mesh(vert_properties=np.asarray(malla.vertices, np.float32),
                                                     tri_verts=np.asarray(malla.faces, np.uint32))).to_mesh()
        malla = trimesh.Trimesh(limpia.vert_properties[:, :3], limpia.tri_verts)
        malla.export(os.path.join(SALIDA, pieza + ".stl"))
        astillas = sum(abs(c.volume) for c in partes) - abs(malla.volume)
        recargada = trimesh.load(os.path.join(SALIDA, pieza + ".stl"), force="mesh")
        print(f"{pieza}: {len(rellenos)} rebajes subidos, {len(cortes)} cortes, astillas quitadas {astillas:.2f} mm3, "
              f"STL valido {recargada.is_volume} ({len(recargada.split(only_watertight=False))} cuerpo)")


if __name__ == "__main__":
    main()
