
"""
speciesnet_tracker.py (patched)
----------------------------------------------------------
Fixes:
- Robust bbox parsing across xyxy/xywh + normalized/absolute.
- Deterministic mapping from prediction filepaths to buffer indices (no ordering mismatch).
- Stride now based on ORIGINAL frame index (not just "processed" counter).
- Visualizer.draw works on a copy to avoid any in-place writer glitches.
"""

from __future__ import annotations
from typing import List, Tuple, Optional, Dict
import os, sys, json, tempfile, subprocess
from pathlib import Path

import time
import csv
import cv2
import numpy as np
from deep_sort_realtime.deepsort_tracker import DeepSort

BBox = Tuple[float, float, float, float]
Detection = Tuple[BBox, float, str]
TrackDict = Dict[str, object]

# ------------------ Utilidades ------------------ #
def _resize_keep_aspect(img: np.ndarray, max_side: int) -> tuple[np.ndarray, float, float]:
    h, w = img.shape[:2]
    if max(w, h) <= max_side:
        return img, 1.0, 1.0
    if w >= h:
        new_w = max_side
        new_h = int(round(h * (new_w / w)))
    else:
        new_h = max_side
        new_w = int(round(w * (new_h / h)))
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    fx = w / new_w
    fy = h / new_h
    return resized, fx, fy

def _basename(path: str) -> str:
    return os.path.basename(path or "")

def _to_xyxy_abs(b, W, H, fmt_hint: Optional[str] = None) -> Tuple[int, int, int, int]:
    """
    Convert a bbox into absolute xyxy (pixels) robustly.
    Accepts:
      - normalized xyxy in [0..1]
      - normalized xywh (top-left anchored) in [0..1]
      - absolute xyxy in pixels
      - absolute xywh in pixels
    We infer by value ranges and monotonicity, unless a fmt_hint is given.
    """
    b = [float(x) for x in (b or [])]
    if len(b) != 4:
        return 0, 0, 0, 0

    def _clip(x1,y1,x2,y2):
        x1 = max(0, min(W - 1, int(round(x1))))
        y1 = max(0, min(H - 1, int(round(y1))))
        x2 = max(0, min(W - 1, int(round(x2))))
        y2 = max(0, min(H - 1, int(round(y2))))
        if x2 < x1: x1, x2 = x2, x1
        if y2 < y1: y1, y2 = y2, y1
        return x1, y1, x2, y2

    # If explicitly hinted, honor it.
    if fmt_hint == "xyxy_norm":
        return _clip(b[0]*W, b[1]*H, b[2]*W, b[3]*H)
    if fmt_hint == "xywh_norm":
        return _clip(b[0]*W, b[1]*H, (b[0]+b[2])*W, (b[1]+b[3])*H)
    if fmt_hint == "xyxy_abs":
        return _clip(b[0], b[1], b[2], b[3])
    if fmt_hint == "xywh_abs":
        return _clip(b[0], b[1], b[0]+b[2], b[1]+b[3])

    # Try to infer.
    maxv = max(abs(v) for v in b)
    is_norm = maxv <= 1.5  # allow a bit of headroom
    x1, y1, z1, z2 = b

    # If z1>1 and z2>1 and z1> x1 etc. it likely is absolute xyxy
    if (not is_norm) and (z1 > x1) and (z2 > y1):
        return _clip(x1, y1, z1, z2)

    # If looks like absolute xywh (w,h positive but not coords)
    if (not is_norm) and (z1 >= 0) and (z2 >= 0) and (x1 <= W and y1 <= H):
        return _clip(x1, y1, x1 + z1, y1 + z2)

    # Normalized cases
    if is_norm and (z1 > x1) and (z2 > y1):
        return _clip(x1 * W, y1 * H, z1 * W, z2 * H)
    # assume xywh normalized
    return _clip(x1 * W, y1 * H, (x1 + z1) * W, (y1 + z2) * H)

