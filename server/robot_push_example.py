"""Example: how your autonomous robot code sends its state to the monitor app.

Call report() from your robot control loop whenever something changes (or every
~1 second). Only send the fields you have. The app shows them on the Home screen.

status should be one of:
  Idle, Patrolling, Moving Forward, Approaching, Target Reached, Extinguishing, Completed
"""
import json
import time
import urllib.request

SERVER = "http://127.0.0.1:5000"  # same Pi -> localhost. Other device -> Pi IP.


def report(**fields):
    req = urllib.request.Request(
        f"{SERVER}/api/robot",
        data=json.dumps(fields).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=1).read()
    except OSError as e:
        print("monitor server not reachable:", e)


if __name__ == "__main__":
    # Replace these with real sensor reads (ultrasonic distance, ADC for battery,
    # water level sensor, pump relay GPIO state, ...).
    report(status="Patrolling", pump_on=False, battery=85, water_level=40, distance_m=2.4)
    time.sleep(2)
    report(status="Approaching", distance_m=1.25)
    time.sleep(2)
    report(status="Extinguishing", pump_on=True, distance_m=0.4)
    time.sleep(2)
    report(status="Completed", pump_on=False, water_level=35)
