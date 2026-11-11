"""Settings for the fire robot monitor server. Edit values here or override with env vars."""
import os

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))

# Camera (Raspberry Pi Camera Rev 1.3 = OV5647 sensor)
FRAME_WIDTH = int(os.getenv("FRAME_WIDTH", "640"))
FRAME_HEIGHT = int(os.getenv("FRAME_HEIGHT", "480"))
TARGET_FPS = int(os.getenv("TARGET_FPS", "25"))
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "75"))
# CAMERA=synthetic forces the fake test video (no camera needed).
CAMERA = os.getenv("CAMERA", "auto")
# Rotate 180 if the camera is mounted upside down on the robot.
ROTATE_180 = os.getenv("ROTATE_180", "0") == "1"

# Fire detection
# DETECTOR: auto (YOLO if model file exists, else colour) | yolo | color
DETECTOR = os.getenv("DETECTOR", "auto")
YOLO_MODEL = os.getenv("YOLO_MODEL", os.path.join(os.path.dirname(__file__), "models", "fire_ncnn_model"))
YOLO_IMGSZ = int(os.getenv("YOLO_IMGSZ", "320"))  # must match the export size from the notebook
# Which model classes count as fire. D-Fire model has "smoke" and "fire". Use "fire,smoke" to alert on both.
FIRE_CLASSES = os.getenv("FIRE_CLASSES", "fire")
# Colour detector only:
FIRE_MIN_AREA_RATIO = float(os.getenv("FIRE_MIN_AREA_RATIO", "0.002"))  # of frame area
FIRE_CONFIDENCE_THRESHOLD = float(os.getenv("FIRE_CONFIDENCE_THRESHOLD", "0.5"))
FIRE_CONFIRM_FRAMES = int(os.getenv("FIRE_CONFIRM_FRAMES", "5"))   # frames in a row to say YES
FIRE_CLEAR_FRAMES = int(os.getenv("FIRE_CLEAR_FRAMES", "15"))      # frames in a row to say NO

# History
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
PATROL_SNAPSHOT_SECONDS = int(os.getenv("PATROL_SNAPSHOT_SECONDS", "300"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "300"))

# Alerts
LOW_WATER_PERCENT = int(os.getenv("LOW_WATER_PERCENT", "20"))
LOW_BATTERY_PERCENT = int(os.getenv("LOW_BATTERY_PERCENT", "20"))

# SIMULATE=1 fakes battery/water/distance/pump so you can test the app without the robot.
SIMULATE = os.getenv("SIMULATE", "0") == "1"
