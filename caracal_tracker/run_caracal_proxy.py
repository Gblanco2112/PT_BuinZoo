"""
run_caracal_proxy.py
------------------------------------
CLI para ejecutar:
- Tracking de video completo (-t)
- Inspección de un frame específico por porcentaje (-f <0-100>)
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

import cv2
from caracal_tracker_proxy import DetectorYOLO, TrackerWrapper, Visualizer, VideoProcessor


# ----------------------------------------------------------
# Función: Tracking completo del video
# ----------------------------------------------------------
def run_tracker(video_path: str) -> None:
    """
    Ejecuta el pipeline de tracking sobre el video indicado y persiste:
    - MP4 anotado en outputs/out_caracal.mp4
    - CSV en outputs/caracal_log.csv

    Parámetros:
        video_path: ruta del archivo de video de entrada.
    """
    print("🟢 Modo tracking iniciado...")

    detector = DetectorYOLO(model_path="yolov8n.pt", conf_thres=0.4)
    tracker = TrackerWrapper()
    visualizer = Visualizer(show_trace=True)

    processor = VideoProcessor(detector, tracker, visualizer)
    processor.process(video_path)


# ----------------------------------------------------------
# Función: Inspección de frame específico
# ----------------------------------------------------------
def inspect_frame(video_path: str, percent: float) -> None:
    """
    Inspecciona el frame ubicado en 'percent' % de la duración del video,
    ejecuta detección YOLO y guarda la imagen anotada.

    Parámetros:
        video_path: ruta del archivo de video de entrada.
        percent: porcentaje [0, 100] de la duración del video.
    """
    print(f"🟡 Modo inspección de frame al {percent}% del video...")

    detector = DetectorYOLO(model_path="yolov8n.pt", conf_thres=0.4)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    # Saturación del porcentaje a rango válido
    percent_clamped = max(0.0, min(100.0, percent))
    frame_idx = int((percent_clamped / 100.0) * (total_frames - 1))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)

    ret, frame = cap.read()
    if not ret:
        cap.release()
        raise RuntimeError(f"No se pudo leer el frame {frame_idx}")

    detections = detector.detect(frame)

    # Dibujo de detecciones sobre el frame
    for (x1, y1, x2, y2), conf, cls_name in detections:
        color = (0, 255, 0)
        label = f"{cls_name} {conf:.2f}"
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
        cv2.putText(frame, label, (int(x1), int(y1) - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    os.makedirs("outputs/frame_inspect", exist_ok=True)
    out_path = f"outputs/frame_inspect/frame_{percent_clamped}.jpg"
    cv2.imwrite(out_path, frame)
    print(f"✅ Frame guardado en: {out_path}")

    cap.release()


# ----------------------------------------------------------
# MAIN
# ----------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Caracal Tracker Proxy CLI: -t para tracking, -f <porcentaje> para inspección de frame."
    )
    parser.add_argument(
        "-t",
        action="store_true",
        help="Ejecutar tracking completo del video"
    )
    parser.add_argument(
        "-f",
        type=float,
        help="Inspeccionar frame al porcentaje especificado del video (ej: 5 para 5%)"
    )
    parser.add_argument(
        "--video",
        type=str,
        default="videos/caracal_zoo_video.mp4",
        help="Ruta del video de entrada"
    )

    args = parser.parse_args()

    if args.t:
        run_tracker(args.video)
    elif args.f is not None:
        inspect_frame(args.video, args.f)
    else:
        print("⚠️  Debe indicarse una opción:")
        print("   -t               : Ejecutar tracking completo")
        print("   -f <porcentaje>  : Inspeccionar un frame específico del video")
