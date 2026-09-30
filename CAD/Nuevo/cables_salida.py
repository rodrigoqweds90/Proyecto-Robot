"""SEGMENTO: SALIDA DE CABLES DE LOS SERVOS
Para cada MG90S del robot arma un bloque donde sale su cable (cara corta del lado del
eje, pegado a la base) y revisa contra que pieza impresa choca. Tambien prueba hacia
donde puede escapar el cable sin atravesar plastico.

Coordenadas locales del modelo MG90S (mm): base en y = 0, eje en x = -5.5 hacia +Y,
cuerpo de x -11.5 a 11.5 y z -6 a 6. Los 3 cables salen en x -11.5, y 0..5, z +-1.75.
"""
import os
import sys

import numpy as np
import trimesh

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import torso_estudio as te  # noqa: E402

nx = te.nx

# cinta de 3 cables del MG90S: ~3.5 x 1.2 mm; con juego de impresion
CINTA_ANCHO = 3.5
CINTA_ESPESOR = 1.2
JUEGO = 0.3
# bloque de salida (local del servo): desde la cara del cuerpo hasta 5 mm afuera
SALIDA = dict(x=(-16.5, -11.6), y=(-1.0, 6.5), z=(-(CINTA_ANCHO / 2 + 0.9), CINTA_ANCHO / 2 + 0.9))
# caminos de escape a probar (local del servo)
ESCAPES = {
    "afuera (-x)": dict(x=(-40.0, -11.6), y=(-1.0, 6.5), z=SALIDA["z"]),
    "abajo (-y)": dict(x=(-16.5, -11.6), y=(-25.0, 6.5), z=SALIDA["z"]),
    "costado +z": dict(x=(-16.5, -11.6), y=(-1.0, 6.5), z=(SALIDA["z"][0], 25.0)),
    "costado -z": dict(x=(-16.5, -11.6), y=(-1.0, 6.5), z=(-25.0, SALIDA["z"][1])),
}


def caja_local(lim, m_rot, t):
    tam = [lim[a][1] - lim[a][0] for a in "xyz"]
    centro = np.array([(lim[a][0] + lim[a][1]) / 2 for a in "xyz"])
    caja = trimesh.creation.box(extents=tam)
    mat = np.eye(4)
    mat[:3, :3] = m_rot
    mat[:3, 3] = m_rot @ centro + t
    caja.apply_transform(mat)
    return caja


def piezas_impresas():
    """(nombre, malla en el mundo) de todo lo impreso."""
    cache, salida = {}, []
    for i, (nombre, ejes, t) in enumerate(te.ensamble()):
        base = os.path.basename(nombre)
        if os.path.isabs(nombre):
            if not base.startswith("Torso_"):
                continue
            ruta = os.path.join(BASE, "stl", base.replace(".ipt", ".stl"))
        else:
            ruta = os.path.join(nx.BASE, "stl", nombre + ".stl")
        if ruta not in cache:
            cache[ruta] = trimesh.load(ruta, force="mesh")
        malla = cache[ruta].copy()
        mat = np.eye(4)
        mat[:3, :3] = np.column_stack([np.asarray(e, float) for e in ejes])
        mat[:3, 3] = t
        malla.apply_transform(mat)
        salida.append((f"{os.path.splitext(base)[0]}#{i}", malla))
    return salida


def servos():
    lista = []
    for nombre, ejes, t in te.ensamble():
        if nombre == nx.SERVO:
            lista.append((np.column_stack([np.asarray(e, float) for e in ejes]), np.asarray(t, float)))
    return lista


def volumen_choque(caja, piezas):
    choques = []
    for nombre, malla in piezas:
        if not caja.bounds[0].__le__(malla.bounds[1]).all() or not malla.bounds[0].__le__(caja.bounds[1]).all():
            continue
        inter = trimesh.boolean.intersection([caja, malla], engine="manifold")
        if inter.volume > 0.05:
            choques.append((nombre, inter.volume))
    return choques


