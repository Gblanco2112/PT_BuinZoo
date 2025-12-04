import numpy as np
from collections import deque

class ActivityCheck:
    # Clase encargada de analizar la trayectoria del animal (en 2D)
    # y clasificar su estado de actividad (Activo, Inactivo, Pacing, N/A)
    # usando la posición a lo largo del tiempo.
    def __init__(self, fm=30):
        # fm: frecuencia de muestreo (frames por segundo) estimada de la cámara
        self.fm = fm
        # Cantidad máxima de posiciones que se almacenan en memoria (historial)
        self.len_pos_max = 8 * self.fm 
        self.posiciones = deque(maxlen=self.len_pos_max)
        
        # Parámetros (Ajustar según resolución / escala de la cámara)
        # Distancia euclidiana máxima para considerar que no hay movimiento
        self.dist_inact = 1.5   
        
        # Debouncing (histeresis temporal para evitar cambios bruscos de estado)
        # Frames mínimos consecutivos para consolidar cada estado.
        self.th_activo = self.fm / 3
        self.th_inactivo = self.fm / 3
        self.th_pacing = self.fm / 2
        self.th_na = self.fm * 1

        # Estado actual "estable" (tras aplicar debouncing)
        self.estado_actual = "N/A"
        # Contadores internos de cuántos frames consecutivos van con cada estado
        self.counter_activo = 0
        self.counter_inactivo = 0
        self.counter_pacing = 0
        self.counter_na = 0
        
    def update_pos(self, pos):
        # Agrega la nueva posición (x, y) al buffer de posiciones
        # pos: array-like de longitud 2 [x, y]
        self.posiciones.append(pos)

    def dist_eucl(self, pos1, pos2):
        # Calcula la distancia euclidiana entre dos puntos en el plano
        # pos1, pos2: arrays [x, y]
        x1, y1 = pos1[0], pos1[1]
        x2, y2 = pos2[0], pos2[1]
        return np.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

    def estado_estable(self, estado_crudo):
        """
        Aplica lógica de debouncing sobre el 'estado_crudo' para obtener
        un estado más estable en el tiempo.
        
        estado_crudo: string en {"Activo", "Inactivo", "Pacing", "N/A"}
        return: estado "filtrado" en {"Movimiento", "Quieto", "Pacing", "N/A"}
        """
        if estado_crudo == "Activo":
            # Incrementa contador de frames activos y resetea el resto
            self.counter_activo += 1
            self.counter_inactivo = 0
            self.counter_pacing = 0
            self.counter_na = 0
            # Si supera el umbral, fijamos el estado estable en "Movimiento"
            if self.counter_activo >= self.th_activo:
                self.estado_actual = "Movimiento"

        elif estado_crudo == "Inactivo":
            # Incrementa contador de frames inactivos y resetea el resto
            self.counter_inactivo += 1
            self.counter_activo = 0
            self.counter_pacing = 0
            self.counter_na = 0
            # Si supera el umbral, fijamos el estado estable en "Quieto"
            if self.counter_inactivo >= self.th_inactivo:
                self.estado_actual = "Quieto"

        elif estado_crudo == "Pacing":
            # Incrementa contador de frames con patrón periódico (pacing)
            self.counter_pacing += 1
            self.counter_activo = 0
            self.counter_inactivo = 0
            self.counter_na = 0
            # Si supera el umbral, fijamos el estado estable en "Pacing"
            if self.counter_pacing >= self.th_pacing:
                self.estado_actual = "Pacing"

        else: # N/A
            # Incrementa contador de frames sin información válida
            self.counter_na += 1
            self.counter_activo = 0
            self.counter_inactivo = 0
            self.counter_pacing = 0
            # Si supera el umbral, fijamos el estado estable en "N/A"
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
        Detecta comportamiento tipo "pacing" (movimiento repetitivo / estereotipado)
        usando autocorrelación sobre la serie de distancias a un punto de referencia.
        
        Parámetros:
            min_cycle_length_s: largo mínimo de ciclo esperado (segundos).
            max_cycle_length_s: largo máximo de ciclo esperado (segundos).
            sample_dt: intervalo entre muestras (s), normalmente 1/fps.
            acf_thresh: umbral de autocorrelación para considerar que hay periodicidad.
            max_frac_missing: fracción máxima de muestras faltantes permitidas.
            debug: si es True, imprime mensajes de depuración.
        
        Retorna:
            True si detecta periodicidad consistente con pacing,
            False en caso contrario.
        """
        # Se obtiene un array con todas las posiciones en el buffer
        pos = np.array(list(self.posiciones))  # shape (N,2)
        N = len(pos)
        if N < 3:
            # No hay suficientes muestras para análisis
            return False

        # Se marcan los datos inválidos (por ejemplo, sin bounding box => (0,0))
        invalid_mask = (pos[:,0] == 0) & (pos[:,1] == 0)
        n_invalid = invalid_mask.sum()
        frac_missing = n_invalid / N
        n_valid = N - n_invalid

        # Decide si hay suficiente datos válidos para hacer el análisis
        if frac_missing > max_frac_missing or n_valid < 3:
            if debug:
                print("Falso con motivo: demasiados puntos faltantes")
            return False

        # Se genera una serie de distancias para cada punto respecto al primero válido
        first_valid_idx = np.where(~invalid_mask)[0][0]
        ref = pos[first_valid_idx]

        # Distancias (y marcamos NaNs donde la posición es inválida)
        dists = np.linalg.norm(pos - ref, axis=1).astype(float)
        dists[invalid_mask] = np.nan

        # Se interpolan los NaN para obtener una serie continua
        idx = np.arange(N)
        valid_idx = idx[~np.isnan(dists)]
        valid_vals = dists[~np.isnan(dists)]

        # Si por alguna razón no hay válidos (ya chequeado), se retorna False
        if len(valid_idx) == 0:
            if debug:
                print("Falso con motivo: sin puntos válidos")
            return False

        # Interpolación lineal de los puntos válidos a toda la serie
        dists_interp = np.interp(idx, valid_idx, valid_vals)

        # Se suaviza la señal para reducir ruido de alta frecuencia
        def smooth_sig(x, k=3):
            # Suavizado por media móvil de ventana k
            if k <= 1:
                return x
            kernel = np.ones(k) / k
            # modo 'same' manual con padding en los bordes
            xp = np.pad(x, (k//2, k-1-k//2), mode='edge')
            return np.convolve(xp, kernel, mode='valid')

        # Centramos la serie y aplicamos suavizado
        d = dists_interp - np.mean(dists_interp)  # centrar
        d = smooth_sig(d, k=3)

        # Autocorrelación (normalizada) de la señal
        acf_full = np.correlate(d, d, mode='full')
        acf = acf_full[acf_full.size//2:]
        if acf[0] == 0:
            # Varianza cero => no hay señal útil
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

        # True => hay periodicidad fuerte en la señal de movimiento
        return peak >= acf_thresh


    def estado(self, pos):
        """
        Determina el estado "crudo" a partir de la posición actual:
        
        - Retorna "N/A" si no hay tracking válido o historial vacío.
        - Retorna "Inactivo" si la diferencia con la última posición es muy pequeña.
        - Retorna "Pacing" si detecta patrón periódico en el historial.
        - Retorna "Activo" en cualquier otro caso.
        """
        # Si la posición es inválida (0,0) o no hay historial, no hay información
        if (pos[0] == 0 and pos[1] == 0) or len(self.posiciones) == 0:
            return "N/A"
        
        # Si la distancia al último punto es menor que el umbral, se considera inactivo
        if self.dist_eucl(pos, self.posiciones[-1]) <= self.dist_inact:
            return "Inactivo"
        
        # En caso contrario, chequeamos si existe patrón periódico (pacing)
        if self.detect_pacing_acf():
            return "Pacing"
            
        # Si no es inactivo ni pacing, consideramos movimiento genérico (activo)
        return "Activo"
