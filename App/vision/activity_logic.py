import numpy as np
from collections import deque

class ActivityCheck:
    def __init__(self, fm=30):
        self.fm = fm
        self.len_pos_max = 8 * self.fm 
        self.posiciones = deque(maxlen=self.len_pos_max)
        
        # Parámetros (Ajustar según resolución)
        self.dist_inact = 1.5   
        
        # Debouncing
        self.th_activo = self.fm / 3
        self.th_inactivo = self.fm / 3
        self.th_pacing = self.fm / 2
        self.th_na = self.fm * 1

        # Estado
        self.estado_actual = "N/A"
        self.counter_activo = 0
        self.counter_inactivo = 0
        self.counter_pacing = 0
        self.counter_na = 0
        
    def update_pos(self, pos):
        self.posiciones.append(pos)

    def dist_eucl(self, pos1, pos2):
        x1, y1 = pos1[0], pos1[1]
        x2, y2 = pos2[0], pos2[1]
        return np.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

    def estado_estable(self, estado_crudo):
        if estado_crudo == "Activo":
            self.counter_activo += 1
            self.counter_inactivo = 0
            self.counter_pacing = 0
            self.counter_na = 0
            if self.counter_activo >= self.th_activo:
                self.estado_actual = "Movimiento"

        elif estado_crudo == "Inactivo":
            self.counter_inactivo += 1
            self.counter_activo = 0
            self.counter_pacing = 0
            self.counter_na = 0
            if self.counter_inactivo >= self.th_inactivo:
                self.estado_actual = "Quieto"

        elif estado_crudo == "Pacing":
            self.counter_pacing += 1
            self.counter_activo = 0
            self.counter_inactivo = 0
            self.counter_na = 0
            if self.counter_pacing >= self.th_pacing:
                self.estado_actual = "Pacing"

        else: # N/A
            self.counter_na += 1
            self.counter_activo = 0
            self.counter_inactivo = 0
            self.counter_pacing = 0
            if self.counter_na >= self.th_na:
                self.estado_actual = "N/A"

        return self.estado_actual

    def detect_pacing_acf(self):
        # Implementación simplificada para integración
        # Si tienes tu lógica de pacing compleja, pégala aquí
        return False 

    def estado(self, pos):
        if (pos[0] == 0 and pos[1] == 0) or len(self.posiciones) == 0:
            return "N/A"
        
        if self.dist_eucl(pos, self.posiciones[-1]) <= self.dist_inact:
            return "Inactivo"
        
        if self.detect_pacing_acf():
            return "Pacing"
            
        return "Activo"