def main():
    piezas = piezas_impresas()
    for n, (m_rot, t) in enumerate(servos()):
        eje = m_rot @ np.array([0, 1.0, 0])
        salida_w = m_rot @ np.array([-11.5, 2.5, 0]) + t
        choques = volumen_choque(caja_local(SALIDA, m_rot, t), piezas)
        print(f"\nServo {n:2d} salida del cable en {np.round(salida_w, 1)} | eje {np.round(eje, 2)}")
        print("   aprieta:", ", ".join(f"{c} {v:.1f} mm3" for c, v in choques) if choques else "nada (libre)")
        libres = []
        for nombre, lim in ESCAPES.items():
            vol = sum(v for _, v in volumen_choque(caja_local(lim, m_rot, t), piezas))
            libres.append((vol, nombre))
        print("   escapes:", ", ".join(f"{nombre} {vol:.0f} mm3" for vol, nombre in sorted(libres)))


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# SEGMENTO: CANAL MINIMO PARA CADA CABLE
# Zona de salida (el cable se dobla pegado a la cara del servo) + canal en una direccion,
# avanzando de a 1 mm hasta que dos rebanadas seguidas quedan libres de plastico.
# ---------------------------------------------------------------------------
ANCHO_CANAL = CINTA_ANCHO / 2 + 0.45          # medio ancho: 1.75 de cinta + juego
ZONA = dict(x=(-15.0, -11.6), y=(-0.5, 6.0), z=(-ANCHO_CANAL, ANCHO_CANAL))
DIRECCIONES = {
    "afuera": ("x", -1, dict(y=ZONA["y"], z=ZONA["z"]), -11.6),
    "abajo": ("y", -1, dict(x=ZONA["x"], z=ZONA["z"]), -0.5),
    "costado+": ("z", +1, dict(x=ZONA["x"], y=ZONA["y"]), ANCHO_CANAL),
    "costado-": ("z", -1, dict(x=ZONA["x"], y=ZONA["y"]), -ANCHO_CANAL),
}


def canal(direccion, largo):
    eje, signo, resto, inicio = DIRECCIONES[direccion]
    lim = dict(resto)
    fin = inicio + signo * largo
    lim[eje] = (min(inicio, fin), max(inicio, fin))
    return lim


def mejor_canal(m_rot, t, piezas, largo_max=30):
    zona_vol = sum(v for _, v in volumen_choque(caja_local(ZONA, m_rot, t), piezas))
    opciones = []
    for direccion in DIRECCIONES:
        libres, cortado, largo = 0, 0.0, 0
        for paso in range(1, largo_max + 1):
            eje, signo, resto, inicio = DIRECCIONES[direccion]
            lim = dict(resto)
            a, b = inicio + signo * (paso - 1), inicio + signo * paso
            lim[eje] = (min(a, b), max(a, b))
            vol = sum(v for _, v in volumen_choque(caja_local(lim, m_rot, t), piezas))
            cortado += vol
            libres = libres + 1 if vol < 0.05 else 0
            if libres == 2:
                largo = paso
                break
        if largo:
            opciones.append((cortado, direccion, largo))
    opciones.sort()
    return zona_vol, opciones


def informe_canales():
    piezas = piezas_impresas()
    resultado = []
    for n, (m_rot, t) in enumerate(servos()):
        zona_vol, opciones = mejor_canal(m_rot, t, piezas)
        if zona_vol < 0.05 and opciones and opciones[0][0] < 0.05:
            print(f"Servo {n:2d}: libre")
            continue
        texto = ", ".join(f"{d} {v:.0f} mm3 en {l} mm" for v, d, l in opciones) or "sin salida en 30 mm"
        print(f"Servo {n:2d}: zona {zona_vol:.0f} mm3 | {texto}")
        resultado.append((n, zona_vol, opciones))
    return resultado


