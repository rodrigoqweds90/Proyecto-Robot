"""SEGMENTO: ESTUDIO DE ACOMODO DEL TORSO NUEVO
Arma el NX25 sin el marco del torso (Frame01) ni la cabeza vieja, con la electronica
real en su lugar propuesto, y revisa interferencias y centro de masa.
  - PCA9685: atras y abajo, componentes hacia abajo
  - ESP32 DevKit V1: atras, encima del PCA, pines hacia arriba
  - Bateria LiPo 2S 1000 mAh (62 x 23.35 x 16.68 mm medida, 70 g): adelante y abajo, parada
  - Reductor XL4015 (52.3 x 23.5 x 12 mm con disipador, medido, ~20 g): acostado sobre la repisa de la bateria, asoma adelante
Ejes del mundo: X izquierda del robot, Y arriba, Z adelante. Medidas en mm.
"""
import os
import sys

import numpy as np
import pythoncom
import pywintypes
import win32com.client
from win32com.client import dynamic, gencache

BASE = os.path.dirname(os.path.abspath(__file__))
CAD = os.path.dirname(BASE)
sys.path.insert(0, os.path.join(CAD, "NX25_original"))
import armar_nx25 as nx  # noqa: E402
import torso  # noqa: E402

X, Y, Z = nx.X, nx.Y, nx.Z
COMP = os.path.join(CAD, "Componentes")
PCA = os.path.join(COMP, "PCA9685_adafruit_815.iam")
ESP32 = os.path.join(COMP, "ESP32_devkit_v1_30pin.iam")
BATERIA = os.path.join(COMP, "Bateria_LiPo_2S_1000_62x23x17.ipt")
XL4015 = os.path.join(COMP, "XL4015_52x12x24_acostado.ipt")
TORSO = [os.path.join(BASE, "Torso_cuerpo" + torso.SUF + ".ipt")]
PELVIS = os.path.join(BASE, "Pelvis.ipt")
CABEZA = [os.path.join(BASE, n + ".ipt") for n in ("Cabeza_frente", "Cabeza_tapa")]
PIPE = os.path.join(BASE, "piezas_m3", "Pipe_M3.ipt")
# proxies solidos (BRep, caja envolvente real) de las piezas que son malla: Inventor no calcula interferencia
# contra mallas, asi que estos son los que entran en AnalyzeInterference. Solo se usan en este ensamble de
# verificacion, nunca en el visual/armado (uniones.py)
PROXY_PCA = os.path.join(BASE, "proxies", "Proxy_PCA9685.ipt")
PROXY_ESP32 = os.path.join(BASE, "proxies", "Proxy_ESP32.ipt")
PROXY_MG90S = os.path.join(BASE, "proxies", "Proxy_MG90S.ipt")
PROXIES = "--proxies" in sys.argv
PIPE_HOSTS = []                 # (indice del pipe, indice de la pieza que lo sujeta) del ultimo ensamble()
CARCASAS = [os.path.join(BASE, n + ".ipt") for n in (("Torso_pecho", "Torso_espalda") if torso.VARIANTE == "A" else ("Torso_pecho", "Torso_atras_B"))]
TORRE_ARRIBA_SERVO = 28.5   # tope de la torre del MG90S en sus coordenadas (el eje asoma 3 mm mas)
COLLAR_HORN = 2.8          # collar del horn de 1 brazo, apoyado en la torre, bajo el brazo
CORRIMIENTO_BRAZOS = torso.X_EXT - 30.0   # la pared del torso pasa de x 30 a x 34

