# Wiring guide (tested on the bench)

This is the wiring we built and tested on 2026-11-12, one part at a time. Each part says whether it is tested. Pin numbers match `arduino/water_tank/water_tank.ino` and `arduino/fire_robot/fire_robot.ino`.

On the Uno, "D9" means the pin labelled **9** on the DIGITAL header. Analog pins keep their "A" (A2, A3...).

---

## 1. Relay to Arduino ✅ tested

The relay module (SRD-05VDC) has 3 pins on one side:

| Relay pin | Arduino |
|---|---|
| VCC | 5V |
| GND | GND |
| IN | 9 |

The relay is active-LOW: pin 9 LOW = relay ON (click + LED on).

## 2. Battery to buck converter ✅ tested

- Battery: 2S lithium pack, 7.4 V (8.4 V when full), 5200 mAh, small white JST plug. We pushed male jumper wires into the plug holes and taped it.
- Buck converter: LM2596 board with a voltage display.

| Battery | Buck converter |
|---|---|
| Red (+) | VIN+ |
| Black (−) | VIN− |

Set the output **before** connecting the pump: press the button until the **OUT** LED is lit, then turn the brass screw (W103) until the display shows **5.00**.

## 3. Buck converter, relay and pump ✅ tested

The pump is a mini submersible pump rated about 3–6 V. **Never connect it straight to the battery** (8.4 V burns it). It must be in water when it runs for more than a moment.

The relay's screw terminals are labelled in Chinese:

| Label | Meaning | Connect to |
|---|---|---|
| 常开 | NO (normally open) | Pump red (+) |
| 公共端 (middle) | COM | Buck VOUT+ |
| 常闭 | NC (normally closed) | nothing |

The pump's black (−) wire goes to buck **VOUT−**.

```
Battery RED   -> VIN+  [BUCK 5.00 V]  VOUT+ -> relay 公共端 (COM, middle)
Battery BLACK -> VIN−                 VOUT− -> pump BLACK

relay 常开 (NO) -> pump RED
relay 常闭 (NC) -> nothing
```

The Arduino only switches the relay. The battery powers the pump.

## 4. HX711 load cell ✅ tested (FULL calibration pending)

The Uno has only one 5V pin, and the relay uses it, so the HX711 now runs on **3.3V** (it works from 2.6 to 5.5 V).

| HX711 | Arduino |
|---|---|
| VCC | 3.3V |
| GND | GND (a different GND pin from the relay) |
| DT | A2 |
| SCK | A3 |

Load cell to HX711: Red = E+, Black = E−, White = A−, Green = A+.

Changing from 5 V to 3.3 V changes the readings, so it must be recalibrated (Serial Monitor, 115200, Newline):

- `C,EMPTY` with the empty tank on: **done** (empty = −230231)
- `C,FULL` with the tank full: **still to do** (needs water)

Until `C,FULL` is done, the code thinks the tank is empty and refuses to start the pump. This is on purpose (it stops the pump running dry).

## 5. HC-SR04 distance sensor ⏳ not wired yet

| HC-SR04 | Arduino |
|---|---|
| Trig | 11 |
| Echo | 12 |
| GND | GND (the one next to pin 13) |
| VCC | 5V from the **ICSP header** (the 5V pin is taken) |

Needs a female-to-female jumper for the ICSP pin. Check the ICSP pin with a photo before plugging in. A breadboard would also solve the shared 5V problem.

## 6. Still to do

- L298N + 4 motors (pins in `arduino/fire_robot/fire_robot.ino`). Battery current for 4 motors may be too much for the thin JST plug wires.
- Heat sensor on A4 (SDA) / A5 (SCL).
- Connect the Uno to the Pi by USB.

---

## Bench tests

- **Relay click test:** relay ON 1 s, OFF 1 s, forever. With the pump wired, the pump follows the clicks.
- **Pump pulse test:** 3 pulses of 0.5 s, then stops. Short enough to run without water. Press RESET on the Uno to run it again.
- **Full water_tank test:** send `C`, then `D`. After 3 s the pump starts (max 10 s). Send `E` to stop. Needs the FULL calibration first.

After any test sketch, upload `arduino/water_tank/water_tank.ino` (or `fire_robot.ino`) again. The calibration is saved in EEPROM, so it is kept.

## Pi camera ✅ working

The Camera Rev 1.3 (OV5647) is detected on the Pi 5 with these lines in `/boot/firmware/config.txt`:

```
camera_auto_detect=0
dtoverlay=ov5647
```

Check with `rpicam-hello --list-cameras`. The picture is **rotated 90°** because of how the camera is mounted. Fix the mount or rotate the image in the server before testing YOLO.
