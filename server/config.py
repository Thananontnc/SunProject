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
# ROTATE=0/90/180/270 turns the picture clockwise (camera mounted sideways or upside down).
# ROTATE_180=1 is the older setting and still works.
ROTATE = int(os.getenv("ROTATE", "180" if os.getenv("ROTATE_180", "0") == "1" else "0")) % 360

# Fire detection
# DETECTOR: auto (YOLO if model file exists, else colour) | yolo | color
DETECTOR = os.getenv("DETECTOR", "auto")
YOLO_MODEL = os.getenv("YOLO_MODEL", os.path.join(os.path.dirname(__file__), "models", "fire_ncnn_model"))
YOLO_IMGSZ = int(os.getenv("YOLO_IMGSZ", "320"))  # must match the export size from the notebook
# Which model classes count as fire. D-Fire model has "smoke" and "fire". Use "fire,smoke" to alert on both.
FIRE_CLASSES = os.getenv("FIRE_CLASSES", "fire")
# Fake-fire filter (YOLO only): ignore fire that doesn't flicker (printed flames, posters)
# and be stricter when the "fire" is on a person's body (fire-print shirts). See fire_filter.py.
FAKE_FIRE_FILTER = os.getenv("FAKE_FIRE_FILTER", "1") == "1"
PERSON_MODEL = os.getenv("PERSON_MODEL", os.path.join(os.path.dirname(__file__), "models", "person_ncnn_model"))
FLICKER_MIN = float(os.getenv("FLICKER_MIN", "8"))                    # flicker score a real flame must reach
FLICKER_MIN_ON_PERSON = float(os.getenv("FLICKER_MIN_ON_PERSON", "11"))  # stricter on a shirt
FLICKER_FRAMES = int(os.getenv("FLICKER_FRAMES", "10"))                # detector results used per score
FILTER_LOG = os.getenv("FILTER_LOG", "0") == "1"                      # print scores (for tuning)
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

# Arduino serial link: "auto" finds /dev/ttyACM* etc, "none" disables, or a path like /dev/ttyACM0
SERIAL_PORT = os.getenv("SERIAL_PORT", "auto")
SERIAL_BAUD = int(os.getenv("SERIAL_BAUD", "115200"))

# SIMULATE=1 fakes battery/water/distance/pump so you can test the app without the robot.
SIMULATE = os.getenv("SIMULATE", "0") == "1"