# --- ubicaciones propuestas ---
Y_PCA = 17.5          # placa del PCA: componentes de 7.4 a 17.5, soldaduras hasta 19.5
Z_PCA = torso.PCA_Z
Y_ESP32 = torso.ESP_Y_PLACA[0]        # componentes abajo hasta y - 3.25, pines arriba hasta y + 10.2
Z_ESP32 = sum(torso.ESP_Z) / 2
CAJAS = {  # nombre: (ruta, tamano x,y,z, esquina minima en el mundo)
    "bateria": (BATERIA, (62.0, 23.35, 16.68), (torso.BAT[0], torso.BAT[2], torso.BAT[4])),
    "xl4015": (XL4015, torso.XL4015, torso.XL4015_ESQUINA),
    # fichas Dupont enchufadas (solo para revisar espacio): las de los 16 servos cuelgan del PCA,
    # las del ESP32 van sobre las dos filas de pines, con 5 mm extra para doblar el cable
    "fichas_servos": (os.path.join(COMP, "Fichas_servos_PCA.ipt"), (50.8, 14.0, 7.6), (-25.4, -6.5, -26.0)),
    "fichas_esp_atras": (os.path.join(COMP, "Fichas_pines_ESP32.ipt"), (38.2, 19.5, 2.6),
                         (-19.1, torso.ESP_Y_PLACA[1] + 2.5, torso.ESP_Z[0])),
    "fichas_esp_frente": (os.path.join(COMP, "Fichas_pines_ESP32.ipt"), (38.2, 19.5, 2.6),
                          (-19.1, torso.ESP_Y_PLACA[1] + 2.5, torso.ESP_Z[1] - 2.6)),
    # (en la variante B las fichas de la PCA y del ESP32 salen hacia atras: ver CAJAS_B)
    # giroscopio MPU6050 (GY-521): placa con componentes (3 mm) y fichas Dupont en su tira de pines (mira arriba)
    "imu": (os.path.join(COMP, "IMU_GY521_21x16.ipt"), (21.2, 3.0, 16.4),
            (torso.IMU_PLACA[0], torso.IMU_Y, torso.IMU_PLACA[2])),
    "fichas_imu": (os.path.join(COMP, "Fichas_pines_IMU.ipt"), (20.3, 22.5, 2.6),
                   (torso.IMU_PLACA[0] + 0.45, torso.IMU_Y + 1.6, torso.IMU_PLACA[2] + 0.3)),
}
if torso.VARIANTE != "A":
    for k in ("fichas_servos", "fichas_esp_atras", "fichas_esp_frente"):
        CAJAS.pop(k)
    # ESP32 acostado: sus 2 filas de pines miran hacia ARRIBA, asi que las fichas Dupont suben desde la placa
    _esp_filas_z = (torso.ESP_RECTO_CAJA[4] + 3.0, torso.ESP_RECTO_CAJA[5] - 3.0)   # filas de pines (en z)
    CAJAS.update({
        # fichas de 14 mm apoyadas en el plastico de los pines (cubren los pines)
        "fichas_servos": (os.path.join(COMP, "Fichas_servos_PCA_atras.ipt"), (50.8, 7.6, torso.FICHA_LARGO),
                          (-25.4, torso.PCA_B_T[1] - 6.3, torso.FICHAS_B_Z["pca"] - torso.FICHA_LARGO)),
        "fichas_esp_abajo": (os.path.join(COMP, "Fichas_pines_ESP32_atras14.ipt"), (38.2, torso.FICHA_LARGO, 2.6),
                             (-19.1, torso.ESP_RECTO_CAJA[3], _esp_filas_z[0] - 1.3)),
        "fichas_esp_arriba": (os.path.join(COMP, "Fichas_pines_ESP32_atras14.ipt"), (38.2, torso.FICHA_LARGO, 2.6),
                              (-19.1, torso.ESP_RECTO_CAJA[3], _esp_filas_z[1] - 1.3)),
    })
MASAS_FIJAS = {"Fichas": 0.0, "MG90S": 13.4, "PCA9685": 9.0, "ESP32": 10.0, "Bateria": 70.0, "XL4015": 20.0, "IMU": 2.0}
DENSIDAD_IMPRESO = 1.24 * 0.75   # g/cm3: PLA con paredes y relleno
# --aligerado: usa las piezas aligeradas verificadas (piezas_aligeradas/*.ipt, STL en para_imprimir)
ALIGERADO = "--aligerado" in sys.argv
ALIGERADAS = os.path.join(BASE, "piezas_aligeradas")


def dyn(o):
    return dynamic.Dispatch(o._oleobj_) if hasattr(o, "_oleobj_") else o


