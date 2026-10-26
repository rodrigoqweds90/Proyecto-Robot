"""SEGMENTO: VISOR DEL SIMULADOR (ventana para ver las secuencias de la app sin mover el robot)
Elige una secuencia (o una pose suelta) de la carpeta de datos de la app y la reproduce con el simulador estatico
(simular_caminata.py): de frente, de costado y desde arriba (huellas), con el centro de masa, que pie apoya, cuanto
se despega el otro y el margen hasta el borde del pie. Entre pose y pose interpola (como si los servos llegaran
todos juntos), asi se ve tambien lo que pasa en el medio.
Solo lee los archivos de la app: no escribe nada ni se conecta al robot.
Pestana 3D con las piezas reales del CAD (visor3d.py) y pestana 2D con las tres vistas.
Uso: python visor_simulador.py   (o doble click en Simulador.bat)
"""
import json
import math
import os
import sys

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QTabWidget, QVBoxLayout, QWidget)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import simular_caminata as sc  # noqa: E402
import visor3d  # noqa: E402

DATOS = sc.cn.DATOS
COLOR = {"izq": QColor("#3b82f6"), "der": QColor("#ef4444"), "cuerpo": QColor("#9ca3af"), "com": QColor("#22c55e"),
         "piso": QColor("#6b7280"), "fondo": QColor("#111827"), "texto": QColor("#e5e7eb"), "malo": QColor("#f59e0b")}
# caja del cuerpo de arriba en mm (marco de la pelvis): de frente se ve el ancho (x), de costado la profundidad (z)
TORSO = {0: [(-32.0, 4.0, 0.0), (32.0, 4.0, 0.0), (32.0, 95.0, 0.0), (-32.0, 95.0, 0.0)],
         2: [(0.0, 4.0, -18.0), (0.0, 4.0, 30.0), (0.0, 95.0, 30.0), (0.0, 95.0, -18.0)]}
PASO_SIM = 40              # ms entre calculos del recorrido (el apoyo depende de como venia el robot)
FPS = 30


