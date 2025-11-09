import argparse
import os
import cv2
from speciesnet_tracker import (
    DetectorSpeciesNetBatch,
    TrackerWrapper,
    Visualizer,
    VideoProcessor,
)

def run_tracker(
    video_path: str,
    min_conf: float,
    max_boxes: int,
    jpeg_quality: int,
    stride: int,
    max_frames: int | None,
    start_frame: int,
    batch_size: int,
    save_max_side: int,
    # nuevos parámetros
    primary_only: bool,
    lag: int,
    min_persist: int,
    max_gap: int,
    startup_suppress: int,
) -> None:
    det = DetectorSpeciesNetBatch(
        min_conf=min_conf,
        only_animals=True,
        max_boxes=max_boxes,
        jpeg_quality=jpeg_quality,
        save_max_side=save_max_side,
        cli_extra_args=[],
        warmup=True,
    )
    tracker = TrackerWrapper(max_age=90, n_init=1, ema_alpha=0.35, only_updated=True)
    viz = Visualizer(show_trace=True)

    vp = VideoProcessor(
        detector=det,
        tracker=tracker,
        visualizer=viz,
        output_video_path="outputs/out_speciesnet.mp4",
        csv_log_path="outputs/speciesnet_log.csv",
        stride=stride,
        max_frames=max_frames,
        start_frame=start_frame,
        batch_size=batch_size,
        # smoothing + una sola caja
        primary_only=primary_only,
        lag=lag,
        min_persist=min_persist,
        max_gap=max_gap,
        startup_suppress=startup_suppress,
        # filtros ya existentes
        min_area_ratio=0.001,
        edge_pad=2,
        use_motion_gate=True,
        motion_min_ratio=0.02,
        motion_strong_conf=0.6,
    )
    vp.process(video_path)

def inspect_frame(
    video_path: str,
    percent: float,
    min_conf: float,
    max_boxes: int,
    jpeg_quality: int,
    save_max_side: int,
) -> None:
    det = DetectorSpeciesNetBatch(
        min_conf=min_conf,
        only_animals=True,
        max_boxes=max_boxes,
        jpeg_quality=jpeg_quality,
        save_max_side=save_max_side,
        cli_extra_args=[],
        warmup=True,
    )

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    idx = int(max(0.0, min(100.0, float(percent))) / 100.0 * (total - 1))
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, frame = cap.read()
    if not ok:
        cap.release()
        raise RuntimeError(f"No se pudo leer el frame {idx}")

    dets = det.detect_batch([frame])[0]
    for (x1, y1, x2, y2), score, label in dets:
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
        cv2.putText(
            frame,
            f"{label} {score:.2f}",
            (int(x1), max(15, int(y1) - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
        )

    os.makedirs("outputs/frame_inspect", exist_ok=True)
    outp = f"outputs/frame_inspect/frame_{percent:.1f}.jpg"
    cv2.imwrite(outp, frame)
    print(f"✅ Frame guardado en: {outp}")
    cap.release()

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Tracking con SpeciesNet (detector_only por lotes) + DeepSORT"
    )
    ap.add_argument("-t", action="store_true", help="Tracking completo del video")
    ap.add_argument("-f", type=float, help="Inspeccionar frame (%)")
    ap.add_argument("--video", default="videos/caracal_video_02.mp4")

    # rendimiento / calidad
    ap.add_argument("--min-conf", type=float, default=0.15)
    ap.add_argument("--max-boxes", type=int, default=10)
    ap.add_argument("--jpeg-quality", type=int, default=90)
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--max-frames", type=int, default=None)
    ap.add_argument("--start-frame", type=int, default=0)
    ap.add_argument("--batch-size", type=int, default=48)
    ap.add_argument("--save-max-side", type=int, default=960)

    # NUEVOS: una sola caja estable + pequeño delay
    ap.add_argument("--primary-only", action="store_true", default=True,
                    help="Dibuja una única caja (track principal) estable")
    ap.add_argument("--lag", type=int, default=6,
                    help="Retardo fijo (frames) para alisar con futuro cercano")
    ap.add_argument("--min-persist", type=int, default=8,
                    help="Frames mínimos para ‘consolidar’ un nuevo track principal")
    ap.add_argument("--max-gap", type=int, default=10,
                    help="Frames sin detección que se permite mantener la caja anterior")
    ap.add_argument("--startup-suppress", type=int, default=15,
                    help="Frames iniciales en los que se ignoran detecciones débiles")

    args = ap.parse_args()

    if args.t:
        run_tracker(
            args.video,
            args.min_conf,
            args.max_boxes,
            args.jpeg_quality,
            args.stride,
            args.max_frames,
            args.start_frame,
            args.batch_size,
            args.save_max_side,
            args.primary_only,
            args.lag,
            args.min_persist,
            args.max_gap,
            args.startup_suppress,
        )
    elif args.f is not None:
        inspect_frame(
            args.video,
            args.f,
            args.min_conf,
            args.max_boxes,
            args.jpeg_quality,
            args.save_max_side,
        )
    else:
        print("⚠️ Usa -t (tracking) o -f <porcentaje>")
