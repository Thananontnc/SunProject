# Pi ↔ Arduino Serial Protocol / โปรโตคอลสื่อสาร Pi ↔ Arduino

This is the **only agreement** between the Pi side (camera, AI, app) and the Arduino side (motors, sensors, pump). Each side can be written and tested separately as long as both follow this document.

เอกสารนี้คือ **ข้อตกลงเดียว** ระหว่างฝั่ง Pi (กล้อง, AI, แอป) กับฝั่ง Arduino (มอเตอร์, เซนเซอร์, ปั๊ม) ถ้าทั้งสองฝั่งทำตามเอกสารนี้ ก็แยกกันเขียนและทดสอบได้เลย

---

## 1. Connection / การเชื่อมต่อ

| Item | Value |
|---|---|
| Cable / สาย | USB cable from Pi 5 to Arduino Uno (Pi sees it as `/dev/ttyACM0`) |
| Baud rate | **115200** |
| Format / รูปแบบ | ASCII text, one message per line, ends with `\n` (newline) |
| Fields / ฟิลด์ | separated by comma `,` with no spaces |
| Unknown value / ไม่มีค่า | `-1` |

> Note: opening the serial port **resets the Arduino** (it restarts in ~2 s). The Pi must wait for the `R` (ready) message before sending.
>
> หมายเหตุ: เมื่อ Pi เปิดพอร์ต serial แล้ว **Arduino จะรีเซ็ตตัวเอง** (ใช้เวลาประมาณ 2 วินาที) Pi ต้องรอข้อความ `R` ก่อนจึงเริ่มส่งคำสั่ง

---

## 2. Pi → Arduino (what the camera sees / สิ่งที่กล้องเห็น)

The Pi sends one of these **10 times per second** (every 100 ms), even when nothing changes.
Pi ส่งข้อความเหล่านี้ **10 ครั้งต่อวินาที** (ทุก 100 ms) แม้ค่าจะไม่เปลี่ยน

### `F` — fire seen / เห็นไฟ
```
F,<pos>,<offset>,<size>,<conf>
```
| Field | Meaning (EN) | ความหมาย (TH) | Example |
|---|---|---|---|
| `pos` | `L`, `C` or `R`: fire is left, center or right | ไฟอยู่ ซ้าย / กลาง / ขวา | `C` |
| `offset` | horizontal offset of the fire center from the image center, **-100 … 100** (-100 = far left, 0 = center, 100 = far right). Use this for smooth steering. | ระยะเยื้องของไฟจากกึ่งกลางภาพ -100 (ซ้ายสุด) ถึง 100 (ขวาสุด) ใช้เลี้ยวแบบนุ่มนวล | `-12` |
| `size` | fire box area as **% of the image, 0 … 100**. Bigger = closer. | ขนาดกรอบไฟเป็น % ของภาพ ยิ่งใหญ่ยิ่งใกล้ | `8` |
| `conf` | confidence **0 … 100** | ความมั่นใจของ AI 0–100 | `87` |

Example / ตัวอย่าง: `F,C,-12,8,87`

### `N` — no fire / ไม่เห็นไฟ
```
N
```

### Safety rule / กฎความปลอดภัย (Arduino must do this / Arduino ต้องทำ)
- If the Arduino receives **no message for 1 second** (Pi crashed, cable unplugged), it must **stop the motors and turn the pump off**.
- ถ้า Arduino **ไม่ได้รับข้อความเกิน 1 วินาที** (Pi ค้าง หรือสายหลุด) ต้อง **หยุดมอเตอร์และปิดปั๊มทันที**

---

## 3. Arduino → Pi (robot state / สถานะหุ่นยนต์)

### `R` — ready / พร้อมทำงาน
Send once in `setup()`. / ส่งครั้งเดียวตอนจบ `setup()`
```
R
```

### `S` — status / สถานะ
Send **5 times per second** (every 200 ms). / ส่ง **5 ครั้งต่อวินาที** (ทุก 200 ms)
```
S,<state>,<dist_cm>,<pump>,<battery>,<water>
```
| Field | Meaning (EN) | ความหมาย (TH) | Example |
|---|---|---|---|
| `state` | one of the states in section 4 | สถานะ ดูหัวข้อที่ 4 | `APPROACH` |
| `dist_cm` | ultrasonic distance in cm, `-1` if no echo | ระยะจาก Ultrasonic (cm), `-1` ถ้าวัดไม่ได้ | `45` |
| `pump` | `1` = pump ON, `0` = OFF | `1` = ปั๊มเปิด, `0` = ปิด | `0` |
| `battery` | battery % 0–100, `-1` if no sensor | แบตเตอรี่ %, `-1` ถ้าไม่มีเซนเซอร์ | `82` |
| `water` | water tank % 0–100, `-1` if no sensor | ระดับน้ำในถัง %, `-1` ถ้าไม่มีเซนเซอร์ | `60` |

