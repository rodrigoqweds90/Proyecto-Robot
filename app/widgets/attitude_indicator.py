"""SEGMENTO: VISUALIZACION 3D DEL GIROSCOPIO
Un cubo en pseudo-3D (proyectado con QPainter, sin OpenGL ni dependencias
extra) que se inclina igual que el torso del robot segun el pitch/roll que
manda el MPU6050. Sirve para confirmar de un vistazo si el robot esta
correctamente parado antes de moverlo.
"""

import math

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

# Medio-ancho/alto/profundo del torso en unidades arbitrarias (proporcion, no cm reales)
HX, HY, HZ = 0.6, 1.0, 0.35

# Vertices del cubo: 0-3 cara de abajo, 4-7 cara de arriba (mismo orden en X/Z)
_VERTICES = [
    (-HX, -HY, -HZ), (HX, -HY, -HZ), (HX, -HY, HZ), (-HX, -HY, HZ),
    (-HX, HY, -HZ),  (HX, HY, -HZ),  (HX, HY, HZ),  (-HX, HY, HZ),
]
_ARISTAS = [
    (0, 1), (1, 2), (2, 3), (3, 0),  # abajo
    (4, 5), (5, 6), (6, 7), (7, 4),  # arriba
    (0, 4), (1, 5), (2, 6), (3, 7),  # verticales
]
_CARA_FRENTE = [2, 3, 7, 6]  # +Z: hacia donde "mira" el robot
_CARA_ARRIBA = [4, 5, 6, 7]  # +Y: cabeza del robot


class AttitudeIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pitch = 0.0
        self._roll = 0.0
        self.setMinimumSize(180, 190)

    def set_attitude(self, pitch, roll):
        self._pitch = pitch
        self._roll = roll
        self.update()

    # ------------------------------------------------------------------
    def _rotar_proyectar(self, punto, cx, cy, escala):
        x, y, z = punto
        pr = math.radians(self._pitch)
        rr = math.radians(self._roll)

        # Pitch: inclinacion adelante/atras, rota alrededor del eje X
        y1 = y * math.cos(pr) - z * math.sin(pr)
        z1 = y * math.sin(pr) + z * math.cos(pr)
        x1 = x

        # Roll: inclinacion de lado a lado, rota alrededor del eje Z (de frente al robot)
        x2 = x1 * math.cos(rr) - y1 * math.sin(rr)
        y2 = x1 * math.sin(rr) + y1 * math.cos(rr)
        z2 = z1

        foco = 4.0
        factor_persp = foco / (foco - z2)
        sx = cx + x2 * escala * factor_persp
        sy = cy - y2 * escala * factor_persp
        return QPointF(sx, sy), z2

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        alto_texto = 46
        cx = self.width() / 2
        cy = (self.height() - alto_texto) / 2
        escala = min(self.width(), self.height() - alto_texto) * 0.32

        # Linea de horizonte de referencia (fija, no rota) para comparar contra el cubo
        painter.setPen(QPen(QColor("#3a4150"), 1, Qt.DashLine))
        painter.drawLine(QPointF(12, cy), QPointF(self.width() - 12, cy))

        proyectados = [self._rotar_proyectar(v, cx, cy, escala) for v in _VERTICES]
        puntos = [p for p, _ in proyectados]

        def cara(indices, color):
            poligono = QPolygonF([puntos[i] for i in indices])
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawPolygon(poligono)

        cara(_CARA_ARRIBA, QColor("#5f8fd6"))
        cara(_CARA_FRENTE, QColor("#4a76b3"))

        painter.setPen(QPen(QColor("#e6e8ec"), 2))
        for a, b in _ARISTAS:
            painter.drawLine(puntos[a], puntos[b])

        painter.setPen(QColor("#c7cdd8"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        texto = f"Pitch {self._pitch:6.1f}°   Roll {self._roll:6.1f}°"
        painter.drawText(0, self.height() - alto_texto + 14, self.width(), 20, Qt.AlignCenter, texto)

        nivel = abs(self._pitch) < 3 and abs(self._roll) < 3
        painter.setPen(QColor("#4fd18f") if nivel else QColor("#8a90a0"))
        painter.setFont(QFont("Segoe UI", 9))
        estado = "Nivelado" if nivel else "Inclinado"
        painter.drawText(0, self.height() - 18, self.width(), 18, Qt.AlignCenter, estado)