def ensamble():
    piezas = [("Bracket06_W", [-X, Y, -Z], [0.0, 0.0, 0.0])]
    piezas += nx.pierna(+1) + nx.pierna(-1) + nx.torso()
    todo = piezas + nx.servos(piezas)          # sin Pipe_B: cada union lleva un tornillo M3 como eje
    if os.path.exists(PELVIS):                 # pelvis nueva, modelada en coordenadas del robot
        todo = [p for p in todo if p[0] != "Bracket06_W"] + [(PELVIS, [X, Y, Z], [0.0, 0.0, 0.0])]
    # fuera el marco viejo, la cabeza vieja, el PCA en su lugar viejo y los servos de hombro (se corren)
    hombros = nx.servos([p for p in piezas if p[0] == "Frame01_W"])[2:]
    todo = [p for p in todo if p[0] not in ("Frame01_W", "Head_W", nx.PCA9685) 
            and not any(np.allclose(p[2], h[2]) for h in hombros)]
    brazos = nx.brazos()
    for nombre, ejes, t in hombros + brazos + nx.servos(brazos):
        todo.append((nombre, ejes, [t[0] + np.sign(t[0]) * CORRIMIENTO_BRAZOS, t[1], t[2]]))
    if torso.VARIANTE == "A":
        todo.append((PCA, [X, Z, -Y], [-29.21, Y_PCA, -17.8 + (Z_PCA + 11.6)]))
        todo.append((ESP32, [Z, -X, -Y], [23.37, Y_ESP32, Z_ESP32 - 12.07]))
    else:   # parados contra la pared de atras, pines hacia atras
        todo.append((PCA, [-X, Y, -Z], list(torso.PCA_B_T)))
        todo.append((ESP32, [list(c) for c in torso.ESP_RECTO_EJES], list(torso.ESP_RECTO_T)))   # recto, horizontal hacia atras
    for ruta, _, esquina in CAJAS.values():
        todo.append((ruta, [X, Y, Z], list(esquina)))
    if PROXIES:
        # un proxy solido por cada MG90S real, con el mismo eje/traslacion, mas uno por el PCA y el ESP32
        for nombre, ejes, t in list(todo):
            if os.path.basename(nombre) == "MG90S_grabcad_mg90s9.ipt":
                todo.append((PROXY_MG90S, ejes, t))
        pca_i = next(i for i, p in enumerate(todo) if p[0] == PCA)
        esp_i = next(i for i, p in enumerate(todo) if p[0] == ESP32)
        todo.append((PROXY_PCA, todo[pca_i][1], todo[pca_i][2]))
        todo.append((PROXY_ESP32, todo[esp_i][1], todo[esp_i][2]))
    for ruta in TORSO:
        if os.path.exists(ruta):
            todo.append((ruta, [X, Y, Z], [0.0, 0.0, 0.0]))
    for ruta in CARCASAS:
        if os.path.exists(ruta):
            todo.append((ruta, [X, Y, Z], [0.0, 0.0, 0.0]))
    if all(os.path.exists(r) for r in CABEZA):
        todo += cabeza()
    if os.path.exists(PIPE):
        todo += pipes(todo)
    return todo


def pipes(todo):
    """Pipe_M3 de cada union (piezas_m3/pipes_m3.json, en coordenadas de la pieza que sujeta).
    La pieza se busca por nombre y orientacion; los brazos estan corridos en x respecto del NX25."""
    import json
    PIPE_HOSTS.clear()
    salida = []
    for p in json.load(open(os.path.join(BASE, "piezas_m3", "pipes_m3.json"), encoding="utf-8")):
        e_nx = np.column_stack(p["agarra_ejes_nx"])
        t_nx = np.asarray(p["agarra_t_nx"], float)
        host = None
        for j, (n, e, t) in enumerate(todo):
            if n != p["agarra"] or not np.allclose(np.column_stack([np.asarray(x, float) for x in e]), e_nx, atol=1e-6):
                continue
            dx = np.asarray(t, float) - t_nx
            if np.allclose(dx, 0, atol=0.01) or (np.allclose(dx[1:], 0, atol=0.01) and abs(abs(dx[0]) - CORRIMIENTO_BRAZOS) < 0.01):
                host = j
        if host is None:
            print("pipe sin pieza que lo sujete:", p["agarra"], p["gira"])
            continue
        M = np.column_stack([np.asarray(x, float) for x in todo[host][1]])
        o = M @ np.asarray(p["origen"], float) + np.asarray(todo[host][2], float)
        d = M @ np.asarray(p["eje"], float)
        aux = X if abs(d[0]) < 0.9 else Y
        xl = np.cross(aux, d)
        xl /= np.linalg.norm(xl)
        PIPE_HOSTS.append((len(todo) + len(salida), host))
        ruta = PIPE.replace("Pipe_M3.ipt", "Pipe_M3_alto.ipt") if p.get("tipo") == "alto" else PIPE
        salida.append((ruta, [xl, d, np.cross(xl, d)], list(o)))
    return salida


