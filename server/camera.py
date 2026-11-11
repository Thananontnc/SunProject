"""Camera source. Uses Picamera2 on the Pi (Camera Rev 1.3 / OV5647), falls back to
an OpenCV webcam (for testing on a laptop), then to a synthetic test pattern."""
import time

import cv2
import numpy as np

import config


class Camera:
    def __init__(self):
        self.kind = None
        self._picam = None
        self._cap = None
        self._t0 = time.time()
        self._open()

    def _open(self):
        if config.CAMERA == "synthetic":
            self.kind = "synthetic"
            return
        try:
            from picamera2 import Picamera2

            cam = Picamera2()
            cam.configure(
                cam.create_video_configuration(
                    main={"size": (config.FRAME_WIDTH, config.FRAME_HEIGHT), "format": "RGB888"}
                )
            )
            cam.start()
            self._picam = cam
            self.kind = "picamera2"
            return
        except Exception as e:  # not on a Pi, or camera not enabled
            print(f"[camera] Picamera2 unavailable ({e}); trying OpenCV webcam")

        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
            self._cap = cap
            self.kind = "opencv"
            return
        cap.release()
        print("[camera] No camera found; using synthetic test frames")
        self.kind = "synthetic"

    def read(self):
        """Return a BGR frame (numpy array) or None."""
        if self._picam is not None:
            # Picamera2 "RGB888" is actually BGR byte order, which matches OpenCV.
            frame = self._picam.capture_array()
        elif self._cap is not None:
            ok, frame = self._cap.read()
            if not ok:
                return None
        else:
            frame = self._synthetic()
        if config.ROTATE_180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        return frame

    def _synthetic(self):
        """Dark room with a flickering 'flame' that drifts left/right, for demo/testing."""
        w, h = config.FRAME_WIDTH, config.FRAME_HEIGHT
        t = time.time() - self._t0
        frame = np.full((h, w, 3), (40, 38, 35), np.uint8)
        cv2.rectangle(frame, (0, int(h * 0.7)), (w, h), (60, 60, 60), -1)
        # flame visible 20s, hidden 10s
        if (t % 30) < 20:
            cx = int(w / 2 + np.sin(t / 3) * w * 0.25)
            base = int(h * 0.72)
            fh = int(h * 0.3 + np.sin(t * 9) * 12)
            pts = np.array([[cx - 45, base], [cx, base - fh], [cx + 45, base]], np.int32)
            cv2.fillPoly(frame, [pts], (0, 120, 255))
            inner = np.array([[cx - 22, base], [cx, base - int(fh * 0.6)], [cx + 22, base]], np.int32)
            cv2.fillPoly(frame, [inner], (120, 230, 255))
        noise = np.random.randint(0, 12, frame.shape, np.uint8)
        return cv2.add(frame, noise)

    def close(self):
        if self._picam is not None:
            self._picam.stop()
        if self._cap is not None:
            self._cap.release()
