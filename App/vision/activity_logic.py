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

    def detect_pacing_acf(self, min_cycle_length_s=3.0,
                          max_cycle_length_s=7.0,
                          sample_dt=1/30,
                          acf_thresh=0.15,
                          max_frac_missing=0.5,
                          debug=False):
        """
        min_cycle_length_s, max_cycle_length_s: rango de largos de ciclo esperados (segundos).
        sample_dt: intervalo entre muestras (s).
        acf_thresh: umbral de autocorrelación para considerar periodicidad.
        """
        # Se obtiene un array para las posiciones
        pos = np.array(list(self.posiciones))  # shape (N,2)
        N = len(pos)
        if N < 3:
            return False

        # Se marcan los datos inválidos (casos NaN, sin bounding box)
        invalid_mask = (pos[:,0] == 0) & (pos[:,1] == 0)
        n_invalid = invalid_mask.sum()
        frac_missing = n_invalid / N
        n_valid = N - n_invalid

        # Decide si hay suficiente datos válidos
        if frac_missing > max_frac_missing or n_valid < 3:
            if debug:
                print("Falso con motivo: demasiados puntos faltantes")
            return False

        # Se genera una serie de distancias para cada punto respecto al primero
        first_valid_idx = np.where(~invalid_mask)[0][0]
        ref = pos[first_valid_idx]

        # distancias (y marcar NaNs donde inválido)
        dists = np.linalg.norm(pos - ref, axis=1).astype(float)
        dists[invalid_mask] = np.nan

        # Se interpolan los NaN para reducir cambios abruptos
        idx = np.arange(N)
        valid_idx = idx[~np.isnan(dists)]
        valid_vals = dists[~np.isnan(dists)]

        # Si por alguna razón no hay válidos (ya chequeado), se retorna False
        if len(valid_idx) == 0:
            if debug:
                print("Falso con motivo: sin puntos válidos")
            return False

        # Interpolación lineal
        dists_interp = np.interp(idx, valid_idx, valid_vals)

        # Se suaviza para reducir ruido
        def smooth_sig(x, k=3):
            if k <= 1:
                return x
            kernel = np.ones(k) / k
            # modo 'same' manual con padding
            xp = np.pad(x, (k//2, k-1-k//2), mode='edge')
            return np.convolve(xp, kernel, mode='valid')

        d = dists_interp - np.mean(dists_interp)  # centrar
        d = smooth_sig(d, k=3)

        # Autocorrelación (normalizada)
        acf_full = np.correlate(d, d, mode='full')
        acf = acf_full[acf_full.size//2:]
        if acf[0] == 0:
            if debug:
                print("Falso con motivo: varianza cero tras interpolar")
        acf = acf / acf[0]

        # Se buscan picos de ACF en el rango de lags permitidos
        min_lag = int(max(1, np.floor(min_cycle_length_s / sample_dt)))
        max_lag = int(np.ceil(max_cycle_length_s / sample_dt))
        max_lag = min(max_lag, len(acf)-1)
        if min_lag >= max_lag:
            if debug:
                print("Falso con motivo: rango lag inválido")
            return False

        # Se busca el pico más alto en el rango (excluyendo lag 0)
        search_segment = acf[min_lag:max_lag+1]
        peak_rel_idx = int(np.argmax(search_segment))
        lag = peak_rel_idx + min_lag
        peak = acf[lag]
        

        # Se define si es pacing si es que el peak es mayor al
        # threshold establecido
        info = {
            'acf_peak': float(peak)
        }

        if debug:
            print(info)

        return peak >= acf_thresh


    def estado(self, pos):
        if (pos[0] == 0 and pos[1] == 0) or len(self.posiciones) == 0:
            return "N/A"
        
        if self.dist_eucl(pos, self.posiciones[-1]) <= self.dist_inact:
            return "Inactivo"
        
        if self.detect_pacing_acf():
            return "Pacing"
            
        return "Activo"