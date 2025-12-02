import argparse
import cv2
import sys
import numpy as np
import threading
import time
from pathlib import Path
from ultralytics import YOLO

# Importamos tu lógica
from activity_logic import ActivityCheck
# Importar lógica de reconstrucción 3D (NUEVO)
from reconstruccion_3d_yolo import Reconstructor3D

# --- CONFIGURACIÓN DE CÁMARAS (FIJA) ---
RTSP_LEFT  = "rtsp://view:vieW.,star3250@190.8.125.219:554/cam/realmonitor?channel=2&subtype=0"
RTSP_RIGHT = "rtsp://view:vieW.,star3250@190.8.125.219:554/cam/realmonitor?channel=1&subtype=0"

class RTSPStream:
    """
    Clase dedicada a leer el stream en un hilo separado.
    Evita el 'buffer drift' (lag) descartando frames viejos.
    """
    def __init__(self, src):
        self.capture = cv2.VideoCapture(src)
        # Configurar buffer pequeño si el backend lo permite (opcional pero útil)
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.status = False
        self.frame = None
        self.stopped = False
        
        # Leer el primer frame para asegurar conexión
        if self.capture.isOpened():
            self.status, self.frame = self.capture.read()
            self.width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.fps = self.capture.get(cv2.CAP_PROP_FPS)
        else:
            self.status = False

    def start(self):
        # Iniciar el hilo
        t = threading.Thread(target=self.update, args=())
        t.daemon = True # El hilo muere si el programa principal muere
        t.start()
        return self

    def update(self):
        # Loop infinito que lee frames lo más rápido posible
        while not self.stopped:
            if not self.capture.isOpened():
                self.stop()
                break
            
            status, frame = self.capture.read()
            if status:
                # Sobrescribimos self.frame con el MÁS NUEVO
                self.frame = frame
                self.status = status
            else:
                self.stop()

    def read(self):
        # Devuelve el último frame capturado
        return self.status, self.frame

    def stop(self):
        self.stopped = True
        if self.capture.isOpened():
            self.capture.release()

def parse_arguments():
    parser = argparse.ArgumentParser(description="Detector de Conducta de Caracal - Dual Cam")
    parser.add_argument("--view", action="store_true", help="Activar visualización combinada")
    parser.add_argument("--weights", type=str, default="yolo_model/best.pt", help="Ruta pesos .pt")
    return parser.parse_args()

def process_camera(model, frame, checker):
    # Tracking usando la GPU (device=0)
    results = model.track(
        frame, 
        persist=True, 
        verbose=False, 
        conf=0.5, 
        iou=0.5,
        tracker="bytetrack.yaml",
        max_det=1,
        device=0
    )

    pos_actual = np.array([0.0, 0.0])
    bbox = None

    if results[0].boxes is not None and len(results[0].boxes) > 0:
        box = results[0].boxes[0]
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
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

def main():
    args = parse_arguments()
    
    # 1. Cargar Modelo
    weights_path = Path(args.weights)
    if not weights_path.exists():
        sys.exit(f"Error: Pesos no encontrados en {weights_path}")
        
    print(f"Cargando modelo YOLO: {weights_path}")
    model = YOLO(str(weights_path))

    # 2. Inicializar Cámaras con THREADING
    print(f"Iniciando hilo CAM IZQUIERDA (Ch2)...")
    stream_left = RTSPStream(RTSP_LEFT).start()
    
    print(f"Iniciando hilo CAM DERECHA (Ch1)...")
    stream_right = RTSPStream(RTSP_RIGHT).start()

    if not stream_left.status or not stream_right.status:
        print("Error: No se pudo conectar a una de las cámaras.")
        stream_left.stop()
        stream_right.stop()
        sys.exit(1)

    # Usar FPS detectado o default
    fps = stream_left.fps if stream_left.fps > 0 else 20
    
    # 3. Inicializar Lógica
    checker_left = ActivityCheck(fm=int(fps))
    checker_right = ActivityCheck(fm=int(fps))
    
    # 4. Inicializar Reconstrucción 3D (Mapeo: Left=Ch2 -> cam_2, Right=Ch1 -> cam_1)
    print("Inicializando Reconstrucción 3D...")
    reconstructor = Reconstructor3D(
        filename="calibracion_datos.npz",
        cam_key_1='cam_2', 
        cam_key_2='cam_1'
    )

    print(f"Sistema iniciado. FM={int(fps)}. Presiona 'q' para salir.")
    
    if args.view:
        cv2.namedWindow("Monitor Dual Caracal", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Monitor Dual Caracal", 1800, 600)

    while True:
        # Leemos el "instante actual" de ambos hilos
        status_l, frame_left = stream_left.read()
        status_r, frame_right = stream_right.read()

        # Si algún hilo murió o perdió señal
        if not status_l or not status_r:
            print("Pérdida de señal en una cámara.")
            break

        # Redimensionar seguro (usando copias para no afectar al hilo lector)
        if frame_left.shape != frame_right.shape:
            frame_right = cv2.resize(frame_right, (frame_left.shape[1], frame_left.shape[0]))

        # --- PROCESAMIENTO ---
        bbox_l, estado_l = process_camera(model, frame_left, checker_left)
        bbox_r, estado_r = process_camera(model, frame_right, checker_right)

        # --- FUSIÓN ---
        estado_global = fusionar_estados(estado_l, estado_r)

        # --- CÁLCULO 3D ---
        coord_3d_str = "N/A"
        if bbox_l is not None and bbox_r is not None:
            punto_3d = reconstructor.obtener_coordenada_3d(bbox_l, bbox_r)
            if punto_3d is not None:
                x, y, z = punto_3d
                coord_3d_str = f"X:{x:.2f} Y:{y:.2f} Z:{z:.2f}"

        # --- VISUALIZACIÓN ---
        if args.view:
            # Dibujos Izquierda
            if bbox_l:
                cv2.rectangle(frame_left, (bbox_l[0], bbox_l[1]), (bbox_l[2], bbox_l[3]), (0, 255, 0), 2)
                cv2.putText(frame_left, f"CAM 2: {estado_l}", (bbox_l[0], bbox_l[1]-10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                 cv2.putText(frame_left, "Sin deteccion", (30, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            # Dibujos Derecha
            if bbox_r:
                cv2.rectangle(frame_right, (bbox_r[0], bbox_r[1]), (bbox_r[2], bbox_r[3]), (0, 255, 0), 2)
                cv2.putText(frame_right, f"CAM 1: {estado_r}", (bbox_r[0], bbox_r[1]-10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                 cv2.putText(frame_right, "Sin deteccion", (30, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            # Unir
            combined_view = cv2.hconcat([frame_left, frame_right])

            # Info Global
            cv2.rectangle(combined_view, (0, 0), (combined_view.shape[1], 60), (0,0,0), -1)
            color_text = (200, 200, 200)
            if estado_global == "Quieto": color_text = (0, 255, 0)
            elif estado_global == "Movimiento": color_text = (0, 165, 255)
            elif estado_global == "Pacing": color_text = (0, 0, 255)

            text = f"ESTADO: {estado_global}"
            text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)[0]
            text_x = (combined_view.shape[1] - text_size[0]) // 2
            cv2.putText(combined_view, text, (text_x, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color_text, 3)

            cv2.imshow("Monitor Dual Caracal", combined_view)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        else:
            # IMPRESIÓN EN TERMINAL (Modificado para incluir 3D)
             print(f"Estado Global: {estado_global} | 3D: {coord_3d_str}   ", end="\r")

    stream_left.stop()
    stream_right.stop()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()