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
BEHAVIOR_MAP = {
    "Quieto": "Resting",
    "Movimiento": "Locomotion",
    "Pacing": "Stereotypy",
    "N/A": "Resting" # Asumimos descanso si no se ve
}

DB_SAVE_INTERVAL = settings.TS_SECONDS # Segundos entre envíos a la API

class RTSPStream:
    """Hilo lector para evitar buffer drift"""
    def __init__(self, src):
        self.capture = cv2.VideoCapture(src)
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.status = False
        self.frame = None
        self.stopped = False
        if self.capture.isOpened():
            self.status, self.frame = self.capture.read()
            self.fps = self.capture.get(cv2.CAP_PROP_FPS)
        else:
            self.fps = 20

    def start(self):
        t = threading.Thread(target=self.update, args=(), daemon=True)
        t.start()
        return self

    def update(self):
        while not self.stopped:
            if not self.capture.isOpened():
                self.stop()
                break
            status, frame = self.capture.read()
            if status:
                self.frame = frame
                self.status = status
            else:
                self.stop()

    def read(self):
        return self.status, self.frame

    def stop(self):
        self.stopped = True
        if self.capture.isOpened(): self.capture.release()

def process_camera(model, frame, checker):
    # YOLO Tracking con GPU
    results = model.track(
        frame, persist=True, verbose=False, conf=0.5, iou=0.5,
        tracker="bytetrack.yaml", max_det=1, device=0 
    )

    pos_actual = np.array([0.0, 0.0])
    bbox = None

    if results[0].boxes and len(results[0].boxes) > 0:
        box = results[0].boxes[0]
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        pos_actual = np.array([cx, cy])
        bbox = (int(x1), int(y1), int(x2), int(y2))

    estado_crudo = checker.estado(pos_actual)
    checker.update_pos(pos_actual)
    estado_final = checker.estado_estable(estado_crudo)
    
    return bbox, estado_final

def fusionar_estados(est1, est2):
    estados = [est1, est2]
    if "Pacing" in estados: return "Pacing"
    if "Movimiento" in estados: return "Movimiento"
    if "Quieto" in estados: return "Quieto"
    return "N/A"

def send_to_backend(behavior_vision):
    """Envía la info al contenedor web mediante HTTP POST"""
    behavior_db = BEHAVIOR_MAP.get(behavior_vision, "Resting")
    
    payload = {
        "animal_id": ANIMAL_ID,
        "behavior": behavior_db,
        "confidence": 1.0
    }
    
    try:
        # Enviamos la petición al otro docker
        resp = requests.post(API_URL, json=payload, timeout=2)
        if resp.status_code != 201:
            print(f"[API WARN] Backend respondió: {resp.status_code}")
    except Exception as e:
        print(f"[API ERROR] Fallo conexión con web_app: {e}")

def main():
    print("--- INICIANDO VISIÓN CARACAL (DOCKER) ---")
    weights_path = Path("yolo_model/best.pt")
    
    # Esperar a que el archivo exista (por si el volumen tarda)
    while not weights_path.exists():
        print("Esperando archivo de pesos en yolo_model/best.pt...")
        time.sleep(5)
        
    print(f"Cargando YOLO: {weights_path}")
    model = YOLO(str(weights_path))

    print("Conectando cámaras...")
    stream_left = RTSPStream(RTSP_LEFT).start()
    stream_right = RTSPStream(RTSP_RIGHT).start()
    time.sleep(3) # Buffer warm-up

    checker_left = ActivityCheck(fm=20)
    checker_right = ActivityCheck(fm=20)
    
    last_save_time = time.time()
    print("Sistema ONLINE. Procesando...")

    while True:
        status_l, frame_left = stream_left.read()
        status_r, frame_right = stream_right.read()

        if not status_l or not status_r:
            print("Esperando señal de video...")
            time.sleep(1)
            continue
            
        # Ajuste de tamaño simple
        if frame_left.shape != frame_right.shape:
             frame_right = cv2.resize(frame_right, (frame_left.shape[1], frame_left.shape[0]))

        # Procesamiento
        _, estado_l = process_camera(model, frame_left, checker_left)
        _, estado_r = process_camera(model, frame_right, checker_right)
        
        estado_global = fusionar_estados(estado_l, estado_r)
        
        # Envío a Backend (cada X segundos)
        current_time = time.time()
        if current_time - last_save_time >= DB_SAVE_INTERVAL:
            print(f"[VISION] Detectado: {estado_global} -> Enviando a API...")
            # Thread para no bloquear video
            t = threading.Thread(target=send_to_backend, args=(estado_global,))
            t.start()
            last_save_time = current_time

    stream_left.stop()
    stream_right.stop()

if __name__ == "__main__":
    main()