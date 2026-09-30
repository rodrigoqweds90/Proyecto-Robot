"""SEGMENTO: UNIONES DEL ROBOT EN INVENTOR (que se mueva como mecanismo)
Abre Torso_estudio.iam (piezas sin aligerar) y restringe cada pieza:
  - rigidas: cada servo con su soporte; electronica, barra y aro espaciador con el torso
  - giratorias: horn <-> eje del servo, y cada perno M3 (antes Pipe_B) con la pieza de la otra oreja
La pelvis queda fija (anclada). Las piernas cierran paralelogramos (muslo y tibia): la union que
cierra cada lazo lleva solo el eje, sin el plano axial, para no sobre-restringir.
Como las piezas del NX25 son mallas (sin caras ni aristas), cada union usa ejes y planos de trabajo
agregados a las piezas en el lugar exacto del ensamble. Guarda Robot_armado.iam.
"""
import collections
import json
import os
import sys

import numpy as np
import pythoncom
import pywintypes
import win32com.client
from win32com.client import dynamic, gencache

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import torso_estudio as te  # noqa: E402

nx = te.nx
AGUJEROS = os.path.join(os.environ["TEMP"], "claude", "c--Users-rodri-Documents-Proyecto-c--",
                        "22d632c2-4356-4bbd-907c-dd3ee2e82679", "scratchpad", "nx25", "agujeros.json")
EJES = {"X": np.array([1.0, 0, 0]), "Y": np.array([0, 1.0, 0]), "Z": np.array([0, 0, 1.0])}
BRACKET06 = (np.column_stack([-nx.X, nx.Y, -nx.Z]), np.zeros(3))     # la pelvis usa los datos del Bracket06
EJE_SERVO_LOCAL = np.array([-5.5, 0.0, 0.0])                         # eje del MG90S: x -5.5, hacia +Y


def dyn(o):
    return dynamic.Dispatch(o._oleobj_) if hasattr(o, "_oleobj_") else o


# ---------------------------------------------------------------------------
# SEGMENTO: GEOMETRIA DE LAS UNIONES (en el mundo, mm)
# ---------------------------------------------------------------------------
def piezas():
    lista = []
    for nombre, ejes, t in te.ensamble():
        base = os.path.splitext(os.path.basename(nombre))[0]
        lista.append(dict(nombre=base, M=np.column_stack([np.asarray(e, float) for e in ejes]), t=np.asarray(t, float)))
    return lista


def rigidas(P):
    """indice de pieza -> indice del soporte al que va fija (o None si es independiente)."""
    torso = next(i for i, p in enumerate(P) if p["nombre"] == "Torso_cuerpo" + te.torso.SUF)
    host = {}
    for i, p in enumerate(P):
        if p["nombre"].startswith("MG90S"):
            host[i] = torso                                         # por defecto: servos del marco (cintura, cuello, hombros)
            for j, q in enumerate(P):
                if q["nombre"] in nx.SERVOS_EN and q["nombre"] != "Frame01_W":
                    for _, _, o in nx.servos([(q["nombre"], list(q["M"].T), q["t"])]):
                        if np.allclose(o, p["t"], atol=0.01):
                            host[i] = j
        elif p["nombre"].startswith(("PCA9685", "ESP32", "Bateria", "XL4015", "Fichas", "IMU", "Torso_barra", "Torso_pecho", "Torso_espalda", "Torso_atras", "Spacer01")):
            host[i] = torso
        elif p["nombre"].startswith("Pipe_M3"):
            host[i] = dict(te.PIPE_HOSTS)[i]                         # fijo a la pieza que lo sujeta
        elif p["nombre"] == "Cabeza_tapa":
            host[i] = next(j for j, q in enumerate(P) if q["nombre"] == "Cabeza_frente")
    return host


