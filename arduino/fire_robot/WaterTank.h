// WaterTank.h - water tank level from a load cell + HX711, for Arduino Uno.
//
// No extra library needed. Copy this file next to your .ino and:
//
//   #include "WaterTank.h"
//   WaterTank tank(A2, A3);            // HX711 DT pin, SCK pin
//   void setup() { Serial.begin(115200); tank.begin(); }
//   void loop()  { tank.update(); int water = tank.percent(); ... }
//
// Calibration (once, saved in EEPROM - survives power off):
//   Serial Monitor 115200, "Newline":
//     C,EMPTY   with the empty tank on the sensor
//     C,FULL    with the tank filled to the top
//     C,SHOW    print calibration + live reading
//     C,RAW     toggle printing raw readings (for testing)
//
// percent() returns 0..100, or -1 if not calibrated / sensor not connected.
#pragma once
#include <Arduino.h>
#include <EEPROM.h>

class WaterTank {
 public:
  // eepromAddr: where calibration is saved (uses 13 bytes). Change if your code uses EEPROM too.
  WaterTank(uint8_t doutPin, uint8_t sckPin, int eepromAddr = 0)
      : _dout(doutPin), _sck(sckPin), _addr(eepromAddr) {}

  void begin() {
    pinMode(_sck, OUTPUT);
    digitalWrite(_sck, LOW);  // SCK high > 60us powers the HX711 down
    pinMode(_dout, INPUT_PULLUP);  // disconnected sensor reads "not ready" -> percent() = -1
    Cal c;
    EEPROM.get(_addr, c);
    if (c.magic == MAGIC) {  // load even a half-done calibration so C,SHOW is correct
      if (c.flags & 1) _empty = c.empty;
      if (c.flags & 2) _full = c.full;
      _calibrated = valid(c);
    }
  }

  // Call every loop(). Non-blocking: only reads when the HX711 has a new sample (~10 per second).
  void update() {
    long v;
    if (!readRaw(v)) return;
    _lastReadMs = millis();
    // median of last 5 removes spikes (bumps, vibration)
    _win[_wi] = v;
    _wi = (_wi + 1) % 5;
    if (_count < 5) _count++;
    long m = median();
    // exponential smoothing: water sloshes while the robot drives
    if (!_hasFiltered) {
      _filtered = m;
      _hasFiltered = true;
    } else {
      _filtered += (m - _filtered) * SMOOTH;
    }
    if (_printRaw) {
      Serial.print(F("E,raw="));
      Serial.print(v);
      Serial.print(F(" filtered="));
      Serial.print((long)_filtered);
      Serial.print(F(" pct="));
      Serial.println(percent());
    }
  }

  // 0..100, or -1 if not calibrated or no sensor data in the last second.
  int percent() const {
    if (!_calibrated || !sensorOk()) return -1;
    float p = (_filtered - _empty) * 100.0f / (float)(_full - _empty);
    if (p < 0) p = 0;
    if (p > 100) p = 100;
    return (int)(p + 0.5f);
  }

  bool sensorOk() const { return _hasFiltered && millis() - _lastReadMs < 1000; }
  bool calibrated() const { return _calibrated; }
  long raw() const { return (long)_filtered; }

  // Average ~2 s of readings and save as the empty / full point. Blocks for ~2 s.
  bool calibrateEmpty() { return calibratePoint(true); }
  bool calibrateFull() { return calibratePoint(false); }

