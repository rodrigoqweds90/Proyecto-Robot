"""SEGMENTO: CONTROL DE LA INTERFAZ DE INVENTOR (sin API para Analisis de tension / Generador de forma)
Usa UI Automation (pywinauto) sobre los dialogos de Inventor, sin traer la ventana al frente
cuando se puede, y la API COM de Inventor para comandos y seleccion de caras.
"""
import time

import pythoncom
import pywintypes
from pywinauto import Application
from win32com.client import dynamic


def d(o):
    return dynamic.Dispatch(o._oleobj_)


def inventor_com():
    return dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID("Inventor.Application")).QueryInterface(pythoncom.IID_IDispatch))


def ventana():
    app = Application(backend="uia").connect(title_re="Autodesk Inventor Professional 2027.*", timeout=10)
    return app.window(title_re="Autodesk Inventor Professional 2027.*")


def dialogos():
    return [(w.window_text(), w) for w in ventana().descendants(control_type="Window") if w.element_info.class_name == "#32770"]


def esperar_dialogo(titulo=None, timeout=20):
    fin = time.time() + timeout
    while time.time() < fin:
        for t, w in dialogos():
            if titulo is None or titulo.lower() in t.lower():
                return w
        time.sleep(0.5)
    return None


def campos(dlg):
    salida = []
    for c in dlg.descendants():
        ei = c.element_info
        try:
            val = c.get_value()
        except Exception:
            val = ""
        salida.append((ei.control_type, c.window_text(), ei.automation_id, val))
    return salida


def imprimir_campos(dlg):
    for tipo, texto, aid, val in campos(dlg):
        print(f"{tipo:12s} | {repr(texto)[:50]:52s} | id={aid} | {val}")


def boton(dlg, texto):
    for c in dlg.descendants(control_type="Button"):
        if c.window_text().replace("&", "").lower() == texto.lower():
            if not c.is_enabled():
                return False
            c.invoke()
            return True
    return False


def marcar(dlg, texto, valor=True):
    for c in dlg.descendants(control_type="CheckBox"):
        if c.window_text().replace("&", "").lower() == texto.lower():
            if bool(c.get_toggle_state()) != valor:
                c.toggle()
            return True
    return False


def ejecutar(app_com, nombre, espera=2.0):
    cmd = d(app_com.CommandManager.ControlDefinitions.Item(nombre))
    cmd.Execute2(False)
    time.sleep(espera)


def captura_inventor(ruta):
    """Captura solo la ventana de Inventor, aunque este detras de otras (PrintWindow)."""
    import ctypes
    import win32gui
    import win32ui
    from PIL import Image
    hwnd = ventana().handle
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    w, h = r - l, b - t
    hdc = win32gui.GetWindowDC(hwnd)
    mfc = win32ui.CreateDCFromHandle(hdc)
    save = mfc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc, w, h)
    save.SelectObject(bmp)
    ctypes.windll.user32.PrintWindow(hwnd, save.GetSafeHdc(), 2)
    info = bmp.GetInfo()
    img = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1)
    win32gui.DeleteObject(bmp.GetHandle()); save.DeleteDC(); mfc.DeleteDC(); win32gui.ReleaseDC(hwnd, hdc)
    img.save(ruta)
    return img


def caras_cilindro(cuerpo, k, centro_xy=None, radio=None, eje=None, tol=0.3, extra=None):
    """Caras cilindricas del cuerpo (mm) con radio y eje dados; centro_xy: (a, b) en el plano perpendicular al eje."""
    import numpy as np
    salida = []
    for i in range(1, cuerpo.Faces.Count + 1):
        f = d(cuerpo.Faces.Item(i))
        if f.SurfaceType != k.kCylinderSurface:
            continue
        g = f.Geometry
        r = g.Radius * 10
        a = np.array([g.AxisVector.X, g.AxisVector.Y, g.AxisVector.Z])
        p = np.array([g.BasePoint.X, g.BasePoint.Y, g.BasePoint.Z]) * 10
        if radio is not None and abs(r - radio) > tol:
            continue
        if eje is not None and abs(abs(a @ np.asarray(eje, float)) - 1) > 1e-3:
            continue
        if centro_xy is not None:
            e = np.asarray(eje, float)
            q = p - (p @ e) * e
            c = np.zeros(3)
            idx = [i for i in range(3) if abs(e[i]) < 0.5]
            c[idx[0]], c[idx[1]] = centro_xy
            if np.linalg.norm(q - c) > tol:
                continue
        if extra is not None and not extra(f):
            continue
        salida.append(f)
    return salida


