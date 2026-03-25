“””
corridor_relay.py — Superior-to-Tomah Corridor Communication

Multi-transport relay network simulating the corridor:
- CB radio (channel 19) for immediate truck-to-truck
- LoRa mesh for relay nodes at fuel stops
- HAM for long-range base station links

Three agents across three radio types, relaying information
down the corridor. Each agent uses a different transport
but the protocol is identical.

Run: python examples/corridor_relay.py
“””

import sys
import os
import time
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(**file**))))

from core import Agent, Message
from transports import CBTransport, LoRaTransport, HAMTransport

# ── Corridor Agents ────────────────────────────

class TruckAgent(Agent):
“”“Mobile agent on CB radio. Reports conditions, receives advisories.”””

```
def on_message(self, msg: Message):
    if msg.verb == "OFFER" and msg.topic == "road_advisory":
        print(f"  [{self.id}] Advisory received: {msg.body}")
    elif msg.verb == "REPLY":
        print(f"  [{self.id}] Reply: {msg.body}")
```

class RelayAgent(Agent):
“”“Fixed relay node at a fuel stop. Bridges between transports.”””

```
def __init__(self, *args, bridge_transports: list = None, **kwargs):
    super().__init__(*args, **kwargs)
    self.bridge_transports = bridge_transports or []

def on_message(self, msg: Message):
    if msg.verb == "STATE" and msg.topic == "road_conditions":
        print(f"  [{self.id}] Relaying road conditions from {msg.sender}")
        # Forward as OFFER on all bridged transports
        fwd = Message.offer(
            self.id,
            f"Relayed from {msg.sender}: {msg.body}",
            topic="road_advisory",
        )
        for t in self.bridge_transports:
            t.broadcast(fwd)
            print(f"  [{self.id}] → forwarded to {t.transport_name}")
```

class BaseStation(Agent):
“”“Fixed base station on HAM. Aggregates corridor data.”””

```
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.reports = []

def on_message(self, msg: Message):
    if msg.verb in ("STATE", "OFFER"):
        self.reports.append({
            "from": msg.sender,
            "body": msg.body,
            "time": msg.timestamp,
        })
        print(f"  [{self.id}] Logged: {msg.verb} from {msg.sender}")
```

def main():
# Shared simulator directories (each radio type gets its own “frequency”)
cb_dir = tempfile.mkdtemp(prefix=“cb_ch19_”)
lora_dir = tempfile.mkdtemp(prefix=“lora_mesh_”)
ham_dir = tempfile.mkdtemp(prefix=“ham_2m_”)

```
print("=" * 60)
print("CORRIDOR RELAY — SUPERIOR TO TOMAH")
print("=" * 60)
print(f"  CB channel dir:   {cb_dir}")
print(f"  LoRa mesh dir:    {lora_dir}")
print(f"  HAM channel dir:  {ham_dir}")

# ── Create agents on different transports ──

# Truck on CB (channel 19)
truck = TruckAgent(
    "truck_northbound", "TruckNode",
    CBTransport("Northbound", channel=19, channel_dir=cb_dir),
    capabilities=["road_reporting", "weather_observation"],
)

# Relay node at fuel stop (LoRa — long range, low power)
relay_lora_transport = LoRaTransport(
    None, agent_id="relay_hayward", channel_dir=lora_dir
)
relay_lora = RelayAgent(
    "relay_hayward", "FuelStopRelay",
    relay_lora_transport,
    capabilities=["relay", "corridor_bridge"],
)

# Same relay also on CB to hear the truck, bridges to LoRa
relay_cb = RelayAgent(
    "relay_hayward_cb", "FuelStopRelay_CB",
    CBTransport("Hayward_Relay", channel=19, channel_dir=cb_dir),
    capabilities=["relay"],
    bridge_transports=[relay_lora_transport],  # bridge CB→LoRa
)

# Base station on HAM (long range)
# Also has LoRa to hear relay nodes
base_ham = BaseStation(
    "base_superior", "BaseStation",
    HAMTransport("KD0SUP", channel_dir=ham_dir),
    capabilities=["aggregation", "analysis"],
)

base_lora = BaseStation(
    "base_superior_lora", "BaseStation_LoRa",
    LoRaTransport(None, agent_id="base_superior_lora", channel_dir=lora_dir),
    capabilities=["aggregation"],
)

all_agents = [truck, relay_cb, relay_lora, base_lora, base_ham]

# ── Start all agents ──
print("\n── Starting corridor network ──")
for a in all_agents:
    a.start()
time.sleep(0.5)

# ── Truck reports road conditions ──
print("\n── Truck reports conditions ──")
conditions = {
    "location": "Hayward, WI",
    "road": "US-63",
    "surface": "black_ice",
    "visibility": "low",
    "wind_chill": -35,
}
# Truck broadcasts on CB
road_msg = Message.state(truck.id, conditions)
road_msg.topic = "road_conditions"
truck.transport.broadcast(road_msg)
truck._log_message(road_msg)
print(f"  [truck] Broadcast: {conditions}")

# Give the relay time to pick up the CB broadcast
time.sleep(1.0)

# Now have truck also broadcast the query
print(f"\n── Truck asks for conditions ahead ──")
truck.ask(
    "Road conditions between Hayward and Superior?",
    topic="road_query",
)

# Let the full relay chain propagate (CB → relay_cb → LoRa → base_lora)
time.sleep(2.0)
print(f"\n── Base station reports ──")
print(f"  LoRa base received: {len(base_lora.reports)} reports")
for r in base_lora.reports:
    print(f"    from {r['from']}: {str(r['body'])[:60]}")
# Debug: show all messages the base saw
print(f"  LoRa base message log:")
for m in base_lora.message_log:
    print(f"    {m.verb} from {m.sender} [{m.topic}]")

# ── Check what base station received ──
print(f"\n── Message counts ──")
for a in all_agents:
    print(f"  {a.id}: {len(a.message_log)} messages via {a.transport.transport_name}")
    for m in a.message_log:
        print(f"    {m.verb} from {m.sender} [{m.topic}] body={str(m.body)[:50]}")

# ── Cleanup ──
print(f"\n── Shutting down ──")
for a in all_agents:
    a.stop()
shutil.rmtree(cb_dir, ignore_errors=True)
shutil.rmtree(lora_dir, ignore_errors=True)
shutil.rmtree(ham_dir, ignore_errors=True)
print("  Done.")
```

if **name** == “**main**”:
main()