def uniones_giratorias(P, host):
    agujeros = json.load(open(AGUJEROS, encoding="utf-8"))
    grupo = lambda i: host.get(i, i)
    servos = [(i, p["M"] @ EJE_SERVO_LOCAL + p["t"], p["M"][:, 1]) for i, p in enumerate(P) if p["nombre"].startswith("MG90S")]
    lista = []

    def ya_esta(a, b, c, d):
        for u in lista:
            if {grupo(u["a"]), grupo(u["b"])} == {grupo(a), grupo(b)} and abs(abs(u["d"] @ d) - 1) < 0.02:
                w = c - u["c"]
                if np.linalg.norm(w - (w @ d) * d) < 1.0:
                    return True
        return False

    def marco(i):
        p = P[i]
        return BRACKET06 if p["nombre"] == "Pelvis" else (p["M"], p["t"])

    def datos(i, tabla):
        nombre = "Bracket06_W" if P[i]["nombre"] == "Pelvis" else P[i]["nombre"]
        return tabla.get(nombre, [])

    # horn <-> servo
    for i in range(len(P)):
        M, t = marco(i)
        for p, e in datos(i, nx.HORNS_EN):
            c, d = M @ np.asarray(p, float) + t, M @ np.asarray(e, float)
            mejor = None
            for s, eje_p, ys in servos:
                if grupo(s) == grupo(i) or abs(abs(d @ ys) - 1) > 0.02:
                    continue
                w = c - eje_p
                perp = np.linalg.norm(w - (w @ ys) * ys)
                if perp < 1.5 and (mejor is None or abs(w @ ys - 31.5) < mejor[1]):
                    mejor = (s, abs(w @ ys - 31.5))
            if mejor:
                lista.append(dict(a=i, b=mejor[0], c=c, d=d / np.linalg.norm(d), tipo="horn"))
    # cuello: la cabeza gira sobre el eje del servo de arriba del torso
    for i, p in enumerate(P):
        if p["nombre"] == "Cabeza_frente":
            for s, eje_p, ys in servos:
                w = p["t"] - eje_p
                if ys @ np.array([0, 1.0, 0]) > 0.99 and np.linalg.norm(w - (w @ ys) * ys) < 1.5:
                    c = np.array([p["t"][0], eje_p[1] + te.TORRE_ARRIBA_SERVO + te.COLLAR_HORN, p["t"][2]])
                    lista.append(dict(a=i, b=s, c=c, d=np.array([0, 1.0, 0]), tipo="cuello"))
    # pernos (antes Pipe_B) <-> agujero coaxial de otra pieza
    for i in range(len(P)):
        M, t = marco(i)
        for p, e in datos(i, nx.PIPES_EN):
            c, d = M @ np.asarray(p, float) + t, M @ np.asarray(e, float)
            mejor = None
            for j, q in enumerate(P):
                if grupo(j) == grupo(i) or q["nombre"] not in agujeros:
                    continue
                for h in agujeros[q["nombre"]]:
                    if not (0.8 < h["r"] < 1.0 or 2.6 < h["r"] < 2.8):
                        continue
                    hd = q["M"] @ EJES[h["eje"]]
                    if abs(abs(hd @ d) - 1) > 0.02:
                        continue
                    hc = q["M"] @ np.asarray(h["centro"], float) + q["t"]
                    w = hc - c
                    perp = np.linalg.norm(w - (w @ d) * d)
                    k = "XYZ".index(h["eje"])
                    extremos = [q["M"] @ np.where(np.arange(3) == k, lim, np.asarray(h["centro"], float)) + q["t"] for lim in (h["desde"], h["hasta"])]
                    axial = min(abs((x - c) @ d) for x in extremos)
                    if perp < 0.8 and axial < 12 and (mejor is None or perp + axial / 10 < mejor[1]):
                        mejor = (j, perp + axial / 10)
            if mejor and not ya_esta(i, mejor[0], c, d / np.linalg.norm(d)):
                lista.append(dict(a=i, b=mejor[0], c=c, d=d / np.linalg.norm(d), tipo="perno"))
    return lista


def ordenar(P, host, giros, raiz):
    """Recorre desde la pelvis: la union que llega a un grupo nuevo lleva eje + plano; la que cierra un lazo, solo eje."""
    grupo = lambda i: host.get(i, i)
    conectados, orden, pendientes = {grupo(raiz)}, [], list(giros)
    while pendientes:
        avance = False
        for u in list(pendientes):
            ga, gb = grupo(u["a"]), grupo(u["b"])
            if ga in conectados or gb in conectados:
                u["lazo"] = ga in conectados and gb in conectados
                conectados |= {ga, gb}
                orden.append(u)
                pendientes.remove(u)
                avance = True
        if not avance:
            break
    return orden, pendientes


# ---------------------------------------------------------------------------
# SEGMENTO: INVENTOR
# ---------------------------------------------------------------------------
class Referencias:
    """Ejes y planos de trabajo fijos dentro de cada documento de pieza (sin repetir los iguales)."""

    def __init__(self, app):
        self.tg = app.TransientGeometry
        self.cache = {}

    def _local(self, occ, P, i, c, v):
        M, t = P[i]["M"], P[i]["t"]
        return M.T @ (c - t), M.T @ v

    def eje(self, occ, P, i, c, d):
        cl, dl = self._local(occ, P, i, c, d)
        return self._crear(occ, ("eje", cl, dl), lambda cd: cd.WorkAxes.AddFixed(
            self.tg.CreatePoint(*(cl / 10)), self.tg.CreateUnitVector(*dl)))

    def plano(self, occ, P, i, c, n):
        cl, nl = self._local(occ, P, i, c, n)
        aux = np.array([1.0, 0, 0]) if abs(nl[0]) < 0.9 else np.array([0, 1.0, 0])
        xl = np.cross(aux, nl); xl /= np.linalg.norm(xl)
        yl = np.cross(nl, xl)
        return self._crear(occ, ("plano", cl, nl), lambda cd: cd.WorkPlanes.AddFixed(
            self.tg.CreatePoint(*(cl / 10)), self.tg.CreateUnitVector(*xl), self.tg.CreateUnitVector(*yl)))

    def _crear(self, occ, clave, fabricar):
        cd = dyn(dyn(occ).Definition)
        doc = dyn(cd.Document)
        k = (doc.FullFileName, clave[0], tuple(np.round(clave[1], 3)), tuple(np.round(clave[2], 4)))
        if k not in self.cache:
            f = dyn(fabricar(cd))
            f.Visible = False
            self.cache[k] = f
        return dyn(occ).CreateGeometryProxy(self.cache[k])