def caras_plano(cuerpo, k, normal, distancia, tol=0.05, extra=None):
    import numpy as np
    salida = []
    for i in range(1, cuerpo.Faces.Count + 1):
        f = d(cuerpo.Faces.Item(i))
        if f.SurfaceType != k.kPlaneSurface:
            continue
        g = f.Geometry
        n = np.array([g.Normal.X, g.Normal.Y, g.Normal.Z])
        p = np.array([g.RootPoint.X, g.RootPoint.Y, g.RootPoint.Z]) * 10
        if abs(n @ np.asarray(normal, float) - 1) > 1e-3 or abs(p @ n - distancia) > tol:
            continue
        if extra is not None and not extra(f):
            continue
        salida.append(f)
    return salida


def seleccionar(app_com, caras):
    doc = d(app_com.ActiveDocument)
    ss = doc.SelectSet
    ss.Clear()
    for f in caras:
        ss.Select(f)
    return ss.Count


def arbol(app_com, max_nivel=4):
    """Nodos del navegador de modelo (ahi aparece el estudio con sus restricciones y cargas)."""
    doc = d(app_com.ActiveDocument)
    salida = []

    def recorrer(nodo, nivel):
        try:
            nombre = d(nodo.BrowserNodeDefinition).Label
        except Exception:
            nombre = "?"
        salida.append("  " * nivel + nombre)
        if nivel < max_nivel:
            for i in range(1, nodo.BrowserNodes.Count + 1):
                recorrer(d(nodo.BrowserNodes.Item(i)), nivel + 1)

    for i in range(1, doc.BrowserPanes.Count + 1):
        panel = d(doc.BrowserPanes.Item(i))
        salida.append(f"[panel] {panel.Name} ({panel.InternalName})")
        try:
            recorrer(d(panel.TopNode), 1)
        except Exception as e:
            salida.append(f"  sin nodos: {e}")
    return salida


# ---------------------------------------------------------------------------
# SEGMENTO: CLICS SOBRE CARAS EN LA VISTA 3D
# Camara ortografica mirando la cara de frente; el punto del modelo se proyecta a pixeles
# de la ventana de la vista y se hace clic ahi.
# ---------------------------------------------------------------------------
def al_frente():
    import win32con
    import win32gui
    import win32com.client as w32
    hwnd = ventana().handle
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    w32.Dispatch("WScript.Shell").SendKeys("%")          # permite SetForegroundWindow
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(1.0)


def mirar(app_com, direccion, objetivo_mm, ancho_mm):
    """Camara ortografica mirando en 'direccion' (vector de la vista hacia el modelo) al punto objetivo."""
    import numpy as np
    tg = app_com.TransientGeometry
    v = d(app_com.ActiveView)
    cam = d(v.Camera)
    dirv = np.asarray(direccion, float) / np.linalg.norm(direccion)
    obj = np.asarray(objetivo_mm, float) / 10
    ojo = obj - dirv * 20
    arriba = np.array([0, 1.0, 0]) if abs(dirv[1]) < 0.9 else np.array([0, 0, -1.0 if dirv[1] < 0 else 1.0])
    cam.Perspective = False
    cam.Eye = tg.CreatePoint(*ojo)
    cam.Target = tg.CreatePoint(*obj)
    cam.UpVector = tg.CreateUnitVector(*arriba)
    cam.SetExtents(ancho_mm / 10, ancho_mm / 10)
    cam.Apply()
    time.sleep(0.8)


def a_pantalla(app_com, punto_mm):
    import numpy as np
    import win32gui
    v = d(app_com.ActiveView)
    cam = d(v.Camera)
    ojo = np.array([cam.Eye.X, cam.Eye.Y, cam.Eye.Z])
    obj = np.array([cam.Target.X, cam.Target.Y, cam.Target.Z])
    up = np.array([cam.UpVector.X, cam.UpVector.Y, cam.UpVector.Z])
    fwd = (obj - ojo) / np.linalg.norm(obj - ojo)
    der = np.cross(fwd, up); der /= np.linalg.norm(der)
    up = np.cross(der, fwd)
    ancho, alto = cam.GetExtents()
    hwnd = v.HWND
    l, t, r, b = win32gui.GetClientRect(hwnd)
    w, h = r - l, b - t
    # Inventor ajusta la extension al aspecto de la ventana: la dimension que sobra se amplia
    escala = max(ancho / w, alto / h)
    p = np.asarray(punto_mm, float) / 10 - obj
    x = w / 2 + (p @ der) / escala
    y = h / 2 - (p @ up) / escala
    sx, sy = win32gui.ClientToScreen(hwnd, (int(round(x)), int(round(y))))
    return sx, sy


