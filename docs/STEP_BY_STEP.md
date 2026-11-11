# Step-by-step guide: from zero to a working robot monitor

Follow these in order. Each step says **where** to run it: 💻 Mac, 🍓 Raspberry Pi, 🖥️ Windows PC (RTX 4060), 📱 phone, or 🔌 Arduino.

Repo: https://github.com/Thananontnc/SunProject

---

## Step 0: Things you need

- Raspberry Pi 5 (4GB), a microSD card (32GB+), and a **5V 5A USB-C** power supply
- Pi Camera Rev 1.3 + a **Pi 5 camera cable (22-pin to 15-pin)**. The original Rev 1.3 cable does not fit the Pi 5.
- Arduino Uno, HX711 + load cell, L298N, HC-SR04 ultrasonic, pump + relay or MOSFET
- A phone with **Expo Go** installed (App Store / Play Store)
- All devices on the **same WiFi**

---

## Step 1: Set up the Raspberry Pi 🍓 (once)

1. 💻 Install **Raspberry Pi Imager** (https://www.raspberrypi.com/software/) and flash **Raspberry Pi OS (64-bit)** to the SD card.
   In the Imager settings (⚙️), set the hostname to `firerobot`, username `pi` and a password, your WiFi, and **enable SSH**.
2. Connect the camera with the Pi 5 cable. The blue side of the cable faces the black clip. Do this with the power **off**.
3. Insert the SD card and power the Pi on. Wait about 1–2 minutes.
4. 💻 Connect from the Mac:
   ```bash
   ssh pi@firerobot.local
   ```
5. 🍓 Update the Pi and test the camera:
   ```bash
   sudo apt update && sudo apt full-upgrade -y
   rpicam-hello -t 3000          # should say the camera was found (ov5647)
   ```
   If no camera is found: run `sudo nano /boot/firmware/config.txt` and add `dtoverlay=ov5647` under `[all]`, then `sudo reboot`.

---

## Step 2: Install the server on the Pi 🍓 (once)

```bash
sudo apt install -y git python3-picamera2 python3-opencv python3-flask python3-numpy
cd ~
git clone https://github.com/Thananontnc/SunProject.git
cd SunProject/server
python3 -m venv --system-site-packages ~/venv     # venv that can still see picamera2 from apt
~/venv/bin/pip install ultralytics ncnn            # for the YOLO model (takes a few minutes)
```

Test it with fake robot data:
```bash
SIMULATE=1 ~/venv/bin/python app.py
```
You should see `[camera] using picamera2` and `Running on http://...:5000`. Write down the Pi's IP:
```bash
hostname -I        # e.g. 192.168.1.42
```
Press `Ctrl+C` to stop.

---

## Step 3: Run the app on your phone 💻 📱

💻 On the Mac (the first time only, clone the repo; the Mac needs Node.js installed):
```bash
git clone https://github.com/Thananontnc/SunProject.git
cd SunProject/app
npm install
npx expo start
```
📱 Open **Expo Go** and scan the QR code. On iPhone, use the Camera app to scan.

📱 In the app: open **Setting**, enter `http://<pi-ip>:5000` (e.g. `http://192.168.1.42:5000`), then tap **Test** and **Save**.
Make sure the server on the Pi is running (Step 2 test command).

You should see live video in **Camera** and the robot status in **Home**.

---

## Step 4: Train the fire model 🖥️ (Windows PC with RTX 4060)

Full details: `training/README.md`.

1. Install **Python 3.12** and tick "Add to PATH". Install **Git for Windows**. Update the NVIDIA driver.
2. In Command Prompt:
   ```bat
   git clone https://github.com/Thananontnc/SunProject.git
   cd SunProject\training
   python -m venv venv
   venv\Scripts\activate
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
   pip install ultralytics kagglehub
   python -c "import torch; print(torch.cuda.is_available())"
   ```
   The last line must print `True`. If it doesn't, take the PyTorch install command from https://pytorch.org/get-started/locally/.
3. Train (takes about 1.5–3 hours):
   ```bat
   python train_fire.py
   ```
   - The PC turned off? Continue with `python train_fire.py --resume`
   - Out of memory? Use `python train_fire.py --batch 16`
   - "spawn" or workers error? Add `--workers 0`
4. The result is `training\fire_ncnn_model.zip`. The fire **mAP50** printed at the end should be > 0.6.

---

## Step 5: Put the model on the Pi 🖥️ → 🍓

From the PC (PowerShell; Windows has `scp` built in):
```bat
scp training\fire_ncnn_model.zip pi@firerobot.local:~/SunProject/server/models/
```
🍓 On the Pi:
```bash
cd ~/SunProject/server/models
unzip -o fire_ncnn_model.zip          # creates models/fire_ncnn_model/
cd ..
~/venv/bin/python app.py
```
The log should show `[detector] YOLO model ... using=['fire']`, and the app's **Camera** tab shows "Detector: YOLO AI".
Test it with a lighter or candle flame in front of the camera (be careful).

---

## Step 6: Water weight sensor 🔌 (Arduino + HX711)

Full details: `arduino/water_tank/` and `docs/serial-protocol.md`.

1. Wiring: HX711 **DT → A2, SCK → A3, VCC → 5V, GND → GND**. Load cell: Red=E+, Black=E-, White=A-, Green=A+.
2. Arduino IDE: open `arduino/water_tank/water_tank.ino`, choose Board **Arduino Uno** and the port, then click **Upload**.
3. Open Serial Monitor at **115200** with **New Line**:
   - `C,SHOW` should show `sensor=OK` (if it shows `NO DATA`, check the wiring)
   - Put the empty tank on and send `C,EMPTY`, then fill the tank and send `C,FULL`
   - The last number of `S,IDLE,-1,0,-1,XX` is now the water %

Unplug the Arduino from the Pi before uploading code.

---

## Step 7: Start the server automatically on boot 🍓

```bash
sudo tee /etc/systemd/system/fire-monitor.service >/dev/null <<'EOF'
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
sudo systemctl status fire-monitor        # should be "active (running)"
journalctl -u fire-monitor -f             # live log (Ctrl+C to exit)
```
After this, the server starts by itself whenever the Pi powers on.

---

## Step 8: Not done yet (next work)

- [ ] **Pi ↔ Arduino bridge**: a program on the Pi that reads `S,...` messages from the Arduino and sends `F,...`/`N` messages to it, so the app shows the real distance, pump, battery and water.
- [ ] **Robot driving code on the Arduino** (your friend): motors, ultrasonic, pump, following `docs/serial-protocol.md`.
- [ ] Optional: take your own Pi camera fire photos and retrain with `--extra` for better accuracy.

---

## Every day: how to use it

1. Turn on the robot (Pi + Arduino). Wait about 1 minute.
2. 💻 `cd SunProject/app && npx expo start`, then scan the QR code with Expo Go. You can skip this once the app is built as an APK.
3. 📱 Open the app. It remembers the Pi address.

## Get the latest code

```bash
cd ~/SunProject && git pull                   # on the Pi, then:
sudo systemctl restart fire-monitor
```
```bash
cd SunProject && git pull && cd app && npm install    # on the Mac
```

## Troubleshooting

| Problem | Fix |
|---|---|
| App says "Can't reach robot" | Phone and Pi on the same WiFi? Correct IP in Setting? Is the server running? (`sudo systemctl status fire-monitor`) |
| `ssh pi@firerobot.local` doesn't work | Use the IP from your router's page instead: `ssh pi@192.168.x.x` |
| No camera | Power off, check the cable direction, add `dtoverlay=ov5647`, reboot |
| Pi reboots when the motors start | The Pi power supply is too weak. It needs 5V 5A, separate from the motor battery |
| Fire not detected / false alarms | Check the "Detector" line in the Camera tab. Retrain with your own photos (Step 4, `--extra`) |
| Water % is -1 | Not calibrated (`C,EMPTY` / `C,FULL`), or HX711 wiring (`C,SHOW` → `NO DATA`) |