def leer_json(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


# =====================================================================
# SEGMENTO: DIBUJO DEL ROBOT
# =====================================================================
class Lienzo(QWidget):
    def __init__(self):
        super().__init__()
        self.res = None
        self.setMinimumSize(900, 420)

    def mostrar(self, res):
        self.res = res
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), COLOR["fondo"])
        if not self.res:
            return
        w, h = self.width(), self.height()
        ancho = w / 3
        vistas = [("De frente (su izquierda, azul, a la derecha)", 0, 1), ("De costado (adelante a la derecha)", 2, 1),
                  ("Desde arriba (adelante hacia arriba)", 0, 2)]
        for k, (titulo, ix, iy) in enumerate(vistas):
            caja = QRectF(k * ancho + 8, 28, ancho - 16, h - 40)
            p.setPen(COLOR["texto"])
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(k * ancho, 4, ancho, 20), Qt.AlignCenter, titulo)
            if iy == 1:
                self.vista_alzado(p, caja, ix)
            else:
                self.vista_planta(p, caja)

    def a_pantalla(self, caja, u, v, rango_u=(-110, 110), rango_v=(-10, 260)):
        esc = min(caja.width() / (rango_u[1] - rango_u[0]), caja.height() / (rango_v[1] - rango_v[0]))
        cx = caja.center().x()
        base = caja.bottom() - 10
        return QPointF(cx + u * esc, base - (v - rango_v[0]) * esc)

    def vista_alzado(self, p, caja, ix):
        r = self.res
        piso_a, piso_b = self.a_pantalla(caja, -110, 0), self.a_pantalla(caja, 110, 0)
        p.setPen(QPen(COLOR["piso"], 2))
        p.drawLine(piso_a, piso_b)
        # cuerpo de arriba (caja) sobre las caderas
        p.setPen(QPen(COLOR["cuerpo"], 2))
        p.setBrush(QBrush(QColor(156, 163, 175, 60)))
        p.drawPolygon(QPolygonF([self.a_pantalla(caja, q[ix], q[1]) for q in r["torso"][ix]]))
        p.setBrush(Qt.NoBrush)
        ci, cd = r["mundo"]["izq"][0][0], r["mundo"]["der"][0][0]
        p.setPen(QPen(COLOR["cuerpo"], 6))
        p.drawLine(self.a_pantalla(caja, ci[ix], ci[1]), self.a_pantalla(caja, cd[ix], cd[1]))
        for lado in ("izq", "der"):
            cadena, esq = r["mundo"][lado]
            p.setPen(QPen(COLOR[lado], 5, Qt.SolidLine, Qt.RoundCap))
            planta = esq.mean(axis=0) + [0, 4, 0]      # tobillo -> centro del pie
            for a, b in list(zip(cadena[:-1], cadena[1:])) + [(cadena[-1], planta)]:
                p.drawLine(self.a_pantalla(caja, a[ix], a[1]), self.a_pantalla(caja, b[ix], b[1]))
            orden = [0, 1, 3, 2]
            p.setPen(QPen(COLOR[lado], 4))
            apoya = lado in r["toca"]
            p.setBrush(QBrush(COLOR[lado].darker(150)) if apoya else Qt.NoBrush)
            p.drawPolygon(QPolygonF([self.a_pantalla(caja, esq[i][ix], esq[i][1]) for i in orden]))
            p.setBrush(Qt.NoBrush)
        c = r["com"]
        p.setPen(QPen(COLOR["com"], 1, Qt.DashLine))
        p.drawLine(self.a_pantalla(caja, c[ix], 0), self.a_pantalla(caja, c[ix], c[1]))
        p.setBrush(QBrush(COLOR["com"]))
        p.setPen(Qt.NoPen)
        p.drawEllipse(self.a_pantalla(caja, c[ix], c[1]), 6, 6)
        p.setBrush(Qt.NoBrush)

    def vista_planta(self, p, caja):
        r = self.res
        for lado in ("izq", "der"):
            esq = r["mundo"][lado][1]
            orden = [0, 1, 3, 2]
            apoya = lado in r["toca"]
            p.setPen(QPen(COLOR[lado], 2, Qt.SolidLine if apoya else Qt.DashLine))
            p.setBrush(QBrush(COLOR[lado].darker(150)) if apoya else Qt.NoBrush)
            p.drawPolygon(QPolygonF([self.a_pantalla(caja, esq[i][0], esq[i][2], (-110, 110), (-110, 110)) for i in orden]))
        p.setBrush(QBrush(COLOR["com"]))
        p.setPen(Qt.NoPen)
        c = r["com"]
        p.drawEllipse(self.a_pantalla(caja, c[0], c[2], (-110, 110), (-110, 110)), 6, 6)
        p.setBrush(Qt.NoBrush)


