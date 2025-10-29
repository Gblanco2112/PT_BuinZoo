"""
caracal_tracker_proxy.py
--------------------------------------
Módulo de detección y tracking del caracal usando YOLO (Ultralytics) + DeepSORT.

Estructura:
- DetectorYOLO: detección por frame (bbox, score, class_name).
- TrackerWrapper: asociación temporal (tracks) con DeepSORT.
- Visualizer: dibujo de cajas/etiquetas y trazo opcional.
- VideoProcessor: orquesta lectura de video, pipeline y persistencia (mp4 + csv).
"""

from __future__ import annotations

import csv
import os
import time
from typing import List, Tuple, Optional, Dict, Protocol

import cv2
import numpy as np
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort


# --------------------------------------------------------------------------------------
# Tipos y constantes
# --------------------------------------------------------------------------------------

BBox = Tuple[float, float, float, float]             # (x1, y1, x2, y2) en píxeles
Detection = Tuple[BBox, float, str]                  # ((x1,y1,x2,y2), conf, class_name)
TrackDict = Dict[str, object]                        # diccionario de datos de un track activo
DEFAULT_PROXY_CLASSES: List[str] = ["cat", "dog", "cow", "elephant"]


# --------------------------------------------------------------------------------------
# Interfaces mínimas (para favorecer mantenibilidad)
# --------------------------------------------------------------------------------------

class Detector(Protocol):
    """Interfaz para detectores basados en frame único."""
    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Ejecuta detección sobre un frame y retorna la lista de detecciones."""


class Tracker(Protocol):
    """Interfaz para trackers multi-objeto."""
    def update(self, detections: List[Detection], frame: np.ndarray) -> List[TrackDict]:
        """Actualiza estados de tracking con las detecciones del frame y retorna tracks confirmados."""


class VisualizerI(Protocol):
    """Interfaz para visualizadores de resultados."""
    def draw(self, frame: np.ndarray, tracks: List[TrackDict], fps: Optional[float] = None) -> np.ndarray:
        """Dibuja información de tracking sobre el frame y devuelve el frame anotado."""


# --------------------------------------------------------------------------------------
# BLOQUE 1: Detector YOLO
# --------------------------------------------------------------------------------------

class DetectorYOLO:
    """
    Detector basado en Ultralytics YOLO.

    Atributos:
        model: modelo YOLO cargado.
        conf_thres: umbral mínimo de confianza.

    Métodos:
        detect(frame): ejecuta inferencia y devuelve detecciones como lista de tuplas.
    """

    def __init__(self, model_path: str = "yolov8n.pt", conf_thres: float = 0.25) -> None:
        print("📦 Cargando modelo YOLO desde", model_path, "...")
        self.model = YOLO(model_path)
        self.conf_thres = conf_thres

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Ejecuta inferencia sobre el frame.

        Retorna:
            Lista de detecciones con formato ((x1,y1,x2,y2), conf, class_name).
        """
        results = self.model.predict(frame, conf=self.conf_thres, verbose=False)
        detections: List[Detection] = []

        for r in results:
            if r.boxes is not None:
                for box in r.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()  # coordenadas absolutas en píxeles
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    cls_name = self.model.names[cls_id]
                    detections.append(((x1, y1, x2, y2), conf, cls_name))
        return detections


# --------------------------------------------------------------------------------------
# BLOQUE 2: Tracker Wrapper (DeepSORT)
# --------------------------------------------------------------------------------------

class TrackerWrapper:
    """
    Adaptador de DeepSORT para seguimiento temporal.

    Atributos:
        tracker: instancia de DeepSort configurada para CPU.
        last_track: último track activo retenido para continuidad visual.
        missing_frames: contador de frames sin detección para retención de caja.

    Métodos:
        update(detections, frame): convierte detecciones a formato del tracker,
        actualiza tracks y aplica retención de caja por breves lapsos sin detección.
    """

    def __init__(self, max_age: int = 50, n_init: int = 1) -> None:
        self.tracker = DeepSort(
            max_age=max_age,
            n_init=n_init,
            embedder='mobilenet',   # embedder interno (CPU)
            embedder_gpu=False,     # CPU
            half=False,             # precisión completa
            max_iou_distance=0.9    # asociación permisiva entre frames contiguos
        )
        self.last_track: Optional[TrackDict] = None
        self.missing_frames: int = 0

    def update(self, detections: List[Detection], frame: np.ndarray) -> List[TrackDict]:
        """
        Actualiza el estado del tracker.

        Parámetros:
            detections: lista de detecciones ((x1,y1,x2,y2), conf, class_name).
            frame: frame actual (BGR).

        Retorna:
            Lista de tracks confirmados en el frame actual.
        """
        if not detections:
            detections = []

        # DeepSORT espera (x1, y1, w, h); se convierte desde (x1, y1, x2, y2).
        converted_dets = []
        for (x1, y1, x2, y2), conf, cls in detections:
            w = x2 - x1
            h = y2 - y1
            converted_dets.append(((float(x1), float(y1), float(w), float(h)), float(conf), cls))

        tracks_ds = self.tracker.update_tracks(converted_dets, frame=frame)
        active_tracks: List[TrackDict] = []

        for track in tracks_ds:
            if not track.is_confirmed():
                continue
            x1, y1, x2, y2 = track.to_ltrb()
            active_tracks.append({
                "track_id": track.track_id,
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
                "class": getattr(track, "cls", "caracal"),
                "score": getattr(track, "det_conf", 0.0)
            })

        # Retención de la última caja durante un corto lapso sin detección
        if active_tracks:
            self.last_track = active_tracks[0]
            self.missing_frames = 0
        else:
            self.missing_frames += 1
            if self.last_track and self.missing_frames < 10:
                active_tracks = [self.last_track]
            else:
                self.last_track = None

        return active_tracks


