"""Fire robot monitor server (runs on the Raspberry Pi).

  GET  /stream           MJPEG live video with fire boxes drawn
  GET  /snapshot.jpg     latest single frame
  GET  /api/status       robot + fire status JSON (app polls this)
  GET  /api/history      fire / patrol events
  POST /api/robot        your robot control script pushes its sensor values here

The app is monitor-only: there is no endpoint that moves the robot or switches the pump.
"""
import json
import os
import random
import threading
import time
import uuid
from datetime import datetime

import cv2
from flask import Flask, Response, abort, jsonify, request, send_from_directory

import config
import fire_detector
from camera import Camera

SNAP_DIR = os.path.join(config.DATA_DIR, "snapshots")
HISTORY_FILE = os.path.join(config.DATA_DIR, "history.json")
os.makedirs(SNAP_DIR, exist_ok=True)

app = Flask(__name__, static_folder=None)
lock = threading.Lock()
frame_ready = threading.Condition(lock)

latest_jpeg = None
frame_id = 0

ROBOT_STATUSES = {
    "Idle": "Robot is waiting",
    "Patrolling": "Robot is searching for fire",
    "Moving Forward": "Robot is moving toward the fire",
    "Approaching": "Robot is approaching the fire",
    "Target Reached": "Robot reached the fire",
    "Extinguishing": "Pump is spraying water",
    "Completed": "Fire is out",
}

state = {
    "status": "Idle",
    "status_detail": ROBOT_STATUSES["Idle"],
    "fire_detected": False,
    "fire_confidence": 0.0,
    "fire_position": None,
    "pump_on": False,
    "battery": None,
    "water_level": None,
    "distance_m": None,
    "fps": 0.0,
    "camera": None,
    "detector": None,
    "infer_ms": 0.0,
    "robot_last_seen": None,
    "simulated": config.SIMULATE,
}


# ---------------------------------------------------------------- history
def load_history():
    try:
        with open(HISTORY_FILE) as f:
            items = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    # A fire event still open from before a restart can't be finished any more.
    for e in items:
        if e.get("type") == "FIRE" and e.get("duration_s") is None:
            e["duration_s"] = -1
    return items


history = load_history()


def save_history():
    tmp = HISTORY_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(history, f, indent=1)
    os.replace(tmp, HISTORY_FILE)


def add_event(kind, frame):
    """kind: 'FIRE' or 'PATROL'. Caller holds the lock."""
    name = f"{uuid.uuid4().hex[:12]}.jpg"
    thumb = cv2.resize(frame, (320, int(320 * frame.shape[0] / frame.shape[1])))
    cv2.imwrite(os.path.join(SNAP_DIR, name), thumb, [cv2.IMWRITE_JPEG_QUALITY, 80])
    event = {
        "id": name[:-4],
        "type": kind,
        "time": datetime.now().isoformat(timespec="seconds"),
        "image": f"/snapshots/{name}",
        "pump_on": state["pump_on"],
        "duration_s": None,
        "confidence": state["fire_confidence"] if kind == "FIRE" else None,
        "_start": time.time(),
    }
    history.insert(0, event)
    while len(history) > config.MAX_HISTORY:
        old = history.pop()
        try:
            os.remove(os.path.join(SNAP_DIR, os.path.basename(old["image"])))
        except OSError:
            pass
    save_history()
    return event


# ---------------------------------------------------------------- simulation
def simulate_robot(dt):
    """Fake robot behaviour so the app can be tested without hardware. Caller holds the lock."""
    s = state
    if s["battery"] is None:
        s.update(battery=85.0, water_level=90.0, distance_m=3.0)
    s["battery"] = max(5.0, s["battery"] - 0.01 * dt)
    if s["fire_detected"]:
        if s["status"] in ("Idle", "Patrolling", "Completed"):
            s["status"] = "Moving Forward"
        if s["status"] in ("Moving Forward", "Approaching"):
            s["distance_m"] = max(0.3, s["distance_m"] - 0.25 * dt)
            s["status"] = "Approaching" if s["distance_m"] < 1.5 else "Moving Forward"
            if s["distance_m"] <= 0.3 and s["fire_position"] == "CENTER":
                s["status"] = "Target Reached"
        elif s["status"] == "Target Reached":
            s["status"] = "Extinguishing"
        if s["status"] == "Extinguishing":
            s["pump_on"] = True
            s["water_level"] = max(0.0, s["water_level"] - 3 * dt)
    else:
        if s["status"] == "Extinguishing":
            s["status"] = "Completed"
        elif s["status"] in ("Moving Forward", "Approaching", "Target Reached"):
            s["status"] = "Patrolling"
        elif s["status"] == "Idle":
            s["status"] = "Patrolling"
        s["pump_on"] = False
        s["distance_m"] = min(3.0, s["distance_m"] + 0.5 * dt) + random.uniform(-0.02, 0.02)
        if s["water_level"] < 5:  # pretend someone refilled it
            s["water_level"] = 100.0
    s["status_detail"] = ROBOT_STATUSES.get(s["status"], "")
    s["robot_last_seen"] = time.time()


