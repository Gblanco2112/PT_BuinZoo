
import argparse, os, cv2
from fixed_speciesnet_tracker import (
    DetectorSpeciesNetBatch, TrackerWrapper, Visualizer, VideoProcessor
)

def run_tracker(video_path: str,
                min_conf: float, max_boxes: int, jpeg_quality: int,
                stride: int, max_frames: int | None, start_frame: int,
                batch_size: int, save_max_side: int):
    det = DetectorSpeciesNetBatch(
        min_conf=min_conf,
        only_animals=True,
        max_boxes=max_boxes,
        jpeg_quality=jpeg_quality,
        save_max_side=save_max_side,
        warmup=True
    )
    tracker = TrackerWrapper(max_age=90, n_init=1, ema_alpha=0.35)
    viz = Visualizer(show_trace=True)
    vp = VideoProcessor(detector=det, tracker=tracker, visualizer=viz,
                        output_video_path="outputs/out_speciesnet.mp4",
                        csv_log_path="outputs/speciesnet_log.csv",
                        stride=stride,
                        max_frames=max_frames,
                        start_frame=start_frame,
                        batch_size=batch_size)
    vp.process(video_path)

def inspect_frame(video_path: str, percent: float,
                  min_conf: float, max_boxes: int, jpeg_quality: int,
                  save_max_side: int):
    det = DetectorSpeciesNetBatch(
        min_conf=min_conf,
        only_animals=True,
        max_boxes=max_boxes,
        jpeg_quality=jpeg_quality,
        save_max_side=save_max_side,
        warmup=True
    )
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    idx = int(max(0.0, min(100.0, float(percent))) / 100.0 * (total - 1))
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, frame = cap.read()
    if not ok:
        cap.release(); raise RuntimeError(f"No se pudo leer el frame {idx}")

    dets_per_frame = det.detect_batch([frame])
    dets = dets_per_frame[0] if dets_per_frame else []
    for (x1, y1, x2, y2), score, label in dets:
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0,255,0), 2)
        cv2.putText(frame, f"{label} {score:.2f}", (int(x1), max(15, int(y1)-6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
    os.makedirs("outputs/frame_inspect", exist_ok=True)
    outp = f"outputs/frame_inspect/frame_{percent:.1f}.jpg"
    cv2.imwrite(outp, frame); print(f"✅ Frame guardado en: {outp}")
    cap.release()

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Tracking con SpeciesNet detector_only + DEEPSORT (CPU, batch)")
    ap.add_argument("-t", action="store_true", help="Tracking completo")
    ap.add_argument("-f", type=float, help="Inspeccionar frame al porcentaje indicado (0–100)")
    ap.add_argument("--video", default="videos/caracal_video_01.mp4", help="Ruta del video de entrada")

    ap.add_argument("--min-conf", type=float, default=0.15, help="Umbral mínimo de detección (SpeciesNet)")
    ap.add_argument("--max-boxes", type=int, default=10, help="Máximo de cajas por frame")
    ap.add_argument("--jpeg-quality", type=int, default=90, help="Calidad JPEG temporal (40–100)")
    ap.add_argument("--stride", type=int, default=1, help="Procesar detección cada N frames (1 = todos)")
    ap.add_argument("--max-frames", type=int, default=None, help="Máximo de frames a procesar")
    ap.add_argument("--start-frame", type=int, default=0, help="Frame inicial (índice)")
    ap.add_argument("--batch-size", type=int, default=24, help="Frames por lote para el detector")
    ap.add_argument("--save-max-side", type=int, default=720, help="Redimensiona el frame para el detector (máx. lado)")

    args = ap.parse_args()
    if args.t:
        run_tracker(args.video, args.min_conf, args.max_boxes, args.jpeg_quality,
                    args.stride, args.max_frames, args.start_frame,
                    args.batch_size, args.save_max_side)
    elif args.f is not None:
        inspect_frame(args.video, args.f, args.min_conf, args.max_boxes, args.jpeg_quality,
                      args.save_max_side)
    else:
        print("⚠️ Usa -t (tracking) o -f <porcentaje>")