def cabeza():
    """Cabeza sobre el servo de cuello: el piso apoya en el brazo del horn (collar sobre la torre)."""
    import cabeza as cb
    marco = [p for p in nx.torso() if p[0] == "Frame01_W"]
    xs, ys, _ = next(e for _, e, _ in nx.servos(marco) if e[1][1] > 0.99)
    o = next(t for _, e, t in nx.servos(marco) if e[1][1] > 0.99)
    eje = np.asarray(o, float) + np.asarray(xs, float) * -5.5
    origen = eje + Y * (TORRE_ARRIBA_SERVO + COLLAR_HORN + cb.ALTO)
    return [(r, [X, Y, Z], list(origen)) for r in CABEZA]


def crear_caja(app, k, ruta, tam):
    if os.path.exists(ruta):
        return
    tg = app.TransientGeometry
    doc = dyn(app.Documents.Add(k.kPartDocumentObject, app.FileManager.GetTemplateFile(k.kPartDocumentObject, k.kMetricSystemOfMeasure), True))
    cd = doc.ComponentDefinition
    sk = cd.Sketches.Add(cd.WorkPlanes.Item(3))
    sk.SketchLines.AddAsTwoPointRectangle(tg.CreatePoint2d(0, 0), tg.CreatePoint2d(tam[0] / 10, tam[1] / 10))
    cd.Features.ExtrudeFeatures.AddByDistanceExtent(sk.Profiles.AddForSolid(), tam[2] / 10,
                                                   k.kPositiveExtentDirection, k.kJoinOperation)
    doc.SaveAs(ruta, False)
    doc.Close(True)


def leer_stl(ruta):
    with open(ruta, "rb") as f:
        f.seek(80)
        n = int(np.frombuffer(f.read(4), "<u4")[0])
        d = np.frombuffer(f.read(n * 50), dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), count=n)
    return d["v"].astype(float)


def volumen_y_centroide(tris):
    """Teorema de la divergencia sobre la malla cerrada (mm3, mm)."""
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    v6 = np.einsum("ij,ij->i", a, np.cross(b, c))
    vol = v6.sum() / 6
    centro = ((a + b + c) * v6[:, None]).sum(0) / (24 * vol)
    return abs(vol), centro


# masa (g) y centro (mm) de las piezas nuevas del torso, medidos en Inventor por torso.py
def masas_torso():
    import json
    with open(os.path.join(BASE, f"torso_masas{torso.SUF}.json"), encoding="utf-8") as f:
        return {k: (m, np.array(c)) for k, (m, c) in json.load(f).items()}


# centro aproximado de cada componente comprado, en sus coordenadas locales
CENTRO_LOCAL = {"MG90S": (0.0, 12.0, 0.0), "PCA9685": (29.2, -6.2, -4.0), "ESP32": (12.07, 22.83, -3.5)}


def centro_de_masa():
    cache, total, momento, pies, plastico = {}, 0.0, np.zeros(3), [], 0.0
    for nombre, ejes, t in ensamble():
        m_rot = np.column_stack([np.asarray(e, float) for e in ejes])
        t = np.asarray(t, float)
        base = os.path.basename(nombre)
        stl_aligerada = os.path.join(BASE, "para_imprimir", os.path.splitext(base)[0] + ".stl")
        if ALIGERADO and os.path.exists(os.path.join(ALIGERADAS, os.path.splitext(base)[0] + ".ipt")):
            vol, c = volumen_y_centroide(leer_stl(stl_aligerada))
            masa, centro = vol / 1000 * DENSIDAD_IMPRESO, m_rot @ c + t
            plastico += masa
            if base in ("Bracket04_B", "Bracket05_B"):
                tris = leer_stl(stl_aligerada).reshape(-1, 3) @ m_rot.T + t
                pies.append((tris[:, 2].min(), tris[:, 2].max()))
            total += masa
            momento += masa * centro
            continue
        fija = None if base.startswith(("Torso_", "Pelvis")) else next((m for clave, m in MASAS_FIJAS.items() if clave.lower() in base.lower()), None)
        if fija is not None:
            if base.startswith(("Bateria", "XL4015", "Fichas", "IMU")):
                tam = next(tm for r, tm, _ in CAJAS.values() if os.path.basename(r) == base)
                local = np.asarray(tam) / 2
            else:
                local = np.asarray(next(c for clave, c in CENTRO_LOCAL.items() if clave.lower() in base.lower()))
            masa, centro = fija, m_rot @ local + t
        elif base in masas_torso():
            masa, centro = masas_torso()[base]
            plastico += masa
        elif base.startswith("Pipe_M3"):
            vol, c = volumen_y_centroide(leer_stl(os.path.join(BASE, "piezas_m3", base.replace(".ipt", ".stl"))))
            masa, centro = vol / 1000 * DENSIDAD_IMPRESO, m_rot @ c + t
            plastico += masa
        elif base.startswith(("Cabeza", "Torso_pecho", "Torso_espalda", "Torso_atras")):
            vol, c = volumen_y_centroide(leer_stl(os.path.join(BASE, "stl", base.replace(".ipt", ".stl"))))
            masa, centro = vol / 1000 * DENSIDAD_IMPRESO, m_rot @ c + t
            plastico += masa
        elif base == "Pelvis.ipt":
            import json
            masa, centro = json.load(open(os.path.join(BASE, "pelvis_masa.json"), encoding="utf-8"))
            centro = np.array(centro)
            plastico += masa
        else:
            if nombre not in cache:
                nuevo = os.path.join(BASE, "piezas_rediseno", nombre + ".stl")
                cache[nombre] = volumen_y_centroide(leer_stl(nuevo if os.path.exists(nuevo) else os.path.join(nx.BASE, "stl", nombre + ".stl")))
            vol, c = cache[nombre]
            masa, centro = vol / 1000 * DENSIDAD_IMPRESO, m_rot @ c + t
            plastico += masa
            if nombre in ("Bracket04_B", "Bracket05_B"):
                tris = leer_stl(os.path.join(nx.BASE, "stl", nombre + ".stl")).reshape(-1, 3) @ m_rot.T + t
                pies.append((tris[:, 2].min(), tris[:, 2].max()))
        total += masa
        momento += masa * centro
    return total, plastico, momento / total, (min(p[0] for p in pies) + max(p[1] for p in pies)) / 2


