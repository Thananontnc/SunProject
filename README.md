# Fire Robot Monitor

**New here? Follow [docs/STEP_BY_STEP.md](docs/STEP_BY_STEP.md).**

**New SD card, quick setup** (on the Pi):
```bash
curl -fsSL https://raw.githubusercontent.com/Thananontnc/SunProject/main/scripts/setup_pi.sh | bash -s -- --rev13
```

A monitor-only mobile app for an autonomous fire-fighting robot. The robot drives itself, so the app has no control buttons.

```
 Raspberry Pi (on robot)                         Phone
 ┌──────────────────────────────┐   WiFi   ┌──────────────────────┐
 │ Camera Rev 1.3 ─► server/app.py ───────► │ app/ (Expo React     │
 │   fire detection (OpenCV)     │  HTTP    │ Native)              │
 │   /stream /api/status /history│          │ Home · Camera ·      │
 │ your robot code ─► POST /api/robot       │ History · Setting    │
 └──────────────────────────────┘          └──────────────────────┘
```

## App screens

- **Home**: robot status (Patrolling / Moving Forward / Approaching / Target Reached / Extinguishing / Completed), fire detected YES/NO, pump ON/OFF (shown only, no switch), battery, and water level with a "Water level too low. Refill water." warning.
- **Camera**: live video with the fire box and confidence, FPS, distance, fire position (LEFT/CENTER/RIGHT), and fullscreen.
- **History**: fire and patrol snapshots grouped by day. You can filter them and tap one to see it larger.
- **Setting**: the Pi address, alert levels, and vibration when fire is detected.

---

## 1. Raspberry Pi server

Camera Rev 1.3 uses the OV5647 sensor. Raspberry Pi OS Bookworm supports it through libcamera/Picamera2.

```bash
# on the Pi
sudo apt update
sudo apt install -y git python3-picamera2 python3-opencv python3-flask python3-numpy
rpicam-hello -t 2000        # check camera works (older OS: libcamera-hello)

git clone https://github.com/Thananontnc/SunProject.git
cd SunProject/server
python3 -m venv --system-site-packages ~/venv    # keeps access to picamera2 from apt
~/venv/bin/pip install flask opencv-python-headless ncnn   # ncnn runs the YOLO model, no PyTorch needed
~/venv/bin/python app.py    # serves on port 5000
hostname -I                 # note the Pi IP, e.g. 192.168.1.42
```

If the camera isn't detected, add `camera_auto_detect=1` (or `dtoverlay=ov5647`) to `/boot/firmware/config.txt` and reboot.

Options (env vars, see `server/config.py`): `ROTATE_180=1`, `FRAME_WIDTH`, `TARGET_FPS`, `LOW_WATER_PERCENT`, `PATROL_SNAPSHOT_SECONDS`, and more.

**Test without the robot:** `CAMERA=synthetic SIMULATE=1 python3 app.py` shows a fake flame and fake robot values. On a Mac or PC, install the dependencies first with `pip install -r requirements.txt`. On a Mac, port 5000 is used by AirPlay, so add `PORT=5055`.

### Start automatically on boot

```bash
sudo tee /etc/systemd/system/fire-monitor.service >/dev/null <<EOF
[Unit]
Description=Fire robot monitor
After=network-online.target
[Service]
WorkingDirectory=/home/pi/SunProject/server
ExecStart=/home/pi/venv/bin/python app.py
Restart=always
User=pi
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now fire-monitor
```

### Connect your robot code

Your autonomous robot program sends battery, water level, distance, pump state and status to the server. See `server/robot_push_example.py`:

```python
report(status="Approaching", pump_on=False, battery=85, water_level=40, distance_m=1.25)
```

The server sets fire detection and position from the camera by itself.

---

## 2. Mobile app

```bash
cd app
npm install
npx expo start
```

1. Install **Expo Go** on your phone (App Store / Play Store).
2. Scan the QR code shown in the terminal.
3. Open the **Setting** tab and enter `http://<pi-ip>:5000`, then tap **Test** and **Save**.

The phone and the Pi must be on the same WiFi network.

### Build an installable APK (Android)

```bash
npx eas-cli@latest build -p android --profile preview
```

This needs a free Expo account. Plain HTTP to the Pi is already allowed in `app.json`.

---

## 3. YOLO fire detection (AI)

1. Open `training/train_fire_yolo.ipynb` in Google Colab (File → Upload notebook) and set the runtime to a T4 GPU.
2. Run all the cells. They download the D-Fire dataset, train YOLO26n, check accuracy and export to NCNN.
3. On the Pi, unzip `fire_ncnn_model.zip` into `server/models/`. `ncnn` is already installed in `~/venv` from step 1 (PyTorch is not needed on the Pi).
4. Restart the server. The log shows `[detector] YOLO model ...` and the app's Camera tab shows "Detector: YOLO AI".

With no model file, the server falls back to the colour detector by itself. Settings: `YOLO_IMGSZ` (must match the export size, default 320), `FIRE_CLASSES=fire,smoke` (also alert on smoke), and `DETECTOR=color|yolo|auto`.

## 4. Working with the Arduino side

`docs/serial-protocol.md` is the agreement between the Pi and the Arduino, in Thai and English. It covers the message format, robot states, safety rules, and how to test each side alone.

## Notes

- The colour detector (used when there's no model) is fast but can be triggered by orange lights or sunlight. The YOLO model is more accurate.
- "Heat" here means fire seen by the camera. The Rev 1.3 camera can't measure temperature. For real heat readings, add a thermal sensor (e.g. MLX90640) later.