def clic_modelo(app_com, punto_mm):
    from pywinauto import mouse
    x, y = a_pantalla(app_com, punto_mm)
    mouse.click(button="left", coords=(x, y))
    time.sleep(0.6)
    return x, y


def escribir(dlg, automation_id, texto):
    """Escribe un valor en un campo y lo confirma con Tab (Inventor valida al salir del campo)."""
    for c in dlg.descendants(control_type="Edit"):
        if c.element_info.automation_id == str(automation_id):
            c.set_focus()
            c.type_keys("^a{BACKSPACE}" + texto.replace(" ", "{SPACE}") + "{TAB}", pause=0.02)
            time.sleep(0.4)
            return c.get_value()
    return None


def region_conservada(app_com, vista, clic_mm, centro_mm, tam_mm, dlg=None):
    """Conservar region: clic en una cara (vista = (direccion, objetivo, ancho)), luego caja por tamano y centro."""
    if dlg is None:
        ejecutar(app_com, "GddCreatePreservedRegionConstraintCmd", 2.5)
        dlg = esperar_dialogo("Conservar región", 5)
    mirar(app_com, *vista)
    clic_modelo(app_com, clic_mm)
    time.sleep(1)
    # al elegir una cara la caja pasa a "Alineado" (ejes de la cara): volver a ejes del robot
    for cb in dlg.descendants(control_type="ComboBox"):
        if cb.element_info.automation_id == "10259":
            cb.select("XYZ globales")
            time.sleep(0.8)
    boton(dlg, "Tamaño")
    time.sleep(0.8)
    for aid, v in zip((10212, 10213, 10214), tam_mm):
        escribir(dlg, aid, f"{v / 10:.3f} cm")
    for aid, v in zip((1216, 1215, 1220), centro_mm):
        escribir(dlg, aid, f"{v / 10:.3f} cm")
    ok = boton(dlg, "Aceptar")
    time.sleep(1.5)
    return ok


def nodo(app_com, etiqueta):
    doc = d(app_com.ActiveDocument)
    encontrado = []

    def recorrer(n):
        try:
            if d(n.BrowserNodeDefinition).Label == etiqueta:
                encontrado.append(n)
                return
        except Exception:
            pass
        for i in range(1, n.BrowserNodes.Count + 1):
            if encontrado:
                return
            recorrer(d(n.BrowserNodes.Item(i)))

    for i in range(1, doc.BrowserPanes.Count + 1):
        try:
            recorrer(d(d(doc.BrowserPanes.Item(i)).TopNode))
        except Exception:
            pass
        if encontrado:
            return encontrado[0]
    return None


def editar_region(app_com, etiqueta, centro_mm, tam_mm):
    n = nodo(app_com, etiqueta)
    d(app_com.ActiveDocument).SelectSet.Clear()
    n.DoSelect()
    time.sleep(0.5)
    ejecutar(app_com, "GddEditConstrPreservedRegionCmd", 2.0)
    dlg = esperar_dialogo("Conservar región", 5) or esperar_dialogo(None, 3)
    boton(dlg, "Tamaño")
    time.sleep(0.6)
    # tamano: 10212 = X, 10213 = Z, 10214 = Y (verificado en pantalla)
    for aid, v in zip((10212, 10214, 10213), tam_mm):
        escribir(dlg, aid, f"{v / 10:.3f} cm")
    for aid, v in zip((1216, 1215, 1220), centro_mm):
        escribir(dlg, aid, f"{v / 10:.3f} cm")
    ok = boton(dlg, "Aceptar")
    time.sleep(1.5)
    return ok



def restriccion_fija(app_com, vista, clics_mm):
    ejecutar(app_com, "FeaCreateConstrFixedCmd", 2.5)
    dlg = esperar_dialogo("Restricción fija", 5)
    mirar(app_com, *vista)
    for p in clics_mm:
        clic_modelo(app_com, p)
    return boton(dlg, "Aceptar")


def carga(app_com, comando, titulo, vista, clics_mm, vector, unidad):
    ejecutar(app_com, comando, 2.5)
    dlg = esperar_dialogo(titulo, 5)
    mirar(app_com, *vista)
    for p in clics_mm:
        clic_modelo(app_com, p)
    marcar(dlg, "Usar componentes de vector", True)
    time.sleep(0.8)
    for aid, v in zip((1216, 1215, 1220), vector):
        escribir(dlg, aid, f"{v} {unidad}")
    ok = boton(dlg, "Aceptar")
    time.sleep(1.5)
    return ok
