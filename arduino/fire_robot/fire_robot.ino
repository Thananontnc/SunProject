// fire_robot.ino - starter driving code for the fire robot (Arduino Uno)
// โค้ดเริ่มต้นสำหรับขับหุ่นดับไฟ (Arduino Uno)
//
// Follows docs/serial-protocol.md:
//   Pi -> Arduino : F,<L|C|R>,<offset>,<size>,<conf>   or   N        (10x per second)
//   Arduino -> Pi : R once, then S,<state>,<dist_cm>,<pump>,<battery>,<water> every 200 ms
//
// This is a STARTER: it compiles and follows the protocol, but the speeds and
// distances below must be tuned on the real robot. Lift the wheels off the
// table for the first test.
// นี่คือโค้ดตั้งต้น: ค่าความเร็วและระยะด้านล่างต้องปรับกับหุ่นจริง ทดสอบครั้งแรกให้ยกล้อขึ้นจากพื้น
//
// ---------------- Wiring / การต่อสาย ----------------
//   L298N  ENA -> D5 (PWM)   IN1 -> D7   IN2 -> D8     left motors  (2 motors on OUT1/OUT2)
//   L298N  ENB -> D6 (PWM)   IN3 -> D4   IN4 -> D10    right motors (2 motors on OUT3/OUT4)
//          Remove the ENA/ENB jumpers so the PWM speed control works.
//          ถอดจัมเปอร์ ENA/ENB ออก ไม่งั้นคุมความเร็วไม่ได้
//   HC-SR04 TRIG -> D11   ECHO -> D12   VCC -> 5V
//   Relay IN -> D9 (pump)                          most relay modules are active-LOW
//   HX711  DT -> A2   SCK -> A3                    water tank (WaterTank.h)
//   A4/A5 left free for an I2C heat sensor (MLX90614 / AMG8833)
//   All GNDs together: Arduino, L298N, motor battery, relay.
//   ต่อ GND ทุกตัวเข้าด้วยกัน
//
// ---------------- Bench test without the Pi / ทดสอบโดยไม่มี Pi ----------------
// Serial Monitor, 115200 baud, "Newline". Each T command runs for 1 second:
//   T,F  forward     T,B  backward     T,L  turn left     T,R  turn right     T,P  pump
// Use these first to check the motor directions. If one side spins the wrong
// way, set LEFT_REVERSED or RIGHT_REVERSED below.
// ใช้คำสั่ง T เช็คทิศทางล้อก่อน ถ้าล้อฝั่งไหนหมุนกลับด้าน ให้แก้ LEFT_REVERSED / RIGHT_REVERSED
// Then type F / N lines by hand (see docs/serial-protocol.md section 5).

#include "WaterTank.h"

// ---------------- Pins ----------------
const uint8_t PIN_ENA = 5;
const uint8_t PIN_IN1 = 7;
const uint8_t PIN_IN2 = 8;
const uint8_t PIN_ENB = 6;
const uint8_t PIN_IN3 = 4;
const uint8_t PIN_IN4 = 10;
const uint8_t PIN_TRIG = 11;
const uint8_t PIN_ECHO = 12;
const uint8_t PIN_RELAY = 9;

// ---------------- Settings to tune / ค่าที่ต้องปรับ ----------------
const bool LEFT_REVERSED = false;    // flip if the left wheels spin backward on T,F
const bool RIGHT_REVERSED = false;   // flip if the right wheels spin backward on T,F
const bool RELAY_ACTIVE_LOW = true;  // most blue relay modules: LOW = ON

const int SPEED_FORWARD = 180;   // 0..255 PWM, far from the fire
const int SPEED_APPROACH = 120;  // close to the fire
const int SPEED_TURN = 150;      // turning in place
const int SPEED_PATROL = 110;    // slow search spin
// Gear motors usually stall below ~90-100 PWM. Raise the speeds if the robot hums but doesn't move.

const int OFFSET_DEADBAND = 15;  // |offset| <= 15 counts as centered
const int DIST_APPROACH_CM = 60; // slow down below this
const int DIST_TARGET_CM = 25;   // stop in front of the fire
const int DIST_MIN_CM = 15;      // never drive closer than this
// If the ultrasonic gets no echo (-1), the fire box size (% of image) is used instead:
const int SIZE_APPROACH = 15;
const int SIZE_TARGET = 30;