  // Handles "C,..." lines. Returns true if the line was a tank command.
  bool handleCommand(const char *line, Stream &out) {
    if (strncmp(line, "C,", 2) != 0) return false;
    const char *cmd = line + 2;
    if (!strcmp(cmd, "EMPTY") || !strcmp(cmd, "FULL")) {
      bool empty = !strcmp(cmd, "EMPTY");
      out.println(empty ? F("E,calibrating EMPTY... keep still 2s") : F("E,calibrating FULL... keep still 2s"));
      if (calibratePoint(empty)) {
        out.print(F("E,saved "));
        out.print(empty ? F("empty=") : F("full="));
        out.println(empty ? _empty : _full);
        if (_calibrated) out.println(F("E,calibration complete"));
        else if (_empty != 0 && _full != 0 && labs(_full - _empty) <= 1000)
          out.println(F("E,ERROR empty and full are almost the same - is the tank on the load cell?"));
        else out.println(empty ? F("E,now fill the tank and send C,FULL") : F("E,now empty the tank and send C,EMPTY"));
      } else {
        out.println(F("E,ERROR no data from HX711 - check wiring"));
      }
    } else if (!strcmp(cmd, "SHOW")) {
      out.print(F("E,empty="));
      out.print(_empty);
      out.print(F(" full="));
      out.print(_full);
      out.print(F(" calibrated="));
      out.print(_calibrated);
      out.print(F(" sensor="));
      out.print(sensorOk() ? F("OK") : F("NO DATA"));
      out.print(F(" now="));
      out.print(raw());
      out.print(F(" water%="));
      out.println(percent());
    } else if (!strcmp(cmd, "RAW")) {
      _printRaw = !_printRaw;
    } else {
      out.println(F("E,unknown command. Use C,EMPTY C,FULL C,SHOW C,RAW"));
    }
    return true;
  }

 private:
  static const uint32_t MAGIC = 0x57415431UL;  // "WAT1"
  static constexpr float SMOOTH = 0.15f;       // 0..1, lower = smoother but slower
  struct Cal {
    uint32_t magic;
    long empty;
    long full;
    uint8_t flags;  // bit0 = empty set, bit1 = full set
  };
  static bool valid(const Cal &c) { return c.magic == MAGIC && c.flags == 3 && labs(c.full - c.empty) > 1000; }

  uint8_t _dout, _sck;
  int _addr;
  long _empty = 0, _full = 0;
  bool _calibrated = false;
  long _win[5] = {0};
  uint8_t _wi = 0, _count = 0;
  float _filtered = 0;
  bool _hasFiltered = false;
  unsigned long _lastReadMs = 0;
  bool _printRaw = false;

  // Reads one 24-bit sample (channel A, gain 128). Returns false if not ready yet.
  bool readRaw(long &out) {
    if (digitalRead(_dout) == HIGH) return false;
    uint32_t v = 0;
    noInterrupts();  // ~0.3 ms: keep SCK pulses short so the HX711 doesn't power down
    for (uint8_t i = 0; i < 24; i++) {
      digitalWrite(_sck, HIGH);
      delayMicroseconds(1);
      v = (v << 1) | (digitalRead(_dout) == HIGH ? 1 : 0);
      digitalWrite(_sck, LOW);
      delayMicroseconds(1);
    }
    digitalWrite(_sck, HIGH);  // 25th pulse: next read = channel A, gain 128
    delayMicroseconds(1);
    digitalWrite(_sck, LOW);
    interrupts();
    if (v == 0xFFFFFFUL) return false;  // floating / disconnected pin
    if (v & 0x800000UL) v |= 0xFF000000UL;  // sign-extend 24 -> 32 bit
    out = (long)v;
    return true;
  }

  long median() const {
    long s[5];
    for (uint8_t i = 0; i < _count; i++) s[i] = _win[i];
    for (uint8_t i = 1; i < _count; i++)  // insertion sort, max 5 items
      for (uint8_t j = i; j > 0 && s[j - 1] > s[j]; j--) {
        long t = s[j];
        s[j] = s[j - 1];
        s[j - 1] = t;
      }
    return s[_count / 2];
  }

  bool calibratePoint(bool empty) {
    long long sum = 0;
    int n = 0;
    unsigned long t0 = millis();
    while (millis() - t0 < 2500 && n < 20) {
      long v;
      if (readRaw(v)) {
        sum += v;
        n++;
      }
    }
    if (n < 5) return false;
    long avg = (long)(sum / n);
    if (empty) _empty = avg;
    else _full = avg;
    // "calibrated" once both points are set and far enough apart
    Cal c;
    EEPROM.get(_addr, c);
    if (c.magic != MAGIC) {
      c.empty = 0;
      c.full = 0;
      c.flags = 0;
    }
    c.magic = MAGIC;
    if (empty) {
      c.empty = avg;
      c.flags |= 1;
    } else {
      c.full = avg;
      c.flags |= 2;
    }
    EEPROM.put(_addr, c);
    _empty = c.empty;
    _full = c.full;
    _calibrated = valid(c);
    _filtered = avg;
    _hasFiltered = true;
    _lastReadMs = millis();
    return true;
  }
};
