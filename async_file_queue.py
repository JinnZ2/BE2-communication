“””
async_file_queue.py — Async File-Based Communication

Two agents communicate via files in a shared directory.
Messages persist on disk — survives restarts, works across processes.

Like leaving a note on the counter:
Agent A writes a message → file appears in Agent B’s inbox
Agent B reads it when ready → processes, replies

Run: python examples/async_file_queue.py
“””

import sys
import os
import time
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(**file**))))

from core import Agent, Message
from transports import FileQueueTransport

class SensorAgent(Agent):
“”“Writes sensor readings to the queue.”””
pass

class MonitorAgent(Agent):
“”“Reads sensor data, responds with analysis.”””

```
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.readings = []

def on_message(self, msg: Message):
    if msg.verb == "STATE" and msg.topic == "sensor_reading":
        reading = msg.body
        self.readings.append(reading)
        print(f"  [monitor] Got reading: {reading}")

        # Check for anomalies
        if isinstance(reading, dict):
            temp = reading.get("temperature", 0)
            if temp > 500:
                self.reply_to(msg, {
                    "alert": "HIGH_TEMP",
                    "value": temp,
                    "action": "reduce_load",
                })
                print(f"  [monitor] ALERT: temp {temp}°C → reduce_load")
```

def main():
# Create a temp directory for the file queue
queue_dir = tempfile.mkdtemp(prefix=“agent_queue_”)
print(f”Queue dir: {queue_dir}”)

```
print("=" * 60)
print("ASYNC FILE QUEUE — PERSISTENT MESSAGING")
print("=" * 60)

# Create agents with file-based transport
sensor = SensorAgent(
    "sensor_01", "ThermalSensor",
    FileQueueTransport("sensor_01", queue_dir, poll_interval=0.2),
    capabilities=["temperature_reading"],
)
monitor = MonitorAgent(
    "monitor_01", "ThermalMonitor",
    FileQueueTransport("monitor_01", queue_dir, poll_interval=0.2),
    capabilities=["thermal_analysis", "alerting"],
)

sensor.start()
monitor.start()
time.sleep(0.5)

# ── Sensor writes readings ──
print("\n── Sensor publishing readings ──")
readings = [
    {"temperature": 420, "pressure": 14.5, "location": "sCO2_loop_A"},
    {"temperature": 480, "pressure": 16.0, "location": "sCO2_loop_A"},
    {"temperature": 530, "pressure": 18.5, "location": "sCO2_loop_A"},
    {"temperature": 490, "pressure": 17.0, "location": "sCO2_loop_A"},
]

for r in readings:
    # Publish as STATE with sensor_reading topic
    msg = Message.state(sensor.id, r)
    msg.topic = "sensor_reading"
    sensor.transport.broadcast(msg)
    sensor._log_message(msg)
    print(f"  [sensor] Published: temp={r['temperature']}°C")
    time.sleep(0.3)

# Let monitor process
time.sleep(1.0)

# ── Check what's on disk ──
print(f"\n── Files on disk ──")
for root, dirs, files in os.walk(queue_dir):
    level = root.replace(queue_dir, "").count(os.sep)
    indent = "  " * (level + 1)
    folder = os.path.basename(root)
    print(f"{indent}{folder}/")
    for f in sorted(files)[:3]:  # show first 3
        print(f"{indent}  {f}")
    if len(files) > 3:
        print(f"{indent}  ... and {len(files) - 3} more")

# ── Results ──
print(f"\n── Monitor received {len(monitor.readings)} readings ──")
alerts = [m for m in sensor.message_log if m.verb == "REPLY"]
print(f"  Alerts received by sensor: {len(alerts)}")
for a in alerts:
    print(f"    {a.body}")

# Cleanup
sensor.stop()
monitor.stop()
shutil.rmtree(queue_dir, ignore_errors=True)
print("\n  Done.")
```

if **name** == “**main**”:
main()
