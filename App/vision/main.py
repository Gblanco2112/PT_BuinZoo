import cv2
import sys
import numpy as np
import threading
import time
import os
import requests  # <--- Para hablar con el otro Docker
from pathlib import Path
from ultralytics import YOLO
from settings import settings
# Importamos tu lógica
from activity_logic import ActivityCheck

# --- CONFIGURACIÓN ---
# Leemos variables de entorno del docker-compose, o usamos defaults
RTSP_LEFT = os.getenv("RTSP_LEFT", "rtsp://view:vieW.,star3250@190.8.125.219:554/cam/realmonitor?channel=2&subtype=0")
RTSP_RIGHT = os.getenv("RTSP_RIGHT", "rtsp://view:vieW.,star3250@190.8.125.219:554/cam/realmonitor?channel=1&subtype=0")
API_URL = os.getenv("API_URL", "http://web_app:8000/api/events")
ANIMAL_ID = "a-001" # Debe coincidir con el ID en la BD del backend

# Mapeo: Visión -> Backend (Inglés)
# Traduce los estados que entrega la visión a estados esperados por la API.
BEHAVIOR_MAP = {
    "Quieto": "Resting",
    "Movimiento": "Locomotion",
    "Pacing": "Stereotypy",
    "N/A": "Resting" # Asumimos descanso si no se ve
}

# Intervalo (en segundos) entre envíos de eventos al backend
DB_SAVE_INTERVAL = settings.TS_SECONDS # Segundos entre envíos a la API

class RTSPStream:
    """Hilo lector para una cámara RTSP, evitando acumulación de buffer (buffer drift)."""
    def __init__(self, src):
        self.capture = cv2.VideoCapture(src)
        # Se limita el tamaño del buffer interno del capture
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.status = False
        self.frame = None
        self.stopped = False
        if self.capture.isOpened():
            # Leemos un frame inicial para conocer FPS y estado
            self.status, self.frame = self.capture.read()
            self.fps = self.capture.get(cv2.CAP_PROP_FPS)
        else:
            # Valor por defecto si no se puede leer FPS
            self.fps = 20

    def start(self):
        # Arranca el hilo de lectura continua de frames
        t = threading.Thread(target=self.update, args=(), daemon=True)
        t.start()
        return self

    def update(self):
        # Bucle de lectura mientras no se detenga el stream
        while not self.stopped:
            if not self.capture.isOpened():
                self.stop()
                break
            status, frame = self.capture.read()
            if status:
                # Actualizamos el último frame disponible
                self.frame = frame
                self.status = status
            else:
                # Si se pierde la señal, detenemos el stream
                self.stop()

    def read(self):
        # Devuelve el último estado y frame leídos
        return self.status, self.frame

    def stop(self):
        # Marca el hilo para detenerse y libera la cámara si sigue abierta
        self.stopped = True
        if self.capture.isOpened(): self.capture.release()

def process_camera(model, frame, checker):
    """
    Procesa un frame de cámara:
    - Aplica YOLO con tracking para obtener la posición del animal.
    - Actualiza el ActivityCheck con la nueva posición.
    - Devuelve el bounding box (si existe) y el estado de actividad estabilizado.
    """
    # YOLO Tracking con GPU
    results = model.track(
        frame, persist=True, verbose=False, conf=0.5, iou=0.5,
        tracker="bytetrack.yaml", max_det=1, device=0 
    )

    pos_actual = np.array([0.0, 0.0])
    bbox = None

    # Si hay detecciones, tomamos la primera (máx. 1 por configuración)
    if results[0].boxes and len(results[0].boxes) > 0:
        box = results[0].boxes[0]
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        pos_actual = np.array([cx, cy])
        bbox = (int(x1), int(y1), int(x2), int(y2))

    # Estado crudo basado solo en la posición actual
    estado_crudo = checker.estado(pos_actual)
    # Actualizamos el historial con la nueva posición
    checker.update_pos(pos_actual)
    # Estado final tras aplicar debouncing / filtro temporal
    estado_final = checker.estado_estable(estado_crudo)
    
    return bbox, estado_final