# =====================================================================
# SEGMENTO: VENTANA
# =====================================================================
class Visor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simulador de caminata")
        self.ref = {int(k): v for k, v in sc.leer("Inicionx25", "posiciones")["angulos"].items()}
        self.trim = {c: self.ref[c] for c in sc.cn.PIERNAS}
        self.pasos = []            # [(nombre, angulos, duracion_ms)]
        self.t = 0.0               # tiempo de reproduccion en ms
        self.recorrido = []        # inclinacion del robot cada PASO_SIM ms
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.avanzar)

        self.combo_sec = QComboBox()
        self.combo_pose = QComboBox()
        self.btn_recargar = QPushButton("Recargar")
        self.btn_play = QPushButton("▶ Reproducir")
        self.slider = QSlider(Qt.Horizontal)
        self.vel = QDoubleSpinBox()
        self.vel.setRange(0.1, 3.0)
        self.vel.setSingleStep(0.25)
        self.vel.setValue(1.0)
        self.vel.setSuffix(" x")
        self.check_interp = QCheckBox("Ver el movimiento entre poses")
        self.check_interp.setChecked(True)
        self.lienzo = Lienzo()
        self.vista3d = visor3d.Vista3D()
        self.pestanas = QTabWidget()
        self.pestanas.addTab(self.vista3d, "3D (arrastra con el mouse para girar, rueda para zoom)")
        self.pestanas.addTab(self.lienzo, "2D: frente, costado y huellas")
        self.pestanas.currentChanged.connect(lambda _: self.dibujar())
        self.info = QLabel()
        self.info.setFont(QFont("Consolas", 10))
        self.info.setTextFormat(Qt.RichText)

        arriba = QHBoxLayout()
        arriba.addWidget(QLabel("Secuencia:"))
        arriba.addWidget(self.combo_sec, 2)
        arriba.addWidget(QLabel("o pose suelta:"))
        arriba.addWidget(self.combo_pose, 2)
        arriba.addWidget(self.btn_recargar)
        controles = QHBoxLayout()
        controles.addWidget(self.btn_play)
        controles.addWidget(self.slider, 1)
        controles.addWidget(QLabel("Velocidad:"))
        controles.addWidget(self.vel)
        controles.addWidget(self.check_interp)
        lay = QVBoxLayout(self)
        lay.addLayout(arriba)
        lay.addWidget(self.pestanas, 1)
        lay.addWidget(self.info)
        lay.addLayout(controles)

        self.combo_sec.currentTextChanged.connect(self.cargar_secuencia)
        self.combo_pose.currentTextChanged.connect(self.cargar_pose)
        self.btn_recargar.clicked.connect(self.recargar)
        self.btn_play.clicked.connect(self.play_pausa)
        self.slider.valueChanged.connect(self.mover_slider)
        self.check_interp.toggled.connect(lambda _: self.empezar(self.pasos) if self.pasos else None)
        self.recargar()

    # ------------------------------------------------------------------
    def recargar(self):
        sec = sorted(f[:-5] for f in os.listdir(os.path.join(DATOS, "secuencias")) if f.endswith(".json"))
        poses = []
        for f in os.listdir(os.path.join(DATOS, "posiciones")):
            if f.endswith(".json"):
                d = leer_json(os.path.join(DATOS, "posiciones", f))
                poses.append((d.get("carpeta", ""), d["nombre"]))
        self.poses = {n: c for c, n in poses}
        for combo, items in ((self.combo_sec, ["(elige)"] + sec),
                             (self.combo_pose, ["(elige)"] + [f"{c} / {n}" if c else n for c, n in sorted(poses)])):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(items)
            combo.blockSignals(False)

    def angulos(self, nombre):
        return {int(k): v for k, v in sc.leer(nombre, "posiciones")["angulos"].items()}

    def cargar_secuencia(self, nombre):
        if not nombre or nombre == "(elige)":
            return
        d = leer_json(os.path.join(DATOS, "secuencias", nombre + ".json"))
        pasos = []
        for paso in d["pasos"]:
            try:
                pasos.append((paso["posicion"], self.angulos(paso["posicion"]), paso["duracion_ms"]))
            except FileNotFoundError:
                pasos.append((paso["posicion"] + " (NO EXISTE)", dict(self.ref), paso["duracion_ms"]))
        self.empezar([("Inicionx25 (erguido)", dict(self.ref), 400)] + pasos)

    def cargar_pose(self, texto):
        if not texto or texto == "(elige)":
            return
        nombre = texto.split(" / ", 1)[-1]
        self.empezar([(nombre, self.angulos(nombre), 1000)])

    def empezar(self, pasos):
        self.timer.stop()
        self.btn_play.setText("▶ Reproducir")
        self.pasos = pasos
        self.total = sum(d for _, _, d in pasos)
        self.slider.blockSignals(True)
        self.slider.setRange(0, int(self.total))
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self.t = 0.0
        # recorrido completo una vez: la inclinacion en cada instante depende de la anterior (un robot que viene
        # cargado en un pie sigue en ese pie), asi la barra puede saltar a cualquier momento sin perder eso
        self.recorrido = []
        previo = (0.0, 0.0)
        for k in range(int(self.total // PASO_SIM) + 1):
            previo = sc.analizar(self.pose_en(k * PASO_SIM)[2], self.trim, previo, 2.0)["inc"]
            self.recorrido.append(previo)
        self.dibujar()

    # ------------------------------------------------------------------
    def play_pausa(self):
        if not self.pasos:
            return
        if self.timer.isActive():
            self.timer.stop()
            self.btn_play.setText("▶ Reproducir")
        else:
            if self.t >= self.total - 1:
                self.t = 0.0
            self.timer.start(int(1000 / FPS))
            self.btn_play.setText("⏸ Pausa")

    def avanzar(self):
        self.t += 1000 / FPS * self.vel.value()
        if self.t >= self.total:
            self.t = self.total - 1
            self.timer.stop()
            self.btn_play.setText("▶ Reproducir")
        self.slider.blockSignals(True)
        self.slider.setValue(int(self.t))
        self.slider.blockSignals(False)
        self.dibujar()

    def mover_slider(self, v):
        self.t = float(v)
        self.dibujar()

    def pose_en(self, t):
        """angulos en el instante t: cada paso empieza en la pose anterior y llega a la suya al final de su duracion"""
        inicio = 0.0
        anterior = self.pasos[0][1]
        for k, (nombre, ang, dur) in enumerate(self.pasos):
            if t < inicio + dur or k == len(self.pasos) - 1:
                f = min(1.0, max(0.0, (t - inicio) / dur)) if self.check_interp.isChecked() else 1.0
                f = f * f * (3 - 2 * f)
                mezcla = {c: anterior.get(c, 0) + (ang.get(c, 0) - anterior.get(c, 0)) * f for c in ang}
                return k, nombre, mezcla
            inicio += dur
            anterior = ang
        return 0, "", self.ref

    def dibujar(self):
        if not self.pasos:
            return
        k, nombre, ang = self.pose_en(self.t)
        previo = self.recorrido[min(int(self.t // PASO_SIM), len(self.recorrido) - 1)]
        r = sc.analizar(ang, self.trim, previo, 2.0)
        # caja del cuerpo de arriba, en el mismo marco que el resto (apoyado en el piso)
        rl, rf = r["inc"]
        R = sc.rot_x(rf) @ sc.rot_z(rl)
        cadera_cuerpo = np.array([sc.CADERA_X, 0.0, 0.0])
        piso = (R @ cadera_cuerpo)[1] - r["mundo"]["izq"][0][0][1]
        r["torso"] = {ix: [R @ np.array(q) - [0, piso, 0] for q in caja] for ix, caja in TORSO.items()}
        if self.pestanas.currentWidget() is self.vista3d:
            self.vista3d.mostrar(ang, self.trim, r)
        else:
            self.lienzo.mostrar(r)
        alto = r["alto"]
        apoya = {"izq+der": "los dos pies", "izq": "pie IZQUIERDO", "der": "pie DERECHO"}["+".join(r["toca"])]
        aviso = ""
        if len(r["toca"]) == 1 and r["margen_juego"] < 0:
            aviso = f"  <span style='color:{COLOR['malo'].name()}'>⚠ casi al borde del pie</span>"
        self.info.setText(
            f"<span style='color:#e5e7eb'>Paso {k + 1}/{len(self.pasos)}: <b>{nombre}</b> &nbsp;|&nbsp; apoya: <b>{apoya}</b>"
            f" &nbsp;|&nbsp; pie izq {alto['izq']:.0f} mm, pie der {alto['der']:.0f} mm del piso"
            f" &nbsp;|&nbsp; inclinacion {r['lat']:+.1f}°"
            f" &nbsp;|&nbsp; margen {r['margen']:.0f} mm{aviso}</span>")


def main():
    app = QApplication(sys.argv)
    v = Visor()
    v.resize(1300, 680)
    if len(sys.argv) > 1:                       # visor_simulador.py "Nombre de secuencia": la abre ya elegida
        v.combo_sec.setCurrentText(sys.argv[1])
    v.setStyleSheet("QWidget { background: #1f2937; color: #e5e7eb; } QPushButton, QComboBox, QDoubleSpinBox "
                    "{ background: #374151; padding: 4px; }")
    v.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
