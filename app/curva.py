"""SEGMENTO: CURVA CONTINUA ENTRE POSES (modo "Continuo" de las secuencias)
En vez de ir de pose en pose frenando en cada una, cada servo sigue una curva suave que pasa exactamente por todas
las poses de la secuencia, en los tiempos de la secuencia (cada pose se alcanza al final de su duracion).
Curva cubica monotona (Fritsch-Carlson): entre dos poses el angulo nunca se pasa de ninguna de las dos, asi que no
aparecen angulos que la secuencia no tiene (por ejemplo una inclinacion de mas). Arranca y termina con velocidad 0.
La usa el panel de secuencias (manda la curva en tramos cortos con POSET lineal) y la herramienta que verifica el
equilibrio (herramientas/acelerar_secuencias.py), asi las dos ven exactamente el mismo movimiento.
"""


class Curva:
    def __init__(self, nudos):
        """nudos: lista de (tiempo_ms, {canal: angulo}), tiempos crecientes"""
        self.t = [float(t) for t, _ in nudos]
        self.canales = list(nudos[0][1].keys())
        self.v = {c: [float(a.get(c, nudos[0][1][c])) for _, a in nudos] for c in self.canales}
        self.m = {c: self._tangentes(self.v[c]) for c in self.canales}
        self.total = self.t[-1]

    def _tangentes(self, v):
        t, n = self.t, len(v)
        h = [t[k + 1] - t[k] for k in range(n - 1)]
        d = [(v[k + 1] - v[k]) / h[k] if h[k] > 0 else 0.0 for k in range(n - 1)]
        m = [0.0] * n                                   # extremos: arranca y termina quieto
        for k in range(1, n - 1):
            if d[k - 1] * d[k] <= 0:
                m[k] = 0.0                              # cambia de sentido (o se queda): se detiene ahi
            else:
                w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
                m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
        return m

    def en(self, tiempo):
        """{canal: angulo} en el instante tiempo (ms)"""
        t = self.t
        if tiempo <= t[0]:
            return {c: self.v[c][0] for c in self.canales}
        if tiempo >= t[-1]:
            return {c: self.v[c][-1] for c in self.canales}
        k = 0
        lo, hi = 0, len(t) - 1
        while hi - lo > 1:                              # busqueda binaria del tramo
            mid = (lo + hi) // 2
            if t[mid] <= tiempo:
                lo = mid
            else:
                hi = mid
        k = lo
        h = t[k + 1] - t[k]
        s = (tiempo - t[k]) / h
        h00, h10 = 2 * s ** 3 - 3 * s ** 2 + 1, s ** 3 - 2 * s ** 2 + s
        h01, h11 = -2 * s ** 3 + 3 * s ** 2, s ** 3 - s ** 2
        return {c: h00 * self.v[c][k] + h10 * h * self.m[c][k] + h01 * self.v[c][k + 1] + h11 * h * self.m[c][k + 1]
                for c in self.canales}

    def indice_en(self, tiempo):
        """numero de pose (nudo) hacia la que se esta yendo en ese instante"""
        for k, tk in enumerate(self.t):
            if tiempo < tk:
                return k
        return len(self.t) - 1
