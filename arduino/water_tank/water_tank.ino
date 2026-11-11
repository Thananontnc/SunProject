// Water tank sensor + pump relay test - Arduino Uno
// เซนเซอร์ถังน้ำ + ทดสอบรีเลย์ปั๊ม
//
// Wiring / การต่อสาย:
//   HX711 VCC -> 5V      HX711 GND -> GND
//   HX711 DT  -> A2      HX711 SCK -> A3
//   Load cell (4 wires) -> HX711: Red=E+  Black=E-  White=A-  Green=A+
//   Relay VCC -> 5V   Relay GND -> GND   Relay IN -> D9
//   Battery 7.4V -> buck IN.  Buck OUT+ -> relay COM,  relay NO -> pump +,  pump - -> buck OUT-
//   Set the buck output to the pump's voltage BEFORE connecting the pump.
//   ตั้งแรงดันขาออกของ buck ให้ตรงกับปั๊มก่อนต่อปั๊มเสมอ
//
// Serial Monitor: 115200 baud, "Newline". Type one command per line:
//   C   correct position          D   fire detected
//       (C and D both received -> wait 3 s -> pump ON)
//   E   fire extinguished -> pump OFF
//   C,EMPTY  C,FULL  C,SHOW  C,RAW   water sensor calibration (see WaterTank.h)
// Safety: the pump turns off by itself after 10 s, and never runs with an empty tank.
// ความปลอดภัย: ปั๊มปิดเองหลัง 10 วินาที และไม่เปิดถ้าน้ำหมด
//
// This sketch also speaks the robot serial protocol (docs/serial-protocol.md):
//   "R" at start and "S,IDLE,-1,<pump>,-1,<water%>" every 200 ms, so the app shows
//   the water level and the pump state when it's plugged into the Pi.

#include "WaterTank.h"

WaterTank tank(A2, A3);  // DT pin, SCK pin

// ---- Pump relay (from the friend's pump code) ----
const int relayPin = 9;
const int RELAY_ON = LOW;  // active LOW relay. If the pump is ON at boot, swap LOW/HIGH
const int RELAY_OFF = HIGH;
const unsigned long waitTime = 3000;      // C + D -> wait 3 s -> pump on
const unsigned long PUMP_MAX_MS = 10000;  // safety: max 10 s per run

bool correctPosition = false;
bool fireDetected = false;
bool waiting = false;
bool pumpRunning = false;
unsigned long startTime = 0;
unsigned long pumpOnTime = 0;

void pumpOn() {
  pumpRunning = true;
  pumpOnTime = millis();
  digitalWrite(relayPin, RELAY_ON);
  Serial.println(F("E,pump ON - spraying water"));
}

void pumpOff(const __FlashStringHelper *why) {
  pumpRunning = false;
  waiting = false;
  correctPosition = false;
  fireDetected = false;
  digitalWrite(relayPin, RELAY_OFF);
  Serial.print(F("E,pump OFF - "));
  Serial.println(why);
}

void handleLine(const char *input) {
  if (tank.handleCommand(input, Serial)) return;  // C,EMPTY / C,FULL / C,SHOW / C,RAW

  // exact match, so "C,EMPTY" or the Pi's "F,C,..." don't count as C / E
  if (!strcmp(input, "E") || !strcmp(input, "e")) {
    pumpOff(F("fire extinguished"));
    return;
  }
  if (!strcmp(input, "C") || !strcmp(input, "c")) {
    correctPosition = true;
    Serial.println(F("E,correct position"));
  } else if (!strcmp(input, "D") || !strcmp(input, "d")) {
    fireDetected = true;
    Serial.println(F("E,fire detected"));
  } else {
    return;  // other messages (F,... / N from the Pi) are for the main robot code
  }

  if (correctPosition && fireDetected && !waiting && !pumpRunning) {
    waiting = true;
    startTime = millis();
    Serial.println(F("E,C + D confirmed, waiting 3 seconds..."));
  }
}

char line[32];
uint8_t lineLen = 0;
unsigned long lastStatus = 0;

void setup() {
  // relay OFF before the pin becomes an output, so the pump doesn't pulse at boot
  digitalWrite(relayPin, RELAY_OFF);
  pinMode(relayPin, OUTPUT);

  Serial.begin(115200);
  tank.begin();
  Serial.println(F("R"));
  Serial.println(F("E,ready: C = correct position, D = fire detected, E = fire extinguished"));
  if (!tank.calibrated()) {
    Serial.println(F("E,water sensor not calibrated: empty tank -> C,EMPTY  then full tank -> C,FULL"));
  }
}

void loop() {
  tank.update();  // call often, never blocks

  // read serial lines without blocking (from Pi or Serial Monitor)
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

  // after 3 s, turn the pump on (unless the tank is empty)
  if (waiting && millis() - startTime >= waitTime) {
    waiting = false;
    if (tank.percent() == 0) {
      pumpOff(F("water tank empty"));
    } else {
      pumpOn();
    }
  }

  // safety
  if (pumpRunning && millis() - pumpOnTime >= PUMP_MAX_MS) pumpOff(F("10 s limit"));
  if (pumpRunning && tank.percent() == 0) pumpOff(F("water tank empty"));

  if (millis() - lastStatus >= 200) {
    lastStatus = millis();
    // S,<state>,<dist_cm>,<pump>,<battery>,<water>
    Serial.print(F("S,IDLE,-1,"));
    Serial.print(pumpRunning ? 1 : 0);
    Serial.print(F(",-1,"));
    Serial.println(tank.percent());
  }
}