# --------------------------------------------------------------------------------------
# BLOQUE 3: Visualizador
# --------------------------------------------------------------------------------------

class Visualizer:
    """
    Visualizador de tracks sobre frames.

    Atributos:
        traces: historial de centroides por track_id para trazo reciente.
        show_trace: habilita/deshabilita dibujo de trayectorias.

    Métodos:
        draw(frame, tracks, fps): dibuja cajas, etiquetas y trazo; también FPS opcional.
    """

    def __init__(self, show_trace: bool = True) -> None:
        self.traces: Dict[object, List[Tuple[int, int]]] = {}
        self.show_trace = show_trace

    def _color_for_id(self, track_id: object) -> Tuple[int, int, int]:
        """Genera un color determinista para el ID dado."""
        if isinstance(track_id, str):
            seed_value = abs(hash(track_id)) % (2**32)
        else:
            seed_value = int(track_id) % (2**32)
        rng = np.random.default_rng(seed_value)
        return tuple(int(x) for x in rng.integers(0, 255, 3))

    def draw(self, frame: np.ndarray, tracks: List[TrackDict], fps: Optional[float] = None) -> np.ndarray:
        """
        Dibuja las cajas y etiquetas de los tracks sobre el frame.

        Parámetros:
            frame: imagen BGR (se modifica in-place).
            tracks: lista de tracks activos.
            fps: valor estimado de FPS para sobreimpresión opcional.

        Retorna:
            El mismo frame con anotaciones para su escritura/visualización.
        """
        for t in tracks:
            x1, y1, x2, y2 = t['bbox']
            tid = t['track_id']
            color = self._color_for_id(tid)
            label = f"Caracal ID {tid}"
            if t.get('score'):
                label += f" ({t['score']:.2f})"

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            if self.show_trace:
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                self.traces.setdefault(tid, []).append((cx, cy))
                pts = self.traces[tid][-30:]
                for i in range(1, len(pts)):
                    cv2.line(frame, pts[i - 1], pts[i], color, 2)

        if fps:
            cv2.putText(frame, f"FPS: {fps:.1f}", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        return frame


# --------------------------------------------------------------------------------------
# BLOQUE 4: Video Processor
# --------------------------------------------------------------------------------------

class VideoProcessor:
    """
    Orquestador del pipeline de video.

    Responsabilidades:
        - Leer frames de la fuente de video.
        - Ejecutar detección, actualizar tracking y dibujar resultados.
        - Guardar el video anotado y un CSV con la información por frame.

    Constructor:
        detector: instancia que cumple Detector.
        tracker: instancia que cumple Tracker.
        visualizer: instancia que cumple VisualizerI.
        proxy_classes: lista de clases “proxy” del caracal (conservada por compatibilidad).
        output_video_path: ruta del mp4 anotado.
        csv_log_path: ruta del CSV de salida.

    Método principal:
        process(video_path): ejecuta el pipeline completo y retorna dict con conteos básicos.
    """

    def __init__(self,
                 detector: Detector,
                 tracker: Tracker,
                 visualizer: VisualizerI,
                 proxy_classes: Optional[List[str]] = None,
                 output_video_path: str = "outputs/out_caracal.mp4",
                 csv_log_path: str = "outputs/caracal_log.csv") -> None:

        self.detector = detector
        self.tracker = tracker
        self.visualizer = visualizer
        self.proxy_classes = proxy_classes or DEFAULT_PROXY_CLASSES
        self.output_video_path = output_video_path
        self.csv_log_path = csv_log_path

        os.makedirs(os.path.dirname(self.output_video_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.csv_log_path), exist_ok=True)

    def process(self, video_path: str) -> Dict[str, int]:
        """
        Ejecuta el pipeline sobre el video de entrada.

        Parámetros:
            video_path: ruta al archivo de video.

        Retorna:
            Diccionario con 'frames_processed' para verificación rápida.
        """
        print(f"🎥 Procesando video: {video_path}")
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"No se pudo abrir el video: {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"Resolución: {width}x{height} @ {fps:.1f} FPS | Frames totales: {total_frames}")
        print("-" * 62)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(self.output_video_path, fourcc, fps, (width, height))

        with open(self.csv_log_path, "w", newline="") as csv_fp:
            csv_writer = csv.writer(csv_fp)
            csv_writer.writerow(["frame", "track_id", "x1", "y1", "x2", "y2", "class", "score"])

            frame_idx = 0
            start_time = time.time()

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                detections = self.detector.detect(frame)
                tracks = self.tracker.update(detections, frame)

                elapsed = time.time() - start_time
                fps_now = (frame_idx + 1) / elapsed if elapsed > 0 else 0.0

                frame_out = self.visualizer.draw(frame, tracks, fps=fps_now)
                writer.write(frame_out)

                for t in tracks:
                    x1, y1, x2, y2 = t["bbox"]  # type: ignore[index]
                    csv_writer.writerow([
                        frame_idx, t["track_id"], x1, y1, x2, y2,
                        t.get("class", "caracal"), t.get("score", 0.0)
                    ])

                frame_idx += 1

        cap.release()
        writer.release()

        print(f"✅ Tracking completado: {{'frames_processed': {frame_idx}}}")
        print(f"🎬 Video: {self.output_video_path}")
        print(f"🧾 CSV  : {self.csv_log_path}")
        return {"frames_processed": frame_idx}