Example / ตัวอย่าง: `S,APPROACH,45,0,82,60`

### `E` — error or log / ข้อผิดพลาด หรือ log
Free text that the Pi prints to its log. / ข้อความอิสระ Pi จะพิมพ์ลง log
```
E,water tank empty
```

### `C` — water sensor calibration (Serial Monitor only) / คาลิเบรตเซนเซอร์น้ำหนักถังน้ำ (พิมพ์ใน Serial Monitor)
Typed by a person, not sent by the Pi. Code: `arduino/water_tank/WaterTank.h`.
พิมพ์เองโดยคน ไม่ได้ส่งมาจาก Pi โค้ดอยู่ที่ `arduino/water_tank/WaterTank.h`

| Command | Meaning (EN) | ความหมาย (TH) |
|---|---|---|
| `C,EMPTY` | save the reading with the empty tank | บันทึกค่าตอนถังว่าง |
| `C,FULL` | save the reading with the full tank | บันทึกค่าตอนถังเต็ม |
| `C,SHOW` | print the calibration and the current water % | แสดงค่าคาลิเบรตและ % น้ำตอนนี้ |
| `C,RAW` | turn raw readings on/off (for testing) | เปิด/ปิดการพิมพ์ค่าดิบ (ไว้ทดสอบ) |

### `T` — bench test (Serial Monitor only) / ทดสอบบนโต๊ะ (พิมพ์ใน Serial Monitor)
Runs for 1 second, only when the Pi is not sending. Code: `arduino/fire_robot/fire_robot.ino`.
ทำงาน 1 วินาที และใช้ได้เฉพาะตอนที่ Pi ไม่ได้ส่งข้อความ โค้ดอยู่ที่ `arduino/fire_robot/fire_robot.ino`

| Command | Meaning (EN) | ความหมาย (TH) |
|---|---|---|
| `T,F` / `T,B` | drive forward / backward | วิ่งไปข้างหน้า / ถอยหลัง |
| `T,L` / `T,R` | turn left / right in place | หมุนซ้าย / ขวา อยู่กับที่ |
| `T,P` | pump on | เปิดปั๊ม |

The `water` field in `S` comes from this sensor (load cell + HX711 on pins A2/A3).
ค่า `water` ในข้อความ `S` มาจากเซนเซอร์นี้ (Load cell + HX711 ต่อที่ขา A2/A3)

---

## 4. Robot states / สถานะของหุ่นยนต์

The Arduino decides the state. The app shows it on the Home screen.
Arduino เป็นผู้ตัดสินสถานะ และแอปจะแสดงสถานะนี้ในหน้า Home

| `state` | App shows / แอปแสดง | When / เมื่อไหร่ |
|---|---|---|
| `IDLE` | Idle | just started, waiting / เพิ่งเปิดเครื่อง กำลังรอ |
| `PATROL` | Patrolling | no fire, searching (e.g. turning slowly) / ไม่เห็นไฟ กำลังค้นหา (เช่น หมุนช้า ๆ) |
| `FORWARD` | Moving Forward | fire seen, far, driving to it / เห็นไฟแต่ยังไกล กำลังวิ่งเข้าหา |
| `APPROACH` | Approaching | fire close (e.g. < 60 cm), driving slowly / ไฟใกล้แล้ว (เช่น < 60 cm) วิ่งช้าลง |
| `TARGET` | Target Reached | stopped in front of fire (e.g. ≤ 25 cm) / หยุดหน้าไฟแล้ว (เช่น ≤ 25 cm) |
| `EXTINGUISH` | Extinguishing | pump ON / กำลังฉีดน้ำ |
| `DONE` | Completed | fire gone after spraying / ไฟดับแล้วหลังฉีดน้ำ |

