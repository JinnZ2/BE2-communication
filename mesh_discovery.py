“””
mesh_discovery.py — Dynamic Mesh Discovery

Agents arrive at different times, discover each other,
find help by capability, handle agents going offline.

Shows:
- Late arrival (agent joins after others are running)
- Capability-based discovery (“who can do X?”)
- Graceful departure (agent says BYE, peers update)
- Working around missing agents

Run: python examples/mesh_discovery.py
“””

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(**file**))))

from core import Agent, Message
from transports import LocalHub, LocalTransport

class WorkerAgent(Agent):
“”“Generic worker that responds to queries about its capabilities.”””

```
def on_message(self, msg: Message):
    if msg.verb == "QUERY" and msg.topic == "capability_check":
        # Someone asking what we can do
        self.reply_to(msg, {
            "agent": self.id,
            "capabilities": self.capabilities,
            "status": self.state.status,
        })

    elif msg.verb == "STUCK":
        # Someone needs help — check if we can assist
        needed = msg.body
        if any(cap in str(needed) for cap in self.capabilities):
            self.offer(
                f"I can help with: {needed}",
                topic=msg.topic,
                recipient=msg.sender,
            )
```

def main():
hub = LocalHub()

```
print("=" * 60)
print("MESH DISCOVERY — DYNAMIC AGENT NETWORK")
print("=" * 60)

# ── Phase 1: Two agents start ──
print("\n── Phase 1: Initial agents ──")
thermal = WorkerAgent(
    "thermal_01", "ThermalMonitor",
    LocalTransport("thermal_01", hub),
    capabilities=["temperature_sensing", "cooling_control"],
)
encoder = WorkerAgent(
    "encoder_01", "LightBridgeEncoder",
    LocalTransport("encoder_01", hub),
    capabilities=["geometric_encoding", "vertex_mapping"],
)

thermal.start()
encoder.start()
time.sleep(0.3)

print(f"  thermal_01 peers: {list(thermal.peers.keys())}")
print(f"  encoder_01 peers: {list(encoder.peers.keys())}")

# ── Phase 2: Late arrival ──
print("\n── Phase 2: Validator arrives late ──")
validator = WorkerAgent(
    "validator_01", "HamiltonianValidator",
    LocalTransport("validator_01", hub),
    capabilities=["lattice_validation", "path_checking"],
)
validator.start()
time.sleep(0.3)

# Validator announced — but only agents listening at that moment heard it.
# The others need to re-announce or validator needs to query.
# Let's have everyone re-announce (heartbeat pattern):
thermal.announce()
encoder.announce()
time.sleep(0.3)

print(f"  validator_01 peers: {list(validator.peers.keys())}")
print(f"  thermal_01 peers: {list(thermal.peers.keys())}")

# ── Phase 3: Capability-based discovery ──
print("\n── Phase 3: Find who can validate ──")
helpers = encoder.find_peers(capability="lattice_validation")
for h in helpers:
    print(f"  Found: {h.agent_id} offers {h.offers}")

# ── Phase 4: Ask for help ──
print("\n── Phase 4: Encoder gets stuck ──")
encoder.signal_stuck(
    "Need lattice_validation for ambiguous vertex",
    topic="validation",
)
time.sleep(0.3)

# Check if anyone offered help
offers = [m for m in encoder.message_log if m.verb == "OFFER"]
for o in offers:
    print(f"  Offer from {o.sender}: {o.body}")

# ── Phase 5: Agent departure ──
print("\n── Phase 5: Thermal agent leaves ──")
thermal.stop()
time.sleep(0.3)

# Check peer status
if "thermal_01" in encoder.peers:
    print(f"  Encoder sees thermal as: {encoder.peers['thermal_01'].status}")
if "thermal_01" in validator.peers:
    print(f"  Validator sees thermal as: {validator.peers['thermal_01'].status}")

# ── Phase 6: Work around missing agent ──
print("\n── Phase 6: Who's still available? ──")
active = encoder.find_peers(status="ACTIVE")
for a in active:
    print(f"  Active: {a.agent_id} ({a.offers})")

offline = [p for p in encoder.peers.values() if p.status == "OFFLINE"]
for a in offline:
    print(f"  Offline: {a.agent_id}")

# Cleanup
encoder.stop()
validator.stop()
print("\n  Done.")
```

if **name** == “**main**”:
main()