def fusionar_estados(est1, est2):
    """
    Fusiona los estados de las dos cámaras en un único estado global.
    Se prioriza:
    1. Pacing
    2. Movimiento
    3. Quieto
    4. N/A (sin información)
    """
    estados = [est1, est2]
    if "Pacing" in estados: return "Pacing"
    if "Movimiento" in estados: return "Movimiento"
    if "Quieto" in estados: return "Quieto"
    return "N/A"

def send_to_backend(behavior_vision):
    """Envía la información de comportamiento al contenedor web mediante HTTP POST."""
    # Mapear el estado de visión al estado esperado por la BD
    behavior_db = BEHAVIOR_MAP.get(behavior_vision, "Resting")
    
    payload = {
        "animal_id": ANIMAL_ID,
        "behavior": behavior_db,
        "confidence": 1.0
    }
    
    try:
        # Enviamos la petición al otro docker (web_app)
        resp = requests.post(API_URL, json=payload, timeout=2)
        if resp.status_code != 201:
            # No consideramos error fatal, solo logueamos la advertencia
            print(f"[API WARN] Backend respondió: {resp.status_code}")
    except Exception as e:
        # Cualquier error de conexión queda registrado en logs
        print(f"[API ERROR] Fallo conexión con web_app: {e}")

def main():
    """
    Punto de entrada principal:
    - Carga el modelo YOLO.
    - Inicializa streams RTSP de ambas cámaras.
    - Ejecuta un loop infinito de lectura, inferencia y envío periódico al backend.
    """
    print("--- INICIANDO VISIÓN CARACAL (DOCKER) ---")
    weights_path = Path("yolo_model/best.pt")
    
    # Esperar a que el archivo de pesos exista (por ejemplo, si el volumen tarda en montarse)
    while not weights_path.exists():
        print("Esperando archivo de pesos en yolo_model/best.pt...")
        time.sleep(5)
        
    print(f"Cargando YOLO: {weights_path}")
    model = YOLO(str(weights_path))

    print("Conectando cámaras...")
    stream_left = RTSPStream(RTSP_LEFT).start()
    stream_right = RTSPStream(RTSP_RIGHT).start()
    time.sleep(3) # Buffer warm-up

    # Creación de chequeadores de actividad para cada cámara
    checker_left = ActivityCheck(fm=20)
    checker_right = ActivityCheck(fm=20)
    
    last_save_time = time.time()
    print("Sistema ONLINE. Procesando...")

    while True:
        # Leemos el frame más reciente de cada cámara (RAW desde el hilo)
        status_l, frame_left_raw = stream_left.read()  # Leemos el RAW
        status_r, frame_right_raw = stream_right.read() # Leemos el RAW

        if not status_l or not status_r:
            # Si falta señal en alguna cámara, esperamos y reintentamos
            print("Esperando señal de video...")
            time.sleep(1)
            continue
        
        # Copia defensiva para no modificar el frame compartido por el hilo
        frame_left = frame_left_raw.copy()
        frame_right = frame_right_raw.copy()
        
        # Ajuste de tamaño simple si las cámaras tienen resoluciones diferentes
        if frame_left.shape != frame_right.shape:
             frame_right = cv2.resize(frame_right, (frame_left.shape[1], frame_left.shape[0]))

        # Procesamiento de cada cámara
        _, estado_l = process_camera(model, frame_left, checker_left)
        _, estado_r = process_camera(model, frame_right, checker_right)
        
        # Fusión del estado global del animal
        estado_global = fusionar_estados(estado_l, estado_r)
        
        # Envío al Backend (cada X segundos, según DB_SAVE_INTERVAL)
        current_time = time.time()
        if current_time - last_save_time >= DB_SAVE_INTERVAL:
            print(f"[VISION] Detectado: {estado_global} -> Enviando a API...")
            # Se usa un thread para no bloquear el loop de video
            t = threading.Thread(target=send_to_backend, args=(estado_global,))
            t.start()
            last_save_time = current_time

    # Nota: estas líneas no se alcanzan en el while True,
    # pero se dejan por claridad si en el futuro se añade lógica de salida.
    stream_left.stop()
    stream_right.stop()

if __name__ == "__main__":
    main()