# ---------------------------------------------------------------------------
# SEGMENTO: CORTAR LOS CANALES EN LOS STL
# Se pasa cada caja (zona + canal) al sistema local de la pieza que aprieta; si una
# pieza se usa varias veces (izq/der, muslo/tibia) se cortan todas sus cajas juntas,
# asi se imprime un solo modelo que sirve en cualquier posicion.
# ---------------------------------------------------------------------------
SALIDA_STL = os.path.join(BASE, "stl_con_canales")


def instancias():
    """(nombre stl, matriz 4x4 local->mundo, malla en el mundo) de las piezas del NX25."""
    lista = []
    cache = {}
    for i, (nombre, ejes, t) in enumerate(te.ensamble()):
        if os.path.isabs(nombre):
            continue
        ruta = os.path.join(nx.BASE, "stl", nombre + ".stl")
        if ruta not in cache:
            cache[ruta] = trimesh.load(ruta, force="mesh")
        mat = np.eye(4)
        mat[:3, :3] = np.column_stack([np.asarray(e, float) for e in ejes])
        mat[:3, 3] = t
        malla = cache[ruta].copy()
        malla.apply_transform(mat)
        lista.append((nombre, mat, malla))
    return lista


def aplicar_canales():
    piezas = piezas_impresas()
    inst = instancias()
    cortes = {}   # nombre -> lista de cajas en coordenadas locales de la pieza
    for n, (m_rot, t) in enumerate(servos()):
        zona_vol, opciones = mejor_canal(m_rot, t, piezas)
        if zona_vol < 0.05 and opciones and opciones[0][0] < 0.05:
            continue
        # entre los costados (los mas baratos) gana el que apunta hacia atras del robot
        costados = [o for o in opciones if o[1].startswith("costado")]
        minimo = min(o[0] for o in costados)
        empatados = [o for o in costados if o[0] < minimo + 5]
        atras = lambda o: (m_rot @ np.array([0, 0, 1.0 if o[1] == "costado+" else -1.0]))[2]
        vol, direccion, largo = min(empatados, key=atras)
        cajas_mundo = [caja_local(ZONA, m_rot, t), caja_local(canal(direccion, largo + 1), m_rot, t)]
        dir_mundo = m_rot @ np.array([0, 0, 1.0 if direccion == "costado+" else -1.0])
        tocadas = []
        for nombre, mat, malla in inst:
            if any(volumen_choque(c, [(nombre, malla)]) for c in cajas_mundo):
                inv = np.linalg.inv(mat)
                for c in cajas_mundo:
                    local = c.copy()
                    local.apply_transform(inv)
                    cortes.setdefault(nombre, []).append(local)
                tocadas.append(nombre)
        print(f"Servo {n:2d}: canal hacia {direccion} ({np.round(dir_mundo, 2)} en el mundo), {largo} mm, "
              f"corta {zona_vol + vol:.0f} mm3 en {', '.join(tocadas)}")

    os.makedirs(SALIDA_STL, exist_ok=True)
    for nombre, cajas in cortes.items():
        original = trimesh.load(os.path.join(nx.BASE, "stl", nombre + ".stl"), force="mesh")
        # cajas repetidas (misma posicion local) se cortan una sola vez
        unicas = []
        for c in cajas:
            if not any(np.allclose(c.bounds, u.bounds, atol=0.05) for u in unicas):
                unicas.append(c)
        herramienta = trimesh.boolean.union(unicas, engine="manifold")
        nuevo = trimesh.boolean.difference([original, herramienta], engine="manifold")
        nuevo.export(os.path.join(SALIDA_STL, nombre + ".stl"))
        print(f"{nombre}: {len(unicas)} cajas, quita {original.volume - nuevo.volume:.0f} mm3 "
              f"({100 * (original.volume - nuevo.volume) / original.volume:.1f}%), estanco: {nuevo.is_watertight}")