### Suggested logic / ลำดับการทำงานที่แนะนำ
```
PATROL ──(F received)──► FORWARD ──(dist < 60cm)──► APPROACH ──(dist ≤ 25cm and pos = C)──► TARGET
   ▲                                                                                         │
   │                                                                                         ▼
 DONE ◄──(N for 3 s while spraying)── EXTINGUISH ◄─────────────────────────────────── pump ON
```
- Steering: if `offset < -15` turn left, if `offset > 15` turn right, else go straight. / การเลี้ยว: `offset < -15` เลี้ยวซ้าย, `offset > 15` เลี้ยวขวา, นอกนั้นตรงไป
- Lost the fire while driving (`N` for 2 s) → back to `PATROL`. / ถ้าเห็นไฟหายระหว่างวิ่ง (`N` นาน 2 วินาที) → กลับไป `PATROL`
- **Pump max ON time: 10 s**, then turn it off and check again (saves water, protects the pump). / **เปิดปั๊มได้นานสุด 10 วินาที** จากนั้นปิดแล้วตรวจใหม่ (ประหยัดน้ำและถนอมปั๊ม)
- Never drive closer than **15 cm** (ultrasonic), even if the fire is still there. / ห้ามเข้าใกล้เกิน **15 cm** (วัดด้วย Ultrasonic) แม้ไฟยังไม่ดับ
- Water `0`% → do not turn the pump on; send `E,water tank empty`. / น้ำหมด → ห้ามเปิดปั๊ม และส่ง `E,water tank empty`

---

## 5. Test without the other side / ทดสอบโดยไม่ต้องรออีกฝั่ง

**Arduino side (no Pi needed) / ฝั่ง Arduino (ไม่ต้องมี Pi):**
Starter sketch: `arduino/fire_robot/` (motors, ultrasonic, pump, water sensor, all of this document). Pins and speeds are at the top of the file.
โค้ดตั้งต้น: `arduino/fire_robot/` (มอเตอร์, Ultrasonic, ปั๊ม, เซนเซอร์น้ำ ตามเอกสารนี้ทั้งหมด) ขาและความเร็วอยู่ด้านบนของไฟล์

Open Arduino IDE → Serial Monitor → 115200 baud, "Newline". Type the messages by hand:
เปิด Arduino IDE → Serial Monitor → 115200 baud, เลือก "Newline" แล้วพิมพ์ข้อความเองได้เลย
```
F,L,-60,2,90     ← robot should turn left / หุ่นควรเลี้ยวซ้าย
F,C,0,10,90      ← go straight / ตรงไป
N                ← no fire / ไม่เห็นไฟ
(type nothing for 1 s → motors must stop / ไม่พิมพ์อะไร 1 วินาที → มอเตอร์ต้องหยุด)
```
Tip: the 1-second safety stop means a typed message only moves the robot for 1 s. Lift the wheels off the table while testing.
เคล็ดลับ: เพราะมีกฎหยุดเองใน 1 วินาที ข้อความที่พิมพ์จะทำให้หุ่นขยับแค่ 1 วินาที ควรยกล้อขึ้นจากพื้นขณะทดสอบ

**Pi side (no Arduino needed) / ฝั่ง Pi (ไม่ต้องมี Arduino):**
Run the server with `SIMULATE=1`. It fakes the robot's states, so the app can be tested without the Arduino.
รัน server ด้วย `SIMULATE=1` จะจำลองสถานะหุ่นยนต์ให้ ทดสอบแอปได้โดยไม่ต้องมี Arduino

---

## 6. Wiring notes / หมายเหตุการต่อสาย

- Pump → **relay module or MOSFET** on an Arduino pin (both L298N channels are used by the wheels). / ปั๊ม → **Relay หรือ MOSFET** ต่อกับขา Arduino (L298N ทั้งสองช่องใช้กับล้อไปแล้ว)
- Ultrasonic HC-SR04 → Arduino (5V). **Do not connect Echo to the Pi** (the Pi's pins take only 3.3V). / Ultrasonic → ต่อกับ Arduino (5V) **ห้ามต่อขา Echo เข้า Pi** (ขา Pi รับได้แค่ 3.3V)
- Motor battery separate from the Pi power. **Connect all GNDs together** (Arduino, L298N, motor battery). / แบตมอเตอร์แยกจากไฟเลี้ยง Pi และ **ต่อ GND ทุกตัวเข้าด้วยกัน** (Arduino, L298N, แบตมอเตอร์)
- Pi 5 power: **5V 5A**. / ไฟเลี้ยง Pi 5: **5V 5A**
- Water weight sensor: HX711 **DT → A2, SCK → A3**, VCC → 5V. Don't use A2/A3 for anything else. / เซนเซอร์น้ำหนักถังน้ำ: HX711 **DT → A2, SCK → A3**, VCC → 5V และห้ามใช้ขา A2/A3 กับอย่างอื่น
