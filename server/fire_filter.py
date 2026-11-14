"""Throws away fire boxes that are probably printed flames (fire-print shirts, posters, stickers).

Two checks, no retraining needed:

1. Flicker: a real flame changes shape and brightness all the time. A printed flame looks the
   same in every frame (it only moves with the person). Each fire box is tracked over the last
   few detector results; the "flicker score" is how much the inside of the box changes
   (mean pixel difference, 0-255, of a small grey copy of the box). Too still = not fire.
2. Person: a small COCO YOLO model finds people. If the fire box sits on a person's body
   (shirt area), it needs a much higher flicker score. A lighter held in a hand still flickers
   enough; a shirt print doesn't.

The heat sensor on the robot is the final safety check; this filter only stops false alarms.

Rejected boxes are returned with a label saying why, so the stream draws them grey:
  "checking"   - seen for too few frames to judge yet
  "no flicker" - too still for a real flame
  "on person"  - on someone's body and not flickering enough
"""
import os
import time
from collections import deque

import cv2
import numpy as np

import config
import fire_detector

CROP = 24  # the box is shrunk to 24x24 grey before comparing frames


def _iou(a, b):
    ax, ay, aw, ah = a[:4]
    bx, by, bw, bh = b[:4]
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def _crop(gray, box):
    x, y, w, h = box[:4]
    patch = gray[max(0, y):y + max(1, h), max(0, x):x + max(1, w)]
    if patch.size == 0:
        return None
    return cv2.resize(patch, (CROP, CROP), interpolation=cv2.INTER_AREA).astype(np.int16)


class _Track:
    def __init__(self, box, crop, now):
        self.box, self.last_crop, self.seen = box, crop, now
        self.diffs = deque(maxlen=config.FLICKER_FRAMES)

    def update(self, box, crop, now):
        if crop is not None and self.last_crop is not None:
            self.diffs.append(float(np.abs(crop - self.last_crop).mean()))
        self.box, self.last_crop, self.seen = box, crop, now

    def score(self):
        return float(np.median(self.diffs)) if len(self.diffs) >= 3 else None


class FireFilter:
    def __init__(self):
        self.tracks = []
        self.person = None
        self.people, self.people_t, self.calls = [], 0.0, 0
        if os.path.exists(os.path.join(config.PERSON_MODEL, "model.ncnn.param")):
            try:
                self.person = fire_detector.NcnnBackend(config.PERSON_MODEL, classes="person", conf=0.4)
            except Exception as e:
                print(f"[filter] person model not loaded ({e}); flicker check only")
        else:
            print(f"[filter] no person model at {config.PERSON_MODEL}; flicker check only")
        print(f"[filter] fake-fire filter on: flicker >= {config.FLICKER_MIN}, "
              f"on a person >= {config.FLICKER_MIN_ON_PERSON}")

    def _people(self, frame, now):
        """Person boxes, refreshed every 3rd call to save CPU (people move slowly)."""
        self.calls += 1
        if self.person and (self.calls % 3 == 1 or now - self.people_t > 0.5):
            self.people, self.people_t = self.person(frame), now
        return self.people

    @staticmethod
    def _on_body(box, people):
        """Fire box centre inside the shirt/trouser area of a person box."""
        cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
        for px, py, pw, ph, *_ in people:
            if px + 0.1 * pw <= cx <= px + 0.9 * pw and py + 0.15 * ph <= cy <= py + 0.9 * ph:
                return True
        return False

    def __call__(self, frame, dets):
        now = time.time()
        self.tracks = [t for t in self.tracks if now - t.seen < 1.0]
        if not dets:
            return [], []
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        people = self._people(frame, now)
        kept, rejected = [], []
        for d in dets:
            crop = _crop(gray, d)
            track = max(self.tracks, key=lambda t: _iou(t.box, d), default=None)
            if track is None or _iou(track.box, d) < 0.2:
                track = _Track(d, crop, now)
                self.tracks.append(track)
            else:
                track.update(d, crop, now)
            score = track.score()
            on_body = self._on_body(d, people)
            need = config.FLICKER_MIN_ON_PERSON if on_body else config.FLICKER_MIN
            if config.FILTER_LOG:
                s = "-" if score is None else f"{score:.1f}"
                print(f"[filter] conf={d[4]:.2f} flicker={s} need={need} on_person={on_body}")
            if score is None:
                rejected.append(d[:5] + ("checking",))
            elif score >= need:
                kept.append(d)
            else:
                rejected.append(d[:5] + ("on person" if on_body else "no flicker",))
        return kept, rejected
