"""Serial link between the Pi and the Arduino UNO (see docs/serial-protocol.md).

Pi -> Arduino, 10x per second:
    F,<L|C|R>,<offset -100..100>,<size % of frame>,<conf 0..100>     fire seen
    N                                                                no fire
Arduino -> Pi:
    R                                         ready (after reset)
    S,<state>,<dist_cm>,<pump>,<battery>,<water>   status, -1 = unknown
    E,<text>                                  log / error

Runs in its own thread. Finds the Arduino automatically (/dev/ttyACM*, /dev/ttyUSB*,
or /dev/cu.usbmodem* on a Mac) and reconnects if the cable is unplugged.
"""
import glob
import threading
import time

import config

STATE_NAMES = {
    "IDLE": "Idle",
    "PATROL": "Patrolling",
    "FORWARD": "Moving Forward",
    "APPROACH": "Approaching",
    "TARGET": "Target Reached",
    "EXTINGUISH": "Extinguishing",
    "DONE": "Completed",
}


def find_port():
    if config.SERIAL_PORT not in ("auto", ""):
        return config.SERIAL_PORT
    for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*", "/dev/cu.usbmodem*", "/dev/cu.usbserial*"):
        ports = sorted(glob.glob(pattern))
        if ports:
            return ports[0]
    return None


def fire_message(state):
    """Build the Pi -> Arduino line from the current fire state. Caller holds the lock."""
    if not state["fire_detected"] or state.get("fire_box") is None:
        return "N"
    x, y, w, h, conf = state["fire_box"]
    fw, fh = state["frame_size"]
    offset = int(round(((x + w / 2) / fw - 0.5) * 200))
    size = int(round(100.0 * w * h / (fw * fh)))
    pos = {"LEFT": "L", "CENTER": "C", "RIGHT": "R"}.get(state["fire_position"], "C")
    return f"F,{pos},{max(-100, min(100, offset))},{max(0, min(100, size))},{int(round(conf * 100))}"


def parse_status(line):
    """'S,APPROACH,45,0,82,60' -> dict for the app state, or None if malformed."""
    p = line.split(",")
    if len(p) != 6:
        return None
    try:
        dist, pump, bat, water = (int(float(v)) for v in p[2:6])
    except ValueError:
        return None
    raw_state = p[1].strip().upper()
    status = STATE_NAMES.get(raw_state, raw_state.title())
    return {
        "status": status,
        "pump_on": pump == 1,
        "distance_m": dist / 100.0 if dist >= 0 else None,
        "battery": float(bat) if bat >= 0 else None,
        "water_level": float(water) if water >= 0 else None,
    }


class ArduinoBridge:
    def __init__(self, state, lock, status_details):
        self.state = state
        self.lock = lock
        self.details = status_details
        self.port = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            import serial  # pyserial
        except ImportError:
            print("[arduino] pyserial not installed; Arduino link disabled (pip install pyserial)")
            return
        while True:
            port = find_port()
            if not port:
                self._set_port(None)
                time.sleep(2)
                continue
            try:
                ser = serial.Serial(port, config.SERIAL_BAUD, timeout=0.05)
            except Exception as e:
                print(f"[arduino] cannot open {port}: {e}")
                time.sleep(2)
                continue
            print(f"[arduino] connected on {port}")
            self._set_port(port)
            try:
                self._loop(ser)
            except Exception as e:
                print(f"[arduino] disconnected: {e}")
            finally:
                try:
                    ser.close()
                except Exception:
                    pass
                self._set_port(None)
            time.sleep(1)

    def _set_port(self, port):
        self.port = port
        with self.lock:
            self.state["arduino"] = port

    def _loop(self, ser):
        opened = time.time()
        ready = False
        buf = b""
        last_send = 0.0
        while True:
            chunk = ser.read(256)
            if chunk:
                buf += chunk
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    line = raw.decode(errors="replace").strip()
                    if line:
                        ready = self._handle(line) or ready
                if len(buf) > 512:  # garbage without newlines
                    buf = b""
            # Opening the port resets the Uno (~2 s). Start sending after "R" or 3 s.
            now = time.time()
            if (ready or now - opened > 3) and now - last_send >= 0.1:
                last_send = now
                with self.lock:
                    msg = fire_message(self.state)
                ser.write((msg + "\n").encode())

    def _handle(self, line):
        """Returns True when the Arduino reports ready."""
        kind = line[0]
        if kind == "R":
            print("[arduino] ready")
            return True
        if kind == "S":
            data = parse_status(line)
            if data:
                with self.lock:
                    if data["status"] != "Idle" or self.state["status"] in ("Idle", None):
                        self.state["status"] = data["status"]
                        self.state["status_detail"] = self.details.get(data["status"], "")
                    for k in ("pump_on", "distance_m", "battery", "water_level"):
                        self.state[k] = data[k]
                    self.state["robot_last_seen"] = time.time()
        elif kind == "E":
            print(f"[arduino] {line[2:]}")
        return False