# ------------------ Detector (SpeciesNet detector_only, BATCH) ------------------ #
class DetectorSpeciesNetBatch:
    def __init__(
        self,
        min_conf: float = 0.15,
        only_animals: bool = True,
        max_boxes: int = 10,
        jpeg_quality: int = 90,
        save_max_side: int = 720,
        cli_extra_args: Optional[List[str]] = None,
        warmup: bool = False
    ):
        self.min_conf = float(min_conf)
        self.only_animals = bool(only_animals)
        self.max_boxes = int(max_boxes)
        self.jpeg_quality = int(np.clip(jpeg_quality, 40, 100))
        self.save_max_side = int(max(160, save_max_side))
        self.cli_extra_args = list(cli_extra_args or [])

        self._tmp_root = Path(tempfile.mkdtemp(prefix="sn_det_batch_"))
        self._frames_dir = self._tmp_root / "frames"
        self._frames_dir.mkdir(parents=True, exist_ok=True)
        self._pred_json = str(self._tmp_root / "predictions.json")

        if warmup:
            self._warmup_once()

    def _run_cli(self) -> None:
        cmd = [
            sys.executable, "-m", "speciesnet.scripts.run_model",
            "--folders", str(self._frames_dir),
            "--predictions_json", self._pred_json,
            "--detector_only",
        ] + self.cli_extra_args

        res = subprocess.run(cmd, text=True, capture_output=True)
        if res.returncode != 0:
            print("❌ SpeciesNet CLI falló:")
            if res.stderr:
                print("---- STDERR ----")
                print(res.stderr)
            if res.stdout:
                print("---- STDOUT ----")
                print(res.stdout)
            raise RuntimeError(f"speciesnet.scripts.run_model returned code {res.returncode}")

    def _warmup_once(self) -> None:
        tiny = np.zeros((8, 8, 3), dtype=np.uint8)
        try:
            if os.path.isfile(self._pred_json):
                os.remove(self._pred_json)
        except Exception:
            pass
        for f in self._frames_dir.glob("frame_*.jpg"):
            try: f.unlink()
            except Exception: pass
        frame_path = self._frames_dir / "frame_00000000.jpg"
        cv2.imwrite(str(frame_path), tiny, [cv2.IMWRITE_JPEG_QUALITY, 80])
        try:
            self._run_cli()
        except Exception as e:
            print(f"[warmup] Aviso: {e}")

    def detect_batch(self, frames: List[np.ndarray]) -> List[List[Detection]]:
        try:
            if os.path.isfile(self._pred_json):
                os.remove(self._pred_json)
        except Exception:
            pass
        for f in self._frames_dir.glob("frame_*.jpg"):
            try: f.unlink()
            except Exception: pass

        # guardar batch redimensionado + guardar factores de escala
        scales = []  # [(fx, fy, save_w, save_h, orig_w, orig_h)]
        index_to_name = {}
        for i, img in enumerate(frames):
            orig_h, orig_w = img.shape[:2]
            img_small, fx, fy = _resize_keep_aspect(img, self.save_max_side)
            save_h, save_w = img_small.shape[:2]
            name = f"frame_{i:08d}.jpg"
            p = self._frames_dir / name
            cv2.imwrite(str(p), img_small, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
            scales.append((fx, fy, save_w, save_h, orig_w, orig_h))
            index_to_name[i] = name  # stable mapping

        self._run_cli()

        with open(self._pred_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Canonicalize predictions as a dict keyed by basename to avoid any ordering issues
        items = []
        if isinstance(data, dict):
            items = data.get("predictions") or data.get("images") or []
        elif isinstance(data, list):
            items = data
        # Map by basename
        pred_by_name = {}
        for it in items:
            fp = str(it.get("filepath") or it.get("file") or "")
            pred_by_name[_basename(fp)] = it

        out: List[List[Detection]] = [[] for _ in range(len(frames))]
        for idx_item in range(len(frames)):
            name = index_to_name[idx_item]
            it = pred_by_name.get(name, {})
            dets = it.get("detections") or it.get("objects") or it.get("boxes") or []
            fx, fy, save_w, save_h, orig_w, orig_h = scales[idx_item]
            this_list: List[Detection] = []

            for d in dets:
                score = float(d.get("score") or d.get("confidence") or d.get("conf") or 0.0)
                if score < self.min_conf:
                    continue

                if self.only_animals:
                    lab = (d.get("label") or "")
                    cat = (d.get("category") or "")
                    is_animal = (isinstance(lab, str) and lab.lower() == "animal") or (str(cat) == "1")
                    if not is_animal:
                        continue

                bbox = d.get("bbox") or d.get("box") or d.get("bbox_xyxy")
                if not bbox or len(bbox) != 4:
                    continue

                # provide a hint if key says xyxy
                hint = None
                if "bbox_xyxy" in d:
                    hint = "xyxy_norm"  # most common from detector_only
                x1s, y1s, x2s, y2s = _to_xyxy_abs(bbox, save_w, save_h, fmt_hint=hint)
                # remap a resolución original
                x1 = int(round(x1s * fx)); y1 = int(round(y1s * fy))
                x2 = int(round(x2s * fx)); y2 = int(round(y2s * fy))
                x1 = max(0, min(orig_w - 1, x1)); x2 = max(0, min(orig_w - 1, x2))
                y1 = max(0, min(orig_h - 1, y1)); y2 = max(0, min(orig_h - 1, y2))

                this_list.append(((float(x1), float(y1), float(x2), float(y2)), score, "animal"))

            this_list.sort(key=lambda t: t[1], reverse=True)
            out[idx_item] = this_list[: self.max_boxes]

        return out

# ------------------ Tracker (DeepSORT + EMA) ------------------ #
class TrackerWrapper:
    def __init__(self, max_age: int = 60, n_init: int = 1, ema_alpha: float = 0.35) -> None:
        self.tracker = DeepSort(
            max_age=max_age,
            n_init=n_init,
            embedder='mobilenet',
            embedder_gpu=False,
            half=False,
            max_iou_distance=0.9
        )
        self.ema_alpha = float(ema_alpha)
        self._ema: Dict[int, np.ndarray] = {}
        self.last_track: Optional[TrackDict] = None
        self.missing_frames: int = 0

    def update(self, detections: List[Detection], frame: np.ndarray) -> List[TrackDict]:
        dets_xywh = []
        for (x1, y1, x2, y2), conf, cls in detections:
            w = x2 - x1
            h = y2 - y1
            dets_xywh.append(((float(x1), float(y1), float(w), float(h)), float(conf), cls))

        tracks_ds = self.tracker.update_tracks(dets_xywh, frame=frame)
        active: List[TrackDict] = []

        for tr in tracks_ds:
            if not tr.is_confirmed():
                continue
            x1, y1, x2, y2 = map(float, tr.to_ltrb())
            tid = int(tr.track_id)

            new_bbox = np.array([x1, y1, x2, y2], dtype=np.float32)
            prev = self._ema.get(tid, new_bbox)
            smoothed = (1.0 - self.ema_alpha) * prev + self.ema_alpha * new_bbox
            self._ema[tid] = smoothed
            sx1, sy1, sx2, sy2 = smoothed.astype(int).tolist()

            active.append({
                "track_id": tid,
                "bbox": [sx1, sy1, sx2, sy2],
                "class": getattr(tr, "cls", "animal"),
                "score": getattr(tr, "det_conf", 0.0)
            })

        if active:
            self.last_track = active[0]; self.missing_frames = 0
        else:
            self.missing_frames += 1
            if self.last_track and self.missing_frames < 10:
                active = [self.last_track]
            else:
                self.last_track = None
        return active

# ------------------ Visualizador ------------------ #
class Visualizer:
    def __init__(self, show_trace: bool = True) -> None:
        self.traces: Dict[int, List[Tuple[int, int]]] = {}
        self.show_trace = show_trace

    def _color(self, tid: int) -> Tuple[int, int, int]:
        rng = np.random.default_rng(int(tid) % (2**32))
        return tuple(int(x) for x in rng.integers(0, 255, 3))

    def draw(self, frame: np.ndarray, tracks: List[TrackDict], fps: Optional[float] = None) -> np.ndarray:
        # Work on a copy to avoid any surprises with writer/backends
        out = frame.copy()
        for t in tracks:
            x1, y1, x2, y2 = t["bbox"]
            tid = t["track_id"]
            color = self._color(tid)
            label = f"{t.get('class','animal')} ID {tid}"
            if t.get("score"):
                label += f" ({t['score']:.2f})"

            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            cv2.putText(out, label, (x1, max(15, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            if self.show_trace:
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                self.traces.setdefault(tid, []).append((cx, cy))
                pts = self.traces[tid][-30:]
                for i in range(1, len(pts)):
                    cv2.line(out, pts[i - 1], pts[i], color, 2)

        if fps:
            cv2.putText(out, f"FPS: {fps:.1f}", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        return out

# ------------------ Procesador de Video (usa lotes) ------------------ #
class VideoProcessor:
    def __init__(self,
                 detector: DetectorSpeciesNetBatch,
                 tracker: TrackerWrapper,
                 visualizer: Visualizer,
                 output_video_path: str = "outputs/out_speciesnet.mp4",
                 csv_log_path: str = "outputs/speciesnet_log.csv",
                 stride: int = 1,
                 max_frames: Optional[int] = None,
                 start_frame: int = 0,
                 batch_size: int = 24) -> None:
        self.detector = detector
        self.tracker = tracker
        self.visualizer = visualizer
        self.output_video_path = output_video_path
        self.csv_log_path = csv_log_path
        self.stride = max(1, int(stride))
        self.max_frames = max_frames if (max_frames is None or max_frames > 0) else None
        self.start_frame = max(0, int(start_frame))
        self.batch_size = max(1, int(batch_size))
        os.makedirs(os.path.dirname(self.output_video_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.csv_log_path), exist_ok=True)

    def process(self, video_path: str) -> Dict[str, int]:
        print(f"🎥 Procesando: {video_path} | stride={self.stride} | start_frame={self.start_frame} "
              f"| max_frames={self.max_frames} | batch_size={self.batch_size}")
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"No se pudo abrir el video: {video_path}")

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"Resolución: {W}x{H} @ {fps:.1f} FPS | Frames: {total}")
        print("-" * 62)

        if self.start_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(self.start_frame, max(0, total - 1)))

        remaining = max(0, total - self.start_frame)
        total_to_process = min(self.max_frames, remaining) if (self.max_frames is not None) else remaining
        _print_progress(0, total_to_process, prefix="Processing")

        writer = cv2.VideoWriter(self.output_video_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
        with open(self.csv_log_path, "w", newline="") as csv_fp:
            csvw = csv.writer(csv_fp)
            csvw.writerow(["frame", "track_id", "x1", "y1", "x2", "y2", "class", "score"])

            processed = 0
            idx = int(cap.get(cv2.CAP_PROP_POS_FRAMES))  # índice real del video
            t0 = time.time()

            frames_buf: List[np.ndarray] = []
            idx_buf: List[int] = []

            def process_buffer():
                nonlocal processed, idx
                if not frames_buf:
                    return
                dets_all = self.detector.detect_batch(frames_buf)
                for i, frame in enumerate(frames_buf):
                    if processed >= total_to_process:
                        break
                    # stride based on ORIGINAL frame index, stable across buffers
                    if ((idx_buf[i] - self.start_frame) % self.stride) == 0:
                        dets = dets_all[i]
                    else:
                        dets = []
                    tracks = self.tracker.update(dets, frame)
                    fps_now = (processed + 1) / max(1e-6, (time.time() - t0))
                    out = self.visualizer.draw(frame, tracks, fps=fps_now)
                    writer.write(out)
                    for t in tracks:
                        x1, y1, x2, y2 = t["bbox"]
                        csvw.writerow([idx_buf[i], t["track_id"], x1, y1, x2, y2,
                                       t.get("class", "animal"), t.get("score", 0.0)])
                    processed += 1
                    _print_progress(processed, total_to_process, prefix="Processing")

                if idx_buf:
                    idx = idx_buf[-1] + 1
                frames_buf.clear()
                idx_buf.clear()

            while True:
                if processed >= total_to_process:
                    break
                ok, frame = cap.read()
                if not ok:
                    process_buffer()
                    break

                # ensure frame is continuous and 3-channel BGR
                if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

                frames_buf.append(frame)
                idx_buf.append(idx)

                if len(frames_buf) >= self.batch_size:
                    process_buffer()

                idx += 1

            _print_progress(total_to_process, total_to_process, prefix="Processing")

        cap.release()
        writer.release()
        print(f"✅ Tracking completado: {{'frames_processed': {processed}}}")
        print(f"🎬 Video: {self.output_video_path}")
        print(f"🧾 CSV  : {self.csv_log_path}")
        return {"frames_processed": processed}


def _print_progress(frames_done: int, total: int, width: int = 30, prefix: str = "Progress"):
    pct = 0 if total == 0 else frames_done / total
    filled = int(width * pct)
    bar = "#" * filled + "-" * (width - filled)
    print(f"\\r{prefix} [{bar}] {pct*100:5.1f}%", end="", flush=True)
    if frames_done >= total:
        print()