def main():
    app = dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))
    gencache.GetModuleForProgID("Inventor.Application")
    k = win32com.client.constants
    tg = app.TransientGeometry
    for ruta, tam, _ in CAJAS.values():
        crear_caja(app, k, ruta, tam)

    ruta_iam = os.path.join(BASE, "Robot_aligerado.iam" if ALIGERADO else f"Torso_estudio{torso.SUF}.iam")
    for i in range(app.Documents.Count, 0, -1):
        d = dyn(app.Documents.Item(i))
        if os.path.normcase(d.FullFileName) == os.path.normcase(ruta_iam):
            d.Close(True)
    doc = dyn(app.Documents.Add(k.kAssemblyDocumentObject, app.FileManager.GetTemplateFile(k.kAssemblyDocumentObject, k.kMetricSystemOfMeasure), True))
    cd = doc.ComponentDefinition
    occs = cd.Occurrences
    for nombre, ejes, t in ensamble():
        xl, yl, zl = (np.asarray(e, float) for e in ejes)
        m = np.column_stack([xl, yl, zl])
        assert np.allclose(m.T @ m, np.eye(3), atol=1e-6) and np.isclose(np.linalg.det(m), 1.0), nombre
        mat = tg.CreateMatrix()
        mat.SetCoordinateSystem(tg.CreatePoint(t[0] / 10, t[1] / 10, t[2] / 10),
                                tg.CreateVector(*xl), tg.CreateVector(*yl), tg.CreateVector(*zl))
        ruta = nombre if os.path.isabs(nombre) else os.path.join(nx.BASE, nombre + ".ipt")
        # pieza con salida de cable y pasos de brida, si existe
        con_brida = os.path.join(BASE, "piezas_canales", os.path.basename(ruta).replace(".ipt", "_brida.ipt"))
        con_m3 = os.path.join(BASE, "piezas_m3", os.path.basename(ruta))
        aligerada = os.path.join(ALIGERADAS, os.path.basename(ruta))
        # prioridad: aligerada (si se pide) > pernos M3 (ya incluye cables) > pasos de cable > original
        estilo = os.path.join(BASE, "piezas_estilo", os.path.basename(ruta))
        if ALIGERADO and os.path.exists(aligerada):
            occs.Add(aligerada, mat)
        elif os.path.exists(estilo):
            occs.Add(estilo, mat)                                                            # estilo 1 facetado
        elif os.path.exists(os.path.join(BASE, "piezas_rediseno", os.path.basename(ruta))):
            occs.Add(os.path.join(BASE, "piezas_rediseno", os.path.basename(ruta)), mat)    # piezas con forma nueva (mano)
        else:
            occs.Add(con_m3 if os.path.exists(con_m3) else (con_brida if os.path.exists(con_brida) else ruta), mat)
    doc.SaveAs(ruta_iam, False)

    # --- rangos de la electronica ---
    electronica = app.TransientObjects.CreateObjectCollection()
    resto = app.TransientObjects.CreateObjectCollection()
    for i in range(1, occs.Count + 1):
        o = dyn(occs.Item(i))
        # con --proxies, el proxy solido reemplaza a su malla real en el chequeo (si no, se solapan consigo
        # mismas: 100% del proxy cae dentro de su propia malla, puro ruido, no un choque real)
        if PROXIES and o.Name.startswith(("PCA9685", "ESP32_devkit", "MG90S")):
            continue
        es_elec = any(s in o.Name for s in ("PCA9685", "ESP32", "Bateria", "XL4015", "Torso_", "Fichas", "Pelvis", "IMU", "Proxy_"))
        (electronica if es_elec else resto).Add(o)
        if es_elec or "Bracket06" in o.Name or "Spacer01" in o.Name or "MG90S" in o.Name:
            r = o.RangeBox
            mn = [round(getattr(r.MinPoint, a) * 10, 1) for a in "XYZ"]
            mx = [round(getattr(r.MaxPoint, a) * 10, 1) for a in "XYZ"]
            if mx[1] > -10:
                print(f"{o.Name:34s} min {mn} max {mx}")

    # --- interferencias: electronica contra el robot y entre si ---
    checks = [("torso y electronica vs robot", lambda: cd.AnalyzeInterference(electronica, resto)),
              ("entre torso y electronica", lambda: cd.AnalyzeInterference(electronica))]
    if PROXIES:
        # chequeo aparte, solo con solidos BRep de verdad (proxies + torso + tapas): Bateria/XL4015/Fichas/IMU
        # siguen siendo malla y hacen fallar el chequeo de arriba entero si se mezclan con ellas
        solidos = app.TransientObjects.CreateObjectCollection()
        for i in range(1, occs.Count + 1):
            o = dyn(occs.Item(i))
            if o.Name.startswith(("Proxy_", "Torso_")):
                solidos.Add(o)
        checks.append(("proxies (PCA/ESP32/servos) vs torso", lambda: cd.AnalyzeInterference(solidos)))
    for titulo, analisis in checks:
        if ALIGERADO:
            print(f"\nInterferencias {titulo}: no se calculan con piezas de malla")
            continue
        try:
            res = analisis()
        except Exception:   # alguna pieza es malla (piezas_estilo): la revisan barrido_movimiento / verificar_*
            print(f"\nInterferencias {titulo}: Inventor no las calcula con piezas de malla (ver barrido_movimiento.py)")
            continue
        print(f"\nInterferencias {titulo}: {res.Count}")
        for i in range(1, res.Count + 1):
            it = dyn(res.Item(i))
            print("  ", dyn(it.OccurrenceOne).Name, "<->", dyn(it.OccurrenceTwo).Name, round(it.Volume * 1000, 1), "mm3")

    v = app.ActiveView
    for nombre, ojo, mira, ancho in (("costado", (300.0, 30.0, 10.0), (0.0, 25.0, 10.0), 130.0),
                                     ("tresc_atras", (-160.0, 150.0, -200.0), (0.0, 25.0, 10.0), 150.0),
                                     ("tresc_frente", (170.0, 120.0, 230.0), (0.0, 25.0, 10.0), 150.0)):
        cam = v.Camera
        cam.Eye = tg.CreatePoint(ojo[0] / 10, ojo[1] / 10, ojo[2] / 10)
        cam.Target = tg.CreatePoint(mira[0] / 10, mira[1] / 10, mira[2] / 10)
        cam.UpVector = tg.CreateUnitVector(0, 1, 0)
        cam.SetExtents(ancho / 10, ancho / 10)
        cam.Apply()
        v.SaveAsBitmap(os.path.join(BASE, "vistas_torso", nombre + ("_aligerado" if ALIGERADO else "") + torso.SUF + ".png"), 800, 800)
    print("Guardado:", ruta_iam, "| piezas:", occs.Count)


def informe_masa():
    total, plastico, com, apoyo = centro_de_masa()
    print(f"Masa sin carcasa del torso: {total:.0f} g (plastico {plastico:.0f} g) | centro de masa (x,y,z): {np.round(com, 1)} mm")
    print(f"Centro del pie en Z: {apoyo:.1f} mm | diferencia: {com[2] - apoyo:+.1f} mm")


if __name__ == "__main__":
    if "--masa" not in sys.argv:
        main()
    informe_masa()
