from __future__ import annotations
from typing import List, Tuple, Optional, Dict, Deque
import os, sys, json, tempfile, subprocess, csv, time, math
from pathlib import Path
from collections import deque

import cv2
import numpy as np
from deep_sort_realtime.deepsort_tracker import DeepSort

BBox = Tuple[float, float, float, float]
Detection = Tuple[BBox, float, str]
TrackDict = Dict[str, object]

# ---------------- util ---------------- #
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

    if fmt_hint == "xyxy_norm":
        return _clip(b[0]*W, b[1]*H, b[2]*W, b[3]*H)
    if fmt_hint == "xywh_norm":
        return _clip(b[0]*W, b[1]*H, (b[0]+b[2])*W, (b[1]+b[3])*H)
    if fmt_hint == "xyxy_abs":
        return _clip(b[0], b[1], b[2], b[3])
    if fmt_hint == "xywh_abs":
        return _clip(b[0], b[1], b[0]+b[2], b[1]+b[3])

    maxv = max(abs(v) for v in b)
    is_norm = maxv <= 1.5
    x1, y1, z1, z2 = b
    if (not is_norm) and (z1 > x1) and (z2 > y1):
        return _clip(x1, y1, z1, z2)
    if (not is_norm) and (z1 >= 0) and (z2 >= 0) and (x1 <= W and y1 <= H):
        return _clip(x1, y1, x1 + z1, y1 + z2)
    if is_norm and (z1 > x1) and (z2 > y1):
        return _clip(x1 * W, y1 * H, z1 * W, z2 * H)
    return _clip(x1 * W, y1 * H, (x1 + z1) * W, (y1 + z2) * H)

def _nms_xyxy(dets: List[Tuple[List[float], float]], iou_thr=0.6) -> List[int]:
    if not dets: return []
    boxes = np.array([b for b, s in dets], dtype=np.float32)
    scores = np.array([s for b, s in dets], dtype=np.float32)
    x1, y1, x2, y2 = boxes.T
    areas = (x2-x1+1)*(y2-y1+1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2-xx1+1)
        h = np.maximum(0.0, yy2-yy1+1)
        inter = w*h
        iou = inter/(areas[i]+areas[order[1:]]-inter+1e-6)
        inds = np.where(iou <= iou_thr)[0]
        order = order[inds+1]
    return keep

def _iou(a: np.ndarray, b: np.ndarray) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
    inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, inter_x2 - inter_x1), max(0, inter_y2 - inter_y1)
    inter = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    denom = area_a + area_b - inter + 1e-6
    return float(inter / denom)