def perpendicular(d):
    aux = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(d, aux)
    return u / np.linalg.norm(u)


def main():
    P = piezas()
    host = rigidas(P)
    giros = uniones_giratorias(P, host)
    raiz = next(i for i, p in enumerate(P) if p["nombre"] == "Pelvis")
    orden, sueltas = ordenar(P, host, giros, raiz)
    print(f"rigidas: {len(host)} | giratorias: {len(orden)} ({sum(u['lazo'] for u in orden)} cierran lazo) | sin conectar: {len(sueltas)}")
    for u in orden:
        print(f"  {u['tipo']:5s} {P[u['a']]['nombre']}#{u['a']} <-> {P[u['b']]['nombre']}#{u['b']}  eje {np.round(u['d'], 2)} en {np.round(u['c'], 1)}"
              f"{'  (cierra lazo)' if u['lazo'] else ''}")
    grupos = collections.defaultdict(list)
    for i in range(len(P)):
        grupos[host.get(i, i)].append(i)
    conectados = {host.get(u["a"], u["a"]) for u in orden} | {host.get(u["b"], u["b"]) for u in orden} | {raiz}
    libres = [P[g]["nombre"] + f"#{g}" for g in grupos if g not in conectados]
    print("grupos sin ninguna union:", libres)
    if "--solo-calculo" in sys.argv:
        return

    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    app.Documents.CloseAll(False)
    doc = dyn(app.Documents.Open(os.path.join(BASE, f"Torso_estudio{te.torso.SUF}.iam"), True))
    cd = dyn(doc.ComponentDefinition)
    occs = cd.Occurrences
    assert occs.Count == len(P), (occs.Count, len(P))
    occ = [dyn(occs.Item(i + 1)) for i in range(len(P))]
    for i, o in enumerate(occ):
        assert P[i]["nombre"].split("_")[0] in o.Name, (i, P[i]["nombre"], o.Name)
        o.Grounded = (i == raiz)
    ref = Referencias(app)
    rest = cd.Constraints
    errores = []

    def restringir(tipo, a, b, fabricar):
        try:
            fabricar()
        except pywintypes.com_error as e:
            errores.append(f"{tipo} {P[a]['nombre']}#{a} <-> {P[b]['nombre']}#{b}: {e.excepinfo[2] if e.excepinfo else e}")

    # rigidas: eje + plano perpendicular + plano que contiene el eje, en el origen de la pieza fija
    for i, h in host.items():
        c = P[i]["t"]
        d = np.array([0, 1.0, 0])
        u = np.array([1.0, 0, 0])
        restringir("rigida", i, h, lambda: rest.AddMateConstraint(ref.eje(occ[i], P, i, c, d), ref.eje(occ[h], P, h, c, d), 0))
        restringir("rigida", i, h, lambda: rest.AddFlushConstraint(ref.plano(occ[i], P, i, c, d), ref.plano(occ[h], P, h, c, d), 0))
        restringir("rigida", i, h, lambda: rest.AddFlushConstraint(ref.plano(occ[i], P, i, c, u), ref.plano(occ[h], P, h, c, u), 0))
    # giratorias
    for u in orden:
        a, b, c, d = u["a"], u["b"], u["c"], u["d"]
        restringir(u["tipo"], a, b, lambda: rest.AddMateConstraint(ref.eje(occ[a], P, a, c, d), ref.eje(occ[b], P, b, c, d), 0))
        if not u["lazo"]:
            restringir(u["tipo"], a, b, lambda: rest.AddFlushConstraint(ref.plano(occ[a], P, a, c, d), ref.plano(occ[b], P, b, c, d), 0))
    doc.Update()
    malas = []
    for i in range(1, rest.Count + 1):
        r = dyn(rest.Item(i))
        if r.HealthStatus != win32com.client.constants.kUpToDateHealth:
            malas.append((r.Name, r.HealthStatus))
    ruta = os.path.join(BASE, f"Robot_armado{te.torso.SUF}.iam")
    doc.SaveAs(ruta, False)
    print(f"restricciones: {rest.Count} | con problema: {len(malas)} {malas[:10]} | errores al crear: {len(errores)}")
    for e in errores[:20]:
        print("  ", e)
    print("Guardado:", ruta)


if __name__ == "__main__":
    main()