const unsigned long LINK_TIMEOUT_MS = 1000;  // no message from Pi -> stop everything
const unsigned long LOST_FIRE_MS = 2000;     // N for 2 s while driving -> PATROL
const unsigned long FIRE_OUT_MS = 3000;      // N for 3 s while spraying -> DONE
const unsigned long PUMP_MAX_MS = 10000;     // pump max ON time, then pause and re-check
const unsigned long PUMP_REST_MS = 2000;     // pause after the pump turns off
const unsigned long DONE_HOLD_MS = 3000;     // stay in DONE before patrolling again
const unsigned long PATROL_SPIN_MS = 400;    // patrol: spin this long...
const unsigned long PATROL_PAUSE_MS = 600;   // ...then stop so the camera gets a sharp image

// ---------------- State ----------------
enum State { IDLE, PATROL, FORWARD, APPROACH, TARGET, EXTINGUISH, DONE };
const char *const STATE_NAMES[] = {"IDLE", "PATROL", "FORWARD", "APPROACH", "TARGET", "EXTINGUISH", "DONE"};

State state = IDLE;
unsigned long stateSinceMs = 0;

struct Fire {
  bool visible = false;  // last message was F
  char pos = 'C';
  int offset = 0;
  int size = 0;
  int conf = 0;
} fire;

bool haveLink = false;
unsigned long lastMsgMs = 0;
unsigned long lastFireMs = 0;

bool pumpIsOn = false;
bool sprayed = false;  // pump ran on this fire: losing it now means it went out
unsigned long pumpOnMs = 0;
unsigned long pumpOffMs = 0;
unsigned long lastWaterWarnMs = 0;

int distanceCm = -1;
uint8_t echoMisses = 0;
unsigned long lastPingMs = 0;

unsigned long testUntilMs = 0;
unsigned long lastStatusMs = 0;

char line[32];
uint8_t lineLen = 0;

WaterTank tank(A2, A3);

// ---------------- Motors and pump ----------------
void setMotor(uint8_t en, uint8_t inA, uint8_t inB, int speed, bool reversed) {
  if (reversed) speed = -speed;
  speed = constrain(speed, -255, 255);
  digitalWrite(inA, speed > 0 ? HIGH : LOW);
  digitalWrite(inB, speed < 0 ? HIGH : LOW);
  analogWrite(en, abs(speed));
}

// left/right: -255 (full back) .. 255 (full forward)
void drive(int left, int right) {
  setMotor(PIN_ENA, PIN_IN1, PIN_IN2, left, LEFT_REVERSED);
  setMotor(PIN_ENB, PIN_IN3, PIN_IN4, right, RIGHT_REVERSED);
}

void stopMotors() { drive(0, 0); }
void turnLeft(int speed) { drive(-speed, speed); }
void turnRight(int speed) { drive(speed, -speed); }

void pumpOn() {
  if (!pumpIsOn) pumpOnMs = millis();
  pumpIsOn = true;
  sprayed = true;
  digitalWrite(PIN_RELAY, RELAY_ACTIVE_LOW ? LOW : HIGH);
}

void pumpOff() {
  if (pumpIsOn) pumpOffMs = millis();
  pumpIsOn = false;
  digitalWrite(PIN_RELAY, RELAY_ACTIVE_LOW ? HIGH : LOW);
}

void stopAll() {
  stopMotors();
  pumpOff();
}

void setState(State s) {
  if (s == state) return;
  if (s == PATROL || s == IDLE) sprayed = false;  // looking for a new fire
  state = s;
  stateSinceMs = millis();
}

// ---------------- Sensors ----------------
// One ping every 60 ms. Blocks up to 25 ms (about 4 m). Keeps the last value for
// up to 3 missed echoes so one bad ping doesn't look like "no obstacle".
void updateDistance() {
  if (millis() - lastPingMs < 60) return;
  lastPingMs = millis();
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long us = pulseIn(PIN_ECHO, HIGH, 25000UL);
  if (us == 0) {
    if (echoMisses < 3) echoMisses++;
    else distanceCm = -1;
  } else {
    echoMisses = 0;
    distanceCm = us / 58;
  }
}

