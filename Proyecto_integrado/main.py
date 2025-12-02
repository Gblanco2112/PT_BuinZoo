import argparse
import cv2
import sys
import numpy as np
from pathlib import Path
from ultralytics import YOLO

# Importamos tu lógica
from activity_logic import ActivityCheck

# --- CONFIGURACIÓN DE CÁMARAS (FIJA) ---
# Channel 2 a la izquierda, Channel 1 a la derecha
RTSP_LEFT  = "rtsp://view:vieW.,star3250@190.8.125.219:554/cam/realmonitor?channel=2&subtype=0"
RTSP_RIGHT = "rtsp://view:vieW.,star3250@190.8.125.219:554/cam/realmonitor?channel=1&subtype=0"

def parse_arguments():
    parser = argparse.ArgumentParser(description="Detector de Conducta de Caracal - Dual Cam")
    
    # Ya no pedimos sources, solo opciones de visualización y modelo
    parser.add_argument("--view", action="store_true",
                        help="Activar visualización combinada en ventana")
    
    parser.add_argument("--weights", type=str, default="yolo_model/best.pt",
                        help="Ruta al archivo de pesos .pt")
    
    return parser.parse_args()

def process_camera(model, frame, checker, cam_name="Cam"):
    """
    Procesa un frame: detecta con YOLO (en GPU) y actualiza su checker.
    """
    # Tracking usando la GPU (device=0)
    results = model.track(
        frame, 
        persist=True, 
        verbose=False, 
        conf=0.5, 
        iou=0.5,
        tracker="bytetrack.yaml",
        max_det=1,
        device=0  # <--- FUERZA EL USO DE GPU
    )

    pos_actual = np.array([0.0, 0.0])
    bbox = None

    # Extraer datos si hay detección
    if results[0].boxes is not None and len(results[0].boxes) > 0:
        box = results[0].boxes[0]
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        pos_actual = np.array([cx, cy])
        bbox = (int(x1), int(y1), int(x2), int(y2))

    # Actualizar lógica de ESTA cámara
    estado_crudo = checker.estado(pos_actual)
    checker.update_pos(pos_actual)
    estado_final = checker.estado_estable(estado_crudo)
    
    return bbox, estado_final, pos_actual

def fusionar_estados(est1, est2):
    """
    Prioridad: Pacing > Movimiento > Quieto > N/A
    """
    estados = [est1, est2]
    
    if "Pacing" in estados:
        return "Pacing"
    if "Movimiento" in estados:
        return "Movimiento"
    if "Quieto" in estados:
        return "Quieto"
    
    return "N/A"

def main():
    args = parse_arguments()
    
    # 1. Cargar Modelo
    weights_path = Path(args.weights)
    if not weights_path.exists():
        print(f"Error: No se encontraron los pesos en {weights_path}")
        sys.exit(1)
        
    print(f"Cargando modelo YOLO: {weights_path}")
    # Se carga el modelo. Al usar device=0 en el loop, se moverá a GPU automáticamente.
    model = YOLO(str(weights_path))

    # 2. Inicializar Cámaras
    print(f"Conectando a CAM IZQUIERDA (Ch2): {RTSP_LEFT}")
    cap_left = cv2.VideoCapture(RTSP_LEFT)
    
    print(f"Conectando a CAM DERECHA (Ch1): {RTSP_RIGHT}")
    cap_right = cv2.VideoCapture(RTSP_RIGHT)

    if not cap_left.isOpened() or not cap_right.isOpened():
        print("Error: No se pudo conectar a una de las cámaras. Verifica la red.")
        sys.exit(1)

    # Obtenemos FPS de referencia (usamos la izquierda como base)
    fps = cap_left.get(cv2.CAP_PROP_FPS)
    if fps == 0 or np.isnan(fps): fps = 20
    
    # 3. Inicializar Lógica (Dos checkers independientes)
    checker_left = ActivityCheck(fm=int(fps))
    checker_right = ActivityCheck(fm=int(fps))

    print(f"Sistema iniciado. FM={int(fps)}. Presiona 'q' en la ventana para salir.")
    
    # Configurar ventana si se solicita
    if args.view:
        cv2.namedWindow("Monitor Dual Caracal", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Monitor Dual Caracal", 1800, 600)

    while True:
        # Leer frames
        ret_l, frame_left = cap_left.read()
        ret_r, frame_right = cap_right.read()

        if not ret_l or not ret_r:
            print("Pérdida de señal o stream incompleto. Reintentando...")
            # Aquí podrías poner lógica de reconexión si fuera crítico, 
            # por ahora rompemos el loop.
            break

        # Redimensionar la derecha para que coincida con la izquierda en altura si difieren
        if frame_left.shape != frame_right.shape:
            frame_right = cv2.resize(frame_right, (frame_left.shape[1], frame_left.shape[0]))

        # --- PROCESAMIENTO (Izquierda = Ch2, Derecha = Ch1) ---
        bbox_l, estado_l, _ = process_camera(model, frame_left, checker_left)
        bbox_r, estado_r, _ = process_camera(model, frame_right, checker_right)

        # --- FUSIÓN ---
        estado_global = fusionar_estados(estado_l, estado_r)

        # --- VISUALIZACIÓN ---
        if args.view:
            # Dibujos Izquierda (Ch2)
            if bbox_l:
                cv2.rectangle(frame_left, (bbox_l[0], bbox_l[1]), (bbox_l[2], bbox_l[3]), (0, 255, 0), 2)
                cv2.putText(frame_left, f"CAM 2 (IZQ): {estado_l}", (bbox_l[0], bbox_l[1]-10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                 cv2.putText(frame_left, "Sin deteccion", (30, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            # Dibujos Derecha (Ch1)
            if bbox_r:
                cv2.rectangle(frame_right, (bbox_r[0], bbox_r[1]), (bbox_r[2], bbox_r[3]), (0, 255, 0), 2)
                cv2.putText(frame_right, f"CAM 1 (DER): {estado_r}", (bbox_r[0], bbox_r[1]-10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                 cv2.putText(frame_right, "Sin deteccion", (30, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            # Unir Lado a Lado: [ Izquierda (Ch2) | Derecha (Ch1) ]
            combined_view = cv2.hconcat([frame_left, frame_right])

            # Panel Superior de Estado Global
            # Barra negra
            cv2.rectangle(combined_view, (0, 0), (combined_view.shape[1], 60), (0,0,0), -1)
            
            # Color del texto según estado
            color_text = (200, 200, 200) # Gris por defecto
            if estado_global == "Quieto": color_text = (0, 255, 0)       # Verde
            elif estado_global == "Movimiento": color_text = (0, 165, 255) # Naranja
            elif estado_global == "Pacing": color_text = (0, 0, 255)       # Rojo

            text = f"ESTADO GLOBAL: {estado_global}"
            text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)[0]
            text_x = (combined_view.shape[1] - text_size[0]) // 2
            
            cv2.putText(combined_view, text, (text_x, 45), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, color_text, 3)

            cv2.imshow("Monitor Dual Caracal", combined_view)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        else:
            # Output simple para consola si no hay vista
            print(f"Estado Global: {estado_global} | (L: {estado_l} R: {estado_r})", end="\r")

    cap_left.release()
    cap_right.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()