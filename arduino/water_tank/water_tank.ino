// Water tank weight sensor test (Load cell + HX711) - Arduino Uno
// ทดสอบเซนเซอร์น้ำหนักถังน้ำ (Load cell + HX711)
//
// Wiring / การต่อสาย:
//   HX711 VCC -> 5V      HX711 GND -> GND
//   HX711 DT  -> A2      HX711 SCK -> A3
//   Load cell (4 wires) -> HX711: Red=E+  Black=E-  White=A-  Green=A+
//   (colours can differ - if the number goes DOWN when you add weight, that's OK too)
//
// This sketch speaks the robot serial protocol (docs/serial-protocol.md):
//   it sends "R" at start and "S,IDLE,-1,0,-1,<water%>" every 200 ms.
// So it can be plugged into the Pi right now and the app shows the water level.
//
// To put it in the main robot sketch, copy WaterTank.h next to it and use the
// 4 lines marked  // <-- TANK

#include "WaterTank.h"  // <-- TANK

WaterTank tank(A2, A3);  // <-- TANK  (DT pin, SCK pin)

char line[32];
uint8_t lineLen = 0;
unsigned long lastStatus = 0;

void setup() {
  Serial.begin(115200);
  tank.begin();  // <-- TANK
  Serial.println(F("R"));
  if (!tank.calibrated()) {
    Serial.println(F("E,water sensor not calibrated: empty tank -> C,EMPTY  then full tank -> C,FULL"));
  }
}

void loop() {
  tank.update();  // <-- TANK (call often, never blocks)

  // read serial lines (from Pi or Serial Monitor)
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      line[lineLen] = '\0';
      if (lineLen > 0) {
        if (!tank.handleCommand(line, Serial)) {
          // other messages (F,... / N from the Pi) are handled by the main robot code
        }
      }
      lineLen = 0;
    } else if (lineLen < sizeof(line) - 1) {
      line[lineLen++] = c;
    }
  }

  if (millis() - lastStatus >= 200) {
    lastStatus = millis();
    // S,<state>,<dist_cm>,<pump>,<battery>,<water>
    Serial.print(F("S,IDLE,-1,0,-1,"));
    Serial.println(tank.percent());  // <-- TANK
  }
}