// TODO heat sensor: return true only if the sensor sees real heat in front of
// the robot (so a photo of fire doesn't start the pump). Until a sensor is
// chosen, the camera alone decides.
// TODO เซนเซอร์ความร้อน: คืนค่า true เมื่อวัดความร้อนได้จริง (กันภาพถ่ายไฟ) ตอนนี้ใช้กล้องอย่างเดียว
bool heatConfirmsFire() { return true; }

bool waterEmpty() { return tank.percent() == 0; }  // -1 (no sensor) is not "empty"

void warnWaterEmpty() {
  if (millis() - lastWaterWarnMs < 5000 && lastWaterWarnMs != 0) return;
  lastWaterWarnMs = millis();
  Serial.println(F("E,water tank empty"));
}

// ---------------- Serial ----------------
void handleTest(char cmd) {
  if (haveLink) {
    Serial.println(F("E,T commands only work when the Pi is not sending"));
    return;
  }
  switch (cmd) {
    case 'F': drive(SPEED_FORWARD, SPEED_FORWARD); break;
    case 'B': drive(-SPEED_FORWARD, -SPEED_FORWARD); break;
    case 'L': turnLeft(SPEED_TURN); break;
    case 'R': turnRight(SPEED_TURN); break;
    case 'P': pumpOn(); break;
    default:
      Serial.println(F("E,unknown test. Use T,F T,B T,L T,R T,P"));
      return;
  }
  testUntilMs = millis() + 1000;
}

void handleLine(char *msg) {
  if (tank.handleCommand(msg, Serial)) return;

  if (msg[0] == 'F' && msg[1] == ',') {
    char *pos = strtok(msg + 2, ",");
    char *off = strtok(NULL, ",");
    char *size = strtok(NULL, ",");
    char *conf = strtok(NULL, ",");
    if (!pos || !off || !size || !conf) {
      Serial.println(F("E,bad F message"));
      return;
    }
    fire.visible = true;
    fire.pos = pos[0];
    fire.offset = constrain(atoi(off), -100, 100);
    fire.size = constrain(atoi(size), 0, 100);
    fire.conf = constrain(atoi(conf), 0, 100);
    lastFireMs = millis();
  } else if (msg[0] == 'N' && msg[1] == '\0') {
    fire.visible = false;
  } else if (msg[0] == 'T' && msg[1] == ',') {
    handleTest(msg[2]);
    return;
  } else {
    Serial.print(F("E,unknown message: "));
    Serial.println(msg);
    return;
  }
  // a valid F or N from the Pi
  lastMsgMs = millis();
  haveLink = true;
  testUntilMs = 0;
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      line[lineLen] = '\0';
      if (lineLen > 0) handleLine(line);
      lineLen = 0;
    } else if (lineLen < sizeof(line) - 1) {
      line[lineLen++] = c;
    }
  }
}

void sendStatus() {
  if (millis() - lastStatusMs < 200) return;
  lastStatusMs = millis();
  Serial.print(F("S,"));
  Serial.print(STATE_NAMES[state]);
  Serial.print(',');
  Serial.print(distanceCm);
  Serial.print(',');
  Serial.print(pumpIsOn ? 1 : 0);
  Serial.print(F(",-1,"));  // battery: no sensor yet (voltage divider on A0 later)
  Serial.println(tank.percent());
}

// ---------------- Driving logic ----------------
// FORWARD / APPROACH: steer toward the fire, slow down when close.
void driveToFire(unsigned long now) {
  if (now - lastFireMs > LOST_FIRE_MS) {
    stopMotors();
    setState(PATROL);
    return;
  }
  bool haveDist = distanceCm >= 0;
  bool close = haveDist ? distanceCm < DIST_APPROACH_CM : fire.size >= SIZE_APPROACH;
  bool atTarget = haveDist ? distanceCm <= DIST_TARGET_CM : fire.size >= SIZE_TARGET;
  bool centered = abs(fire.offset) <= OFFSET_DEADBAND;

  if (!fire.visible) {  // short dropout (one missed frame): wait, don't drive blind
    stopMotors();
    return;
  }
  if (atTarget && centered) {
    stopMotors();
    setState(TARGET);
    return;
  }
  setState(close ? APPROACH : FORWARD);

  if (fire.offset < -OFFSET_DEADBAND) {
    turnLeft(SPEED_TURN);
  } else if (fire.offset > OFFSET_DEADBAND) {
    turnRight(SPEED_TURN);
  } else if (haveDist && distanceCm <= DIST_MIN_CM) {
    stopMotors();  // too close, never drive further in
  } else {
    int speed = close ? SPEED_APPROACH : SPEED_FORWARD;
    drive(speed, speed);
  }
}