# ---------------------------------------------------------------- camera loop
def camera_loop():
    global latest_jpeg, frame_id
    cam = Camera()
    with lock:
        state["camera"] = cam.kind
    print(f"[camera] using {cam.kind}")

    detector = fire_detector.AsyncDetector()
    with lock:
        state["detector"] = detector.name

    hit_streak = miss_streak = 0
    seen_result = 0
    active_fire = None
    last_patrol = 0.0
    fps_t, fps_n = time.time(), 0
    last = time.time()
    min_dt = 1.0 / max(1, config.TARGET_FPS)

    while True:
        t0 = time.time()
        frame = cam.read()
        if frame is None:
            time.sleep(0.1)
            continue

        detector.submit(frame)
        dets, result_id = detector.latest()
        if result_id != seen_result:  # count streaks per detector result, not per video frame
            seen_result = result_id
            if dets:
                hit_streak, miss_streak = hit_streak + 1, 0
            else:
                hit_streak, miss_streak = 0, miss_streak + 1
        fire_detector.draw(frame, dets)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY])

        now = time.time()
        with lock:
            if dets:
                state["fire_confidence"] = dets[0][4]
                state["fire_position"] = fire_detector.position_of(dets[0], frame.shape[1])
            if not state["fire_detected"] and hit_streak >= config.FIRE_CONFIRM_FRAMES:
                state["fire_detected"] = True
                active_fire = add_event("FIRE", frame)
            elif state["fire_detected"] and miss_streak >= config.FIRE_CLEAR_FRAMES:
                state["fire_detected"] = False
                state["fire_confidence"] = 0.0
                state["fire_position"] = None
                if active_fire:
                    active_fire["duration_s"] = int(now - active_fire["_start"])
                    save_history()
                active_fire = None
            if active_fire and state["pump_on"] and not active_fire["pump_on"]:
                active_fire["pump_on"] = True
                save_history()
            if not state["fire_detected"] and now - last_patrol > config.PATROL_SNAPSHOT_SECONDS:
                last_patrol = now
                add_event("PATROL", frame)

            state["infer_ms"] = detector.infer_ms
            if config.SIMULATE:
                simulate_robot(now - last)
            last = now

            fps_n += 1
            if now - fps_t >= 1.0:
                state["fps"] = round(fps_n / (now - fps_t), 1)
                fps_t, fps_n = now, 0

            if ok:
                latest_jpeg = buf.tobytes()
                frame_id += 1
                frame_ready.notify_all()

        spare = min_dt - (time.time() - t0)
        if spare > 0:
            time.sleep(spare)


# ---------------------------------------------------------------- routes
@app.route("/")
def index():
    return "Fire robot server is running. Open the mobile app and enter this address."


@app.route("/snapshots/<name>")
def snapshot_file(name):
    return send_from_directory(SNAP_DIR, name)


def mjpeg():
    seen = -1
    while True:
        with frame_ready:
            frame_ready.wait_for(lambda: frame_id != seen, timeout=2)
            if latest_jpeg is None:
                continue
            seen, jpg = frame_id, latest_jpeg
        yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"


@app.route("/stream")
def stream():
    return Response(mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame",
                    headers={"Cache-Control": "no-cache, private"})


@app.route("/snapshot.jpg")
def snapshot():
    with lock:
        jpg = latest_jpeg
    if jpg is None:
        abort(503)
    return Response(jpg, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})


@app.route("/api/status")
def api_status():
    with lock:
        s = dict(state)
    seen = s.pop("robot_last_seen")
    s["robot_online"] = seen is not None and time.time() - seen < 10
    for k in ("battery", "water_level", "distance_m"):
        if s[k] is not None:
            s[k] = round(s[k], 2 if k == "distance_m" else 0)
    s["alerts"] = []
    if s["water_level"] is not None and s["water_level"] <= config.LOW_WATER_PERCENT:
        s["alerts"].append({"level": "warn", "text": "Water level too low. Refill water."})
    if s["battery"] is not None and s["battery"] <= config.LOW_BATTERY_PERCENT:
        s["alerts"].append({"level": "warn", "text": "Battery low. Charge the robot."})
    if s["fire_detected"]:
        s["alerts"].insert(0, {"level": "fire", "text": "Fire detected!"})
    s["server_time"] = datetime.now().isoformat(timespec="seconds")
    return jsonify(s)


@app.route("/api/history")
def api_history():
    with lock:
        items = [{k: v for k, v in e.items() if not k.startswith("_")} for e in history]
    return jsonify(items)


@app.route("/api/robot", methods=["POST"])
def api_robot():
    """Robot control script reports its state. Send only fields you have, e.g.
    {"status": "Approaching", "pump_on": false, "battery": 85, "water_level": 40, "distance_m": 1.25}
    """
    data = request.get_json(silent=True) or {}
    with lock:
        if "status" in data:
            state["status"] = str(data["status"])
            state["status_detail"] = str(data.get("status_detail") or ROBOT_STATUSES.get(state["status"], ""))
        if "pump_on" in data:
            state["pump_on"] = bool(data["pump_on"])
        for k in ("battery", "water_level", "distance_m"):
            if data.get(k) is not None:
                state[k] = float(data[k])
        state["robot_last_seen"] = time.time()
    return jsonify(ok=True)


@app.route("/api/config")
def api_config():
    return jsonify(low_water_percent=config.LOW_WATER_PERCENT, low_battery_percent=config.LOW_BATTERY_PERCENT)


if __name__ == "__main__":
    threading.Thread(target=camera_loop, daemon=True).start()
    print(f"Server on port {config.PORT}. In the app, enter http://<pi-ip>:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, threaded=True)
