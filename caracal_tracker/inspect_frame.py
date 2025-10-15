"""
inspect_frame.py
------------------------------------
Inspecciona un frame específico (porcentaje 0–100) de un video, ejecuta detección
con Ultralytics YOLO y guarda una imagen anotada con las cajas resultantes.

Salida:
    outputs/frames/frame_<percent>.jpg
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

import cv2
from ultralytics import YOLO


def inspect_frame(
    video_path: str,
    frame_percent: float,
    output_dir: str = "outputs/frames",
    model_path: str = "yolov8n.pt",
    conf_thres: float = 0.35,
    imgsz: int = 640,
) -> Optional[str]:
    """
    Ejecuta detección YOLO sobre el frame ubicado en `frame_percent` % del video.

    Parámetros:
        video_path: ruta al archivo de video.
        frame_percent: porcentaje del video a muestrear [0, 100].
        output_dir: carpeta donde se guarda la imagen anotada.
        model_path: ruta o alias del checkpoint YOLO de Ultralytics.
        conf_thres: umbral mínimo de confianza para reportar detecciones.
        imgsz: tamaño de entrada (lado mayor) usado por YOLO.

    Retorna:
        Ruta del archivo de salida si fue exitoso; None si hubo error.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Carga del modelo (Ultralytics selecciona CPU/GPU automáticamente).
    model = YOLO(model_path)

    # Apertura del video.
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: no se pudo abrir el video: {video_path}")
        return None

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1

    # Saturación del porcentaje a rango válido y cálculo del índice destino.
    pct = max(0.0, min(100.0, float(frame_percent)))
    target_frame = int((pct / 100.0) * (total_frames - 1))

    # Posicionamiento y lectura del frame.
    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
    ok, frame = cap.read()
    if not ok or frame is None:
        print(f"Error: no se pudo leer el frame {target_frame}.")
        cap.release()
        return None

    # Inferencia YOLO.
    results = model.predict(frame, imgsz=imgsz, conf=conf_thres, verbose=False)
    res = results[0]  # un solo frame

    # Anotación (Ultralytics proporciona la imagen con cajas via .plot()).
    annotated = res.plot()

    # Persistencia.
    out_path = os.path.join(output_dir, f"frame_{pct:.1f}.jpg")
    cv2.imwrite(out_path, annotated)

    # Resumen de detecciones.
    print(f"Video: {video_path}")
    print(f"Frames totales: {total_frames} | Frame analizado: {target_frame} ({pct:.1f}%)")
    print(f"Salida: {out_path}")
    if getattr(res, "boxes", None) is not None and len(res.boxes) > 0:
        print("Detecciones:")
        for box in res.boxes:
            cls_name = model.names[int(box.cls)]
            conf = float(box.conf)
            print(f" - {cls_name}: {conf:.2f}")
    else:
        print("Sin detecciones por encima del umbral.")

    cap.release()
    return out_path


def _build_parser() -> argparse.ArgumentParser:
    """
    Crea el parser de CLI para ejecutar la inspección desde consola.
    """
    parser = argparse.ArgumentParser(
        description="Inspeccionar un frame específico de un video con YOLO."
    )
    parser.add_argument(
        "--video",
        required=True,
        help="Ruta al video (ej.: videos/caracal_zoo_video.mp4)",
    )
    parser.add_argument(
        "--frame",
        type=float,
        required=True,
        help="Porcentaje del video a inspeccionar (0–100).",
    )
    parser.add_argument(
        "--model",
        default="yolov8n.pt",
        help="Modelo YOLO a usar (ruta o alias de Ultralytics).",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.35,
        help="Umbral de confianza mínimo (default: 0.35).",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Tamaño de entrada para YOLO (default: 640).",
    )
    parser.add_argument(
        "--outdir",
        default="outputs/frames",
        help="Directorio de salida para la imagen anotada.",
    )
    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()
    inspect_frame(
        video_path=args.video,
        frame_percent=args.frame,
        output_dir=args.outdir,
        model_path=args.model,
        conf_thres=args.conf,
        imgsz=args.imgsz,
    )