void runStateMachine(unsigned long now) {
  switch (state) {
    case IDLE:  // the Pi just started talking
      setState(PATROL);
      break;

    case PATROL: {
      if (fire.visible) {
        stopMotors();
        setState(FORWARD);
        break;
      }
      unsigned long t = (now - stateSinceMs) % (PATROL_SPIN_MS + PATROL_PAUSE_MS);
      if (t < PATROL_SPIN_MS) turnRight(SPEED_PATROL);
      else stopMotors();
      break;
    }

    case FORWARD:
    case APPROACH:
      driveToFire(now);
      break;

    case TARGET:
      stopMotors();
      if (now - lastFireMs > LOST_FIRE_MS) {
        setState(sprayed ? DONE : PATROL);  // went out during the pump rest -> DONE
        break;
      }
      if (!fire.visible) break;
      if (abs(fire.offset) > OFFSET_DEADBAND ||                      // fire moved sideways
          (distanceCm >= 0 && distanceCm > DIST_TARGET_CM + 10)) {   // or robot is too far now
        setState(APPROACH);
        break;
      }
      if (waterEmpty()) {
        warnWaterEmpty();
        break;
      }
      if (pumpOffMs != 0 && now - pumpOffMs < PUMP_REST_MS) break;
      if (!heatConfirmsFire()) break;
      pumpOn();
      setState(EXTINGUISH);
      break;

    case EXTINGUISH:
      stopMotors();
      if (waterEmpty()) {
        pumpOff();
        warnWaterEmpty();
        setState(TARGET);
      } else if (now - lastFireMs > FIRE_OUT_MS) {
        pumpOff();
        setState(DONE);
      } else if (now - pumpOnMs >= PUMP_MAX_MS) {
        pumpOff();  // rest, then TARGET checks again
        setState(TARGET);
      }
      break;

    case DONE:
      stopAll();
      if (now - stateSinceMs >= DONE_HOLD_MS) setState(PATROL);
      break;
  }
}

// ---------------- Main ----------------
void setup() {
  // relay OFF before the pin becomes an output, so the pump doesn't pulse at boot
  digitalWrite(PIN_RELAY, RELAY_ACTIVE_LOW ? HIGH : LOW);
  pinMode(PIN_RELAY, OUTPUT);
  pumpOff();

  pinMode(PIN_ENA, OUTPUT);
  pinMode(PIN_IN1, OUTPUT);
  pinMode(PIN_IN2, OUTPUT);
  pinMode(PIN_ENB, OUTPUT);
  pinMode(PIN_IN3, OUTPUT);
  pinMode(PIN_IN4, OUTPUT);
  stopMotors();

  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);

  Serial.begin(115200);
  tank.begin();
  Serial.println(F("R"));
  if (!tank.calibrated()) {
    Serial.println(F("E,water sensor not calibrated: empty tank -> C,EMPTY  then full tank -> C,FULL"));
  }
}

void loop() {
  tank.update();
  readSerial();
  updateDistance();
  unsigned long now = millis();  // after reading, so now >= lastMsgMs / lastFireMs

  if (haveLink && now - lastMsgMs > LINK_TIMEOUT_MS) {
    // safety rule: Pi crashed or cable unplugged
    haveLink = false;
    fire.visible = false;
    stopAll();
    setState(IDLE);
    Serial.println(F("E,no message from Pi for 1 s - stopped"));
  }

  if (haveLink) {
    runStateMachine(now);
  } else if (testUntilMs != 0 && (long)(now - testUntilMs) >= 0) {
    stopAll();  // bench test (T,...) finished
    testUntilMs = 0;
  }

  sendStatus();
}
