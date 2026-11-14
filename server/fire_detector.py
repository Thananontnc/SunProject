"""Fire detection.

Backends:
  * YOLO  - used automatically when a trained model exists at config.YOLO_MODEL
            (e.g. models/fire_ncnn_model). NCNN exports run with only the small
            `ncnn` package (NcnnBackend); ultralytics is a fallback for other formats.
  * color - OpenCV colour rules. Fast, no model, but fooled by orange lights.
            Used when no model is found or ultralytics isn't installed.

Each detection is a tuple (x, y, w, h, confidence, label) in full-frame pixels.

Detection runs in its own thread (`AsyncDetector`) so a slow model never slows the
video stream: the stream keeps ~25 FPS and boxes update as fast as the model can go.
"""
import os
import threading
import time

import cv2
import numpy as np

import config


# ---------------------------------------------------------------- colour backend
def detect_color(frame):
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (w // 2, h // 2))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

    # Fire colours: red -> orange -> yellow, saturated and bright.
    mask_color = cv2.inRange(hsv, (0, 80, 180), (35, 255, 255))
    # Very bright near-white core of a flame.
    mask_core = cv2.inRange(hsv, (0, 0, 240), (40, 90, 255))
    mask = cv2.bitwise_or(mask_color, mask_core)

    # Extra RGB rule: R > G > B and R is high (classic fire-pixel rule).
    b, g, r = cv2.split(small)
    rgb_rule = ((r > 180) & (r >= g) & (g > b)).astype(np.uint8) * 255
    mask = cv2.bitwise_and(mask, rgb_rule)

    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = config.FIRE_MIN_AREA_RATIO * small.shape[0] * small.shape[1]
    results = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        roi = mask[y : y + bh, x : x + bw]
        fill = float(np.count_nonzero(roi)) / max(1, bw * bh)
        size = min(1.0, area / (min_area * 20))
        conf = round(min(0.99, 0.45 + 0.35 * fill + 0.2 * size), 2)
        results.append((x * 2, y * 2, bw * 2, bh * 2, conf, "fire"))
    results.sort(key=lambda d: d[2] * d[3], reverse=True)
    return results


# ---------------------------------------------------------------- YOLO backend
class YoloBackend:
    def __init__(self, path):
        from ultralytics import YOLO  # imported lazily: only needed when a model exists

        self.model = YOLO(path, task="detect")
        self.names = self.model.names  # {0: 'smoke', 1: 'fire'} for D-Fire
        wanted = {c.strip().lower() for c in config.FIRE_CLASSES.split(",") if c.strip()}
        self.class_ids = [i for i, n in self.names.items() if str(n).lower() in wanted]
        if not self.class_ids:
            raise ValueError(f"model classes {self.names} contain none of FIRE_CLASSES={config.FIRE_CLASSES}")
        print(f"[detector] YOLO model {path} classes={self.names} using={[self.names[i] for i in self.class_ids]}")

    def __call__(self, frame):
        r = self.model.predict(
            frame,
            imgsz=config.YOLO_IMGSZ,
            conf=config.FIRE_CONFIDENCE_THRESHOLD,
            classes=self.class_ids,
            verbose=False,
        )[0]
        out = []
        for (x1, y1, x2, y2), conf, cls in zip(
            r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()
        ):
            out.append((int(x1), int(y1), int(x2 - x1), int(y2 - y1), round(conf, 2), str(self.names[int(cls)])))
        out.sort(key=lambda d: d[2] * d[3], reverse=True)
        return out


def _read_metadata(model_dir):
    """Class names + image size from Ultralytics metadata.yaml (no yaml lib needed)."""
    names, imgsz, section = {}, None, None
    with open(os.path.join(model_dir, "metadata.yaml"), encoding="utf-8") as f:
        for line in f:
            s = line.rstrip()
            if not s:
                continue
            if not s.startswith(" ") and not s.startswith("-"):
                section = s.split(":", 1)[0]
                continue
            if section == "names" and ":" in s:
                k, v = s.split(":", 1)
                names[int(k.strip())] = v.strip().strip("'\"")
            elif section == "imgsz" and s.strip().startswith("-") and imgsz is None:
                imgsz = int(s.strip()[1:].strip())
    return names, imgsz


class NcnnBackend:
    """Runs an Ultralytics NCNN export with only the small `ncnn` package (no PyTorch).

    Output 'out0' is (4 + num_classes, N): box cx, cy, w, h in input pixels, then class scores.
    """

    def __init__(self, model_dir, classes=None, conf=None):
        import ncnn

        self.ncnn = ncnn
        self.conf = config.FIRE_CONFIDENCE_THRESHOLD if conf is None else conf
        self.names, meta_size = _read_metadata(model_dir)
        self.size = meta_size or config.YOLO_IMGSZ
        self.net = ncnn.Net()
        self.net.opt.use_vulkan_compute = False
        self.net.opt.num_threads = os.cpu_count() or 4
        self.net.load_param(os.path.join(model_dir, "model.ncnn.param"))
        self.net.load_model(os.path.join(model_dir, "model.ncnn.bin"))
        classes = classes or config.FIRE_CLASSES
        wanted = {c.strip().lower() for c in classes.split(",") if c.strip()}
        self.class_ids = [i for i, n in self.names.items() if n.lower() in wanted]
        if not self.class_ids:
            raise ValueError(f"model classes {self.names} contain none of {classes}")
        print(f"[detector] NCNN model {model_dir} size={self.size} classes={self.names} "
              f"using={[self.names[i] for i in self.class_ids]}")

    def __call__(self, frame):
        h, w = frame.shape[:2]
        s = self.size
        r = min(s / w, s / h)
        nw, nh = int(round(w * r)), int(round(h * r))
        px, py = (s - nw) // 2, (s - nh) // 2
        canvas = np.full((s, s, 3), 114, np.uint8)
        canvas[py : py + nh, px : px + nw] = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        blob = np.ascontiguousarray(canvas[:, :, ::-1].transpose(2, 0, 1), dtype=np.float32) / 255.0

        ex = self.net.create_extractor()
        ex.input("in0", self.ncnn.Mat(blob))
        _, out = ex.extract("out0")
        out = np.array(out)  # (4 + nc, N)

        scores = out[4:]
        cls = scores.argmax(0)
        conf = scores[cls, np.arange(scores.shape[1])]
        keep = (conf >= self.conf) & np.isin(cls, self.class_ids)
        if not keep.any():
            return []
        cx, cy, bw, bh = out[:4, keep]
        conf, cls = conf[keep], cls[keep]
        x1 = (cx - bw / 2 - px) / r
        y1 = (cy - bh / 2 - py) / r
        boxes = np.stack([x1, y1, bw / r, bh / r], 1)
        idx = cv2.dnn.NMSBoxes(boxes.tolist(), conf.tolist(), self.conf, 0.45)
        result = []
        for i in np.array(idx).flatten():
            x, y, bw_, bh_ = boxes[i]
            x0, y0 = max(0, int(x)), max(0, int(y))
            x1_, y1_ = min(w, int(x + bw_)), min(h, int(y + bh_))
            result.append((x0, y0, x1_ - x0, y1_ - y0, round(float(conf[i]), 2), self.names[int(cls[i])]))
        result.sort(key=lambda d: d[2] * d[3], reverse=True)
        return result


def load_backend():
    """Returns (name, detect_function)."""
    mode = config.DETECTOR
    if mode in ("auto", "yolo"):
        if os.path.exists(os.path.join(config.YOLO_MODEL, "model.ncnn.param")):
            try:  # lightweight path: ncnn only, no PyTorch
                return "yolo", NcnnBackend(config.YOLO_MODEL)
            except ImportError:
                print("[detector] `ncnn` not installed; trying ultralytics")
            except Exception as e:
                print(f"[detector] NCNN load failed ({e}); trying ultralytics")
        if os.path.exists(config.YOLO_MODEL):
            try:
                return "yolo", YoloBackend(config.YOLO_MODEL)
            except Exception as e:
                if mode == "yolo":
                    raise
                print(f"[detector] YOLO failed to load ({e}); using colour detector")
        elif mode == "yolo":
            raise FileNotFoundError(f"YOLO model not found: {config.YOLO_MODEL}")
        else:
            print(f"[detector] no model at {config.YOLO_MODEL}; using colour detector")
    return "color", detect_color


class AsyncDetector:
    """Runs the detector on the newest frame in a background thread."""

    def __init__(self):
        self.name, self._fn = load_backend()
        self._cv = threading.Condition()
        self._frame = None
        self.result = []
        self.rejected = []  # boxes the fake-fire filter threw away (drawn grey)
        self.result_id = 0
        import fire_filter  # here, not at the top: fire_filter imports this module

        self._filter = fire_filter.FireFilter() if config.FAKE_FIRE_FILTER and self.name == "yolo" else None
        self.infer_ms = 0.0
        threading.Thread(target=self._run, daemon=True).start()

    def submit(self, frame):
        with self._cv:
            self._frame = frame.copy()
            self._cv.notify()

    def latest(self):
        with self._cv:
            return self.result, self.result_id

    def latest_rejected(self):
        with self._cv:
            return self.rejected

    def _run(self):
        while True:
            with self._cv:
                self._cv.wait_for(lambda: self._frame is not None)
                frame, self._frame = self._frame, None
            t0 = time.time()
            try:
                dets = self._fn(frame)
            except Exception as e:
                print(f"[detector] error: {e}")
                dets = []
            dets = [d for d in dets if d[4] >= config.FIRE_CONFIDENCE_THRESHOLD]
            rejected = []
            if self._filter:
                try:
                    dets, rejected = self._filter(frame, dets)
                except Exception as e:
                    print(f"[filter] error: {e}")
            with self._cv:
                self.result = dets
                self.rejected = rejected
                self.result_id += 1
                self.infer_ms = round((time.time() - t0) * 1000, 1)


# ---------------------------------------------------------------- helpers
def position_of(box, frame_width):
    """LEFT / CENTER / RIGHT of the biggest fire, like the mockup's POSITION field."""
    x, _, bw = box[0], box[1], box[2]
    cx = (x + bw / 2) / frame_width
    if cx < 0.4:
        return "LEFT"
    if cx > 0.6:
        return "RIGHT"
    return "CENTER"


def draw(frame, detections):
    for x, y, bw, bh, conf, label in detections:
        color = (80, 220, 80) if label.lower() == "fire" else (200, 200, 200)
        cv2.rectangle(frame, (x, y), (x + bw, y + bh), color, 2)
        text = f"{label.capitalize()} {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(frame, (x, max(0, y - th - 8)), (x + tw + 8, y), color, -1)
        cv2.putText(frame, text, (x + 4, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return frame