# ---------------- detector ---------------- #
class DetectorSpeciesNetBatch:
    def __init__(
        self,
        min_conf: float = 0.2,
        only_animals: bool = True,
        max_boxes: int = 8,
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

        scales = []
        index_to_name = {}
        for i, img in enumerate(frames):
            orig_h, orig_w = img.shape[:2]
            img_small, fx, fy = _resize_keep_aspect(img, self.save_max_side)
            save_h, save_w = img_small.shape[:2]
            name = f"frame_{i:08d}.jpg"
            p = self._frames_dir / name
            cv2.imwrite(str(p), img_small, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
            scales.append((fx, fy, save_w, save_h, orig_w, orig_h))
            index_to_name[i] = name

        self._run_cli()

        with open(self._pred_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        items = []
        if isinstance(data, dict):
            items = data.get("predictions") or data.get("images") or []
        elif isinstance(data, list):
            items = data

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

            tmp: List[Detection] = []
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

                hint = "xyxy_norm" if ("bbox_xyxy" in d) else None
                x1s, y1s, x2s, y2s = _to_xyxy_abs(bbox, save_w, save_h, fmt_hint=hint)
                x1 = int(round(x1s * fx)); y1 = int(round(y1s * fy))
                x2 = int(round(x2s * fx)); y2 = int(round(y2s * fy))
                x1 = max(0, min(orig_w - 1, x1)); x2 = max(0, min(orig_w - 1, x2))
                y1 = max(0, min(orig_h - 1, y1)); y2 = max(0, min(orig_h - 1, y2))
                tmp.append(((float(x1), float(y1), float(x2), float(y2)), score, "animal"))

            if tmp:
                dets_for_nms = [([t[0][0], t[0][1], t[0][2], t[0][3]], t[1]) for t in tmp]
                keep = _nms_xyxy(dets_for_nms, iou_thr=0.6)
                tmp = [tmp[i] for i in keep]

            tmp.sort(key=lambda t: t[1], reverse=True)
            out[idx_item] = tmp[: self.max_boxes]
        return out

# -------------- tracker ---------------- #
class TrackerWrapper:
    def __init__(self, max_age: int = 15, n_init: int = 1, ema_alpha: float = 0.35, only_updated: bool = True) -> None:
        self.tracker = DeepSort(
            max_age=max_age,
            n_init=n_init,
            embedder='mobilenet',
            embedder_gpu=False,
            half=False,
            max_iou_distance=0.9
        )
        self.ema_alpha = float(ema_alpha)
        self.only_updated = bool(only_updated)
        self._ema: Dict[int, np.ndarray] = {}

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
            if self.only_updated and getattr(tr, "time_since_update", 1) != 0:
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

        return active

# -------------- primary-box manager -------------- #
class PrimaryManager:
    def __init__(self, min_persist: int = 8, max_gap: int = 10):
        self.min_persist = int(min_persist)
        self.max_gap = int(max_gap)
        self.primary_id: Optional[int] = None
        self.persist = 0
        self.gap = 0
        self.ema_bbox: Optional[np.ndarray] = None

    def _select_candidate(self, tracks: List[TrackDict]) -> Optional[TrackDict]:
        if not tracks:
            return None
        return sorted(tracks, key=lambda t: float(t.get("score", 0.0)), reverse=True)[0]

    def step(self, tracks: List[TrackDict]) -> Optional[TrackDict]:
        if self.primary_id is not None:
            current = next((t for t in tracks if int(t["track_id"]) == self.primary_id), None)
            if current is not None:
                self.gap = 0
                self.persist += 1
                self._update_ema(current["bbox"])
                current["bbox"] = self.ema_bbox.astype(int).tolist()
                return current

            self.gap += 1
            if self.gap <= self.max_gap and self.ema_bbox is not None:
                return {"track_id": int(self.primary_id),
                        "bbox": self.ema_bbox.astype(int).tolist(),
                        "class": "animal",
                        "score": 0.0}

            self.primary_id = None
            self.persist = 0
            self.ema_bbox = None

        cand = self._select_candidate(tracks)
        if cand is None:
            return None
        self.primary_id = int(cand["track_id"])
        self.persist = 1
        self.gap = 0
        self._update_ema(cand["bbox"])
        cand["bbox"] = self.ema_bbox.astype(int).tolist()
        return cand

    def _update_ema(self, bbox: List[int], alpha: float = 0.35):
        arr = np.array(bbox, dtype=np.float32)
        if self.ema_bbox is None:
            self.ema_bbox = arr
        else:
            self.ema_bbox = (1 - alpha) * self.ema_bbox + alpha * arr

# -------------- viz ---------------- #
class Visualizer:
    def __init__(self, show_trace: bool = True) -> None:
        self.traces: Dict[int, List[Tuple[int, int]]] = {}
        self.show_trace = show_trace

    def _color(self, tid: int) -> Tuple[int, int, int]:
        rng = np.random.default_rng(int(tid) % (2**32))
        return tuple(int(x) for x in rng.integers(0, 255, 3))

    def draw(self,
             frame: np.ndarray,
             tracks: List[TrackDict],
             fps: Optional[float] = None,
             filter_track_id: Optional[int] = None,
             fixed_color: Optional[Tuple[int,int,int]] = None) -> np.ndarray:
        out = frame.copy()
        to_draw = tracks
        if filter_track_id is not None:
            to_draw = [t for t in tracks if int(t["track_id"]) == int(filter_track_id)]

        for t in to_draw:
            x1, y1, x2, y2 = t["bbox"]
            tid = int(t["track_id"])
            color = fixed_color if fixed_color is not None else self._color(tid)
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

# --------- motion gate + video processor --------- #
class MotionGate:
    def __init__(self, min_motion_ratio: float = 0.02, strong_conf: float = 0.6):
        self.bg = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=12, detectShadows=False)
        self.min_motion_ratio = float(min_motion_ratio)
        self.strong_conf = float(strong_conf)

    def filter(self, frame: np.ndarray, detections: List[Detection]) -> List[Detection]:
        mask = self.bg.apply(frame)
        if mask is None or not detections:
            return detections
        h, w = mask.shape[:2]
        kept: List[Detection] = []
        for (x1,y1,x2,y2), score, cls in detections:
            x1i, y1i, x2i, y2i = int(max(0,x1)), int(max(0,y1)), int(min(w-1,x2)), int(min(h-1,y2))
            if x2i <= x1i or y2i <= y1i:
                continue
            crop = mask[y1i:y2i+1, x1i:x2i+1]
            motion_ratio = float((crop > 0).mean()) if crop.size else 0.0
            if score >= self.strong_conf or motion_ratio >= self.min_motion_ratio:
                kept.append(((x1,y1,x2,y2), score, cls))
        return kept

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
                 batch_size: int = 24,
                 min_area_ratio: float = 0.001,
                 edge_pad: int = 2,
                 use_motion_gate: bool = True,
                 motion_min_ratio: float = 0.02,
                 motion_strong_conf: float = 0.6,
                 primary_only: bool = True,
                 lag: int = 6,
                 min_persist: int = 8,
                 max_gap: int = 10,
                 startup_suppress: int = 15) -> None:
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

        self.min_area_ratio = float(min_area_ratio)
        self.edge_pad = int(edge_pad)
        self.motion_gate = MotionGate(motion_min_ratio, motion_strong_conf) if use_motion_gate else None

        self.primary_only = bool(primary_only)
        self.lag = max(0, int(lag))
        self.startup_suppress = max(0, int(startup_suppress))
        self.primary = PrimaryManager(min_persist=min_persist, max_gap=max_gap)
        self.fixed_blue = (255, 0, 0)  # BGR

        # --- métricas de tiempo ---
        self._det_time_total = 0.0     # tiempo acumulado solo de detección
        self._wall_start = None        # tiempo de pared total

    def _hygiene_filter(self, dets: List[Detection], W: int, H: int) -> List[Detection]:
        area_min = self.min_area_ratio * (W * H)
        kept = []
        for (x1,y1,x2,y2), conf, cls in dets:
            w = max(0, x2-x1); h = max(0, y2-y1)
            area = w*h
            if area < area_min: 
                continue
            if x1 <= self.edge_pad or y1 <= self.edge_pad or x2 >= (W-1-self.edge_pad) or y2 >= (H-1-self.edge_pad):
                if conf < 0.6:
                    continue
            kept.append(((x1,y1,x2,y2), conf, cls))
        return kept

    def process(self, video_path: str) -> Dict[str, int]:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"No se pudo abrir el video: {video_path}")

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if self.start_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(self.start_frame, max(0, total - 1)))

        remaining = max(0, total - self.start_frame)
        total_to_process = min(self.max_frames, remaining) if (self.max_frames is not None) else remaining

        writer = cv2.VideoWriter(self.output_video_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
        with open(self.csv_log_path, "w", newline="") as csv_fp:
            csvw = csv.writer(csv_fp)
            csvw.writerow(["frame", "track_id", "x1", "y1", "x2", "y2", "class", "score"])

            processed = 0
            idx = int(cap.get(cv2.CAP_PROP_POS_FRAMES))  # real video index
            t0 = time.time()
            self._wall_start = time.perf_counter()

            frames_buf: List[np.ndarray] = []
            idx_buf: List[int] = []

            out_frames: Deque[Tuple[int, np.ndarray, Optional[TrackDict]]] = deque()

            def flush_if_ready(force_all: bool = False):
                while out_frames and (force_all or len(out_frames) > self.lag):
                    fidx, frm, tr = out_frames.popleft()
                    tracks_to_draw = [tr] if (tr is not None) else []
                    out = self.visualizer.draw(
                        frm, tracks_to_draw, fps=(processed / max(1e-6, time.time()-t0)),
                        filter_track_id=tr["track_id"] if tr else None,
                        fixed_color=self.fixed_blue if tr else None
                    )
                    writer.write(out)
                    if tr:
                        x1, y1, x2, y2 = tr["bbox"]
                        csvw.writerow([fidx, tr["track_id"], x1, y1, x2, y2,
                                       tr.get("class", "animal"), tr.get("score", 0.0)])

            def process_batch():
                nonlocal processed, idx
                if not frames_buf:
                    return
                # --- medir solo detección ---
                t_det0 = time.perf_counter()
                dets_all = self.detector.detect_batch(frames_buf)
                self._det_time_total += (time.perf_counter() - t_det0)
                # ----------------------------

                for i, frame in enumerate(frames_buf):
                    if processed >= total_to_process:
                        break

                    dets = dets_all[i] if ((idx_buf[i] - self.start_frame) % self.stride) == 0 else []
                    dets = self._hygiene_filter(dets, W, H)
                    if self.motion_gate is not None:
                        dets = self.motion_gate.filter(frame, dets)

                    if processed < self.startup_suppress:
                        dets = [d for d in dets if d[1] >= 0.4]

                    tracks = self.tracker.update(dets, frame)

                    chosen: Optional[TrackDict] = None
                    if self.primary_only:
                        chosen = self.primary.step(tracks)
                    else:
                        if tracks:
                            chosen = tracks[0]

                    out_frames.append((idx_buf[i], frame.copy(), chosen))
                    flush_if_ready(force_all=False)
                    processed += 1

                if idx_buf:
                    idx = idx_buf[-1] + 1
                frames_buf.clear()
                idx_buf.clear()

            while True:
                if processed >= total_to_process:
                    break
                ok, frame = cap.read()
                if not ok:
                    process_batch()
                    break
                if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                frames_buf.append(frame)
                idx_buf.append(idx)
                if len(frames_buf) >= self.batch_size:
                    process_batch()
                idx += 1

            flush_if_ready(force_all=True)

        cap.release()
        writer.release()

        # ---- resumen de tiempos ----
        wall = time.perf_counter() - (self._wall_start or time.perf_counter())
        det_total = self._det_time_total
        det_per = det_total / max(1, processed)
        fps_eff = processed / max(1e-6, wall)
        print(f"⏱️ Tiempo total: {wall:.2f}s | Detección: {det_total:.2f}s ({det_per:.3f}s/frame) | FPS efectivo: {fps_eff:.2f}")

        return {"frames_processed": processed}
