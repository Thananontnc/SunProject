#!/usr/bin/env bash
# One-command setup for the fire robot monitor on a fresh Raspberry Pi OS (Pi 5).
#
#   curl -fsSL https://raw.githubusercontent.com/Thananontnc/SunProject/main/scripts/setup_pi.sh | bash
#
# Safe to run again: it updates the code and keeps your settings.
# Options (put after "bash -s --"):
#   --rev13     camera is Pi Camera Rev 1.3 (OV5647): force its driver on both camera ports
#   --simulate  fake robot values (for testing without the Arduino)
#   --no-apt    skip "apt update/install" (offline re-run)
set -euo pipefail

# Everything is inside main() so bash reads the whole script before running it
# (needed for 'curl ... | bash', where commands could otherwise eat the script from stdin).
main() {

REPO_URL="https://github.com/Thananontnc/SunProject.git"
APP_USER="${SUDO_USER:-$USER}"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
REPO_DIR="$APP_HOME/SunProject"
VENV="$APP_HOME/venv"
SERVICE=/etc/systemd/system/fire-monitor.service
ENV_FILE="$REPO_DIR/server/fire-monitor.env"
BOOT_CFG=/boot/firmware/config.txt
REV13=0; SIMULATE=0; DO_APT=1
for a in "$@"; do
  case "$a" in
    --rev13) REV13=1 ;;
    --simulate) SIMULATE=1 ;;
    --no-apt) DO_APT=0 ;;
    *) echo "unknown option: $a"; exit 1 ;;
  esac
done

step() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }

if [ "$(id -u)" -eq 0 ] && [ -z "${SUDO_USER:-}" ]; then
  echo "Run this as your normal user (not root). It will ask for your password when needed."; exit 1
fi
sudo -v   # ask for the password once, up front

if [ "$DO_APT" -eq 1 ]; then
  step "1/8 Installing system packages (apt)"
  sudo apt-get update -y
  sudo apt-get install -y git python3-venv python3-picamera2 python3-opencv \
    python3-flask python3-numpy python3-serial rpicam-apps
fi

step "2/8 Getting the project code -> $REPO_DIR"
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull --ff-only || warn "git pull failed (local changes?) - keeping current code"
else
  git clone "$REPO_URL" "$REPO_DIR"
fi

step "3/8 Python environment -> $VENV"
[ -x "$VENV/bin/python" ] || python3 -m venv --system-site-packages "$VENV"
# Everything in server/requirements.txt (apt already gave flask/numpy/opencv/serial, so pip
# only adds what's missing, e.g. ncnn for the YOLO model). New entries there get installed
# automatically on the next run. Retries help on flaky WiFi.
"$VENV/bin/pip" install --quiet --retries 10 --timeout 120 -r "$REPO_DIR/server/requirements.txt"
"$VENV/bin/python" -c "import flask, cv2, numpy, serial, ncnn, picamera2; print('python packages OK')"

step "4/8 Camera setup"
if [ "$REV13" -eq 1 ] && [ -f "$BOOT_CFG" ]; then
  if ! grep -q '^dtoverlay=ov5647' "$BOOT_CFG"; then
    sudo sed -i 's/^camera_auto_detect=1/camera_auto_detect=0/' "$BOOT_CFG"
    printf '\n[all]\ndtoverlay=ov5647\ndtoverlay=ov5647,cam0\n' | sudo tee -a "$BOOT_CFG" >/dev/null
    echo "Rev 1.3 camera driver added (active after reboot)"
  else
    echo "Rev 1.3 camera driver already configured"
  fi
else
  echo "Using automatic camera detection (Camera Module 3 and most cameras)"
fi
sudo usermod -aG video,dialout "$APP_USER"   # camera + Arduino USB access

step "5/8 SSH: don't block computers on the local network after many quick logins"
echo "PerSourcePenaltyExemptList 192.168.0.0/16,10.0.0.0/8,172.16.0.0/12" \
  | sudo tee /etc/ssh/sshd_config.d/lan.conf >/dev/null
sudo systemctl reload ssh 2>/dev/null || sudo systemctl restart ssh || true

step "6/8 WiFi: turn off power saving (stops the connection dropping)"
if [ -d /etc/NetworkManager/conf.d ]; then
  printf '[connection]\nwifi.powersave = 2\n' \
    | sudo tee /etc/NetworkManager/conf.d/wifi-powersave-off.conf >/dev/null
  echo "WiFi power saving off (active after reboot)"
else
  echo "NetworkManager not found - skipped"
fi

step "7/8 Auto-start service (fire-monitor)"
if [ ! -f "$ENV_FILE" ]; then
  echo "SIMULATE=$SIMULATE" > "$ENV_FILE"
elif [ "$SIMULATE" -eq 1 ]; then
  sed -i 's/^SIMULATE=.*/SIMULATE=1/' "$ENV_FILE"
fi
sudo tee "$SERVICE" >/dev/null <<EOF
[Unit]
Description=Fire robot monitor server
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
WorkingDirectory=$REPO_DIR/server
EnvironmentFile=-$ENV_FILE
ExecStart=$VENV/bin/python -u app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable fire-monitor >/dev/null
sudo systemctl restart fire-monitor

step "8/8 Checking"
ok=0
for _ in $(seq 1 20); do
  if curl -fs -m 2 http://127.0.0.1:5000/api/status >/tmp/fire-status.json; then ok=1; break; fi
  sleep 1
done
IP="$(hostname -I | awk '{print $1}')"
if [ "$ok" -eq 1 ]; then
  python3 - <<'PY'
import json
d = json.load(open("/tmp/fire-status.json"))
print(f"  camera   : {d.get('camera')}")
print(f"  detector : {d.get('detector')}")
print(f"  arduino  : {d.get('arduino') or 'not connected'}")
PY
  if ! grep -q '"detector": *"yolo"' /tmp/fire-status.json; then
    warn "YOLO model not loaded (using the simple colour detector). Check $REPO_DIR/server/models/fire_ncnn_model"
  fi
  TEMP="$(vcgencmd measure_temp 2>/dev/null | grep -oE '[0-9]+' | head -1 || true)"
  THROTTLED="$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2 || true)"
  echo "  cpu temp : ${TEMP:-?} C"
  if [ -n "$TEMP" ] && [ "$TEMP" -ge 75 ]; then
    warn "Pi is hot (${TEMP} C). The AI runs all the time - fit the Raspberry Pi 5 Active Cooler (fan)."
  elif [ -n "$THROTTLED" ] && [ "$THROTTLED" != "0x0" ]; then
    warn "Pi slowed down because of heat or low power since boot (get_throttled=$THROTTLED). Check the fan and the 5V 5A power supply."
  fi
  if ! ls /sys/devices/platform/cooling_fan/hwmon/*/fan1_input >/dev/null 2>&1; then
    warn "No fan found on the Pi 5 fan connector."
  fi
  if rpicam-hello --list-cameras 2>&1 | grep -q "Available cameras"; then
    echo "  pi camera: detected"
  else
    warn "No camera detected yet. Check the cable (Pi 5 needs the narrow 22-pin cable), then reboot."
  fi
  printf '\n\033[1;32mDONE.\033[0m In the app (Setting), enter:  http://%s:5000   or   http://%s.local:5000\n' "$IP" "$(hostname)"
  [ "$REV13" -eq 1 ] && echo "Reboot once to load the camera driver:  sudo reboot"
else
  warn "Server did not answer. Look at the log:  journalctl -u fire-monitor -n 50"
  exit 1
fi
}

main "$@" < /dev/null
