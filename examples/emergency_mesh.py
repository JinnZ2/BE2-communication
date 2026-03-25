"""
examples/emergency_mesh.py — Emergency Phone Mesh Network

Simulates an emergency scenario where cell towers are down.
Phones form a BLE mesh to relay distress signals, share
locations, and coordinate evacuation.

Five phones across a neighborhood:
- Phone A: sends SOS (trapped, needs help)
- Phone B: relays the SOS (out of direct range of C)
- Phone C: receives relayed SOS, shares supply info
- Phone D: WiFi Direct hub for high-bandwidth data exchange
- Phone E: late arrival, discovers the mesh and gets caught up

Demonstrates:
- BLE mesh relay with TTL-based hop limiting
- SOS priority messaging
- Location sharing
- WiFi Direct for higher-bandwidth exchange
- Late device joining the mesh
- Multi-transport bridging (BLE + WiFi Direct)

Usage:
    python -m examples.emergency_mesh

Released CC0.
"""

import sys
import os
import time
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import Agent, Message
from transports.ble import BLETransport, FLAG_SOS, FLAG_LOCATION
from transports.wifi_direct import WiFiDirectTransport


# ── Emergency Agents ──────────────────────────

class EmergencyPhone(Agent):
    """A phone in the emergency mesh network."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sos_received = []
        self.locations = {}
        self.supplies = {}

    def on_message(self, msg: Message):
        if msg.verb == "STUCK":
            # SOS / distress signal
            self.sos_received.append({
                "from": msg.sender,
                "message": msg.body,
                "time": msg.timestamp,
            })
            print(f"  [{self.id}] SOS from {msg.sender}: {msg.body}")

        elif msg.verb == "STATE" and msg.topic == "location":
            # Location update
            self.locations[msg.sender] = msg.body
            print(f"  [{self.id}] Location from {msg.sender}: {msg.body}")

        elif msg.verb == "OFFER" and msg.topic == "supplies":
            # Supply availability
            self.supplies[msg.sender] = msg.body
            print(f"  [{self.id}] Supplies from {msg.sender}: {msg.body}")

        elif msg.verb == "QUERY" and msg.topic == "status":
            # Someone asking for status
            self.reply_to(msg, {
                "status": "ok" if not self.sos_received else "aware_of_emergency",
                "sos_count": len(self.sos_received),
                "known_locations": len(self.locations),
            })

        elif msg.verb == "REPLY":
            print(f"  [{self.id}] Reply from {msg.sender}: {msg.body}")


class BridgePhone(EmergencyPhone):
    """Phone that bridges BLE mesh to WiFi Direct for higher bandwidth."""

    def __init__(self, *args, wifi_transport=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.wifi_transport = wifi_transport

    def on_message(self, msg: Message):
        # Forward emergency messages from BLE to WiFi Direct
        if msg.verb in ("STUCK", "STATE", "OFFER") and self.wifi_transport:
            fwd = Message(
                verb=msg.verb,
                sender=msg.sender,
                body=msg.body,
                topic=msg.topic,
            )
            self.wifi_transport.broadcast(fwd)
            print(f"  [{self.id}] Bridged {msg.verb} from {msg.sender} -> WiFi Direct")


def main():
    # Create shared simulator directories
    ble_dir = tempfile.mkdtemp(prefix="ble_mesh_")
    wifi_dir = tempfile.mkdtemp(prefix="wifi_direct_")

    print("=" * 60)
    print("EMERGENCY MESH — PHONES AS LIFELINES")
    print("=" * 60)
    print(f"  BLE mesh dir:     {ble_dir}")
    print(f"  WiFi Direct dir:  {wifi_dir}")
    print()
    print("Scenario: Cell towers down after severe storm.")
    print("Five phones form an emergency mesh network.")

    # ── Create phone agents ──

    # Phone A: trapped person sending SOS
    phone_a = EmergencyPhone(
        "phone_a", "EmergencyPhone",
        BLETransport("phone_a", channel_dir=ble_dir),
        capabilities=["sos", "location"],
    )

    # Phone B: neighbor in range of A, relays to wider mesh
    phone_b = EmergencyPhone(
        "phone_b", "EmergencyPhone",
        BLETransport("phone_b", channel_dir=ble_dir, relay_enabled=True),
        capabilities=["relay", "location"],
    )

    # Phone C: further away, receives relayed messages
    phone_c = EmergencyPhone(
        "phone_c", "EmergencyPhone",
        BLETransport("phone_c", channel_dir=ble_dir, relay_enabled=True),
        capabilities=["first_aid", "supplies"],
    )

    # Phone D: WiFi Direct hub + BLE bridge
    wifi_transport = WiFiDirectTransport("phone_d_wifi", group_dir=wifi_dir)
    phone_d = BridgePhone(
        "phone_d", "BridgePhone",
        BLETransport("phone_d", channel_dir=ble_dir, relay_enabled=True),
        capabilities=["bridge", "wifi_direct"],
        wifi_transport=wifi_transport,
    )

    # WiFi Direct side of Phone D (separate agent identity on WiFi)
    phone_d_wifi = EmergencyPhone(
        "phone_d_wifi", "WiFiPhone",
        wifi_transport,
        capabilities=["high_bandwidth"],
    )

    all_phones = [phone_a, phone_b, phone_c, phone_d, phone_d_wifi]

    # ── Phase 1: Startup and discovery ──
    print("\n── Phase 1: Mesh formation ──")
    for p in all_phones:
        p.start()
    time.sleep(0.5)

    for p in [phone_a, phone_b, phone_c, phone_d]:
        peer_names = list(p.peers.keys())
        if peer_names:
            print(f"  {p.id} sees: {peer_names}")

    # ── Phase 2: SOS distress signal ──
    print("\n── Phase 2: Phone A sends SOS ──")
    phone_a.signal_stuck(
        "Trapped in basement, 123 Oak St. Need help. Injured leg."
    )
    # Also share location
    location_msg = Message.state(phone_a.id, {
        "lat": 44.8113,
        "lon": -91.4985,
        "accuracy_m": 15,
        "address": "123 Oak St",
        "floor": "basement",
    })
    location_msg.topic = "location"
    phone_a.transport.broadcast(location_msg)
    phone_a._log_message(location_msg)

    # Wait for mesh relay
    time.sleep(1.5)

    print(f"\n  SOS received by:")
    for p in [phone_b, phone_c, phone_d]:
        count = len(p.sos_received)
        if count:
            print(f"    {p.id}: {count} SOS message(s)")

    # ── Phase 3: Supply coordination ──
    print("\n── Phase 3: Supply sharing ──")
    supply_msg = Message.offer(phone_c.id, {
        "water_liters": 10,
        "first_aid_kit": True,
        "flashlights": 3,
        "blankets": 5,
    }, topic="supplies")
    phone_c.transport.broadcast(supply_msg)
    phone_c._log_message(supply_msg)

    time.sleep(1.0)

    # ── Phase 4: Late arrival ──
    print("\n── Phase 4: Phone E joins the mesh ──")
    phone_e = EmergencyPhone(
        "phone_e", "EmergencyPhone",
        BLETransport("phone_e", channel_dir=ble_dir, relay_enabled=True),
        capabilities=["vehicle", "transport"],
    )
    phone_e.start()
    time.sleep(0.5)

    # Phone E asks for current status
    phone_e.ask("What's the emergency status?", topic="status")
    time.sleep(1.0)

    all_phones.append(phone_e)

    # ── Phase 5: Status summary ──
    print("\n── Phase 5: Network status ──")
    print(f"  Mesh nodes: {len(all_phones)}")
    for p in all_phones:
        active_peers = [pid for pid, ps in p.peers.items()
                        if ps.status != "OFFLINE"]
        print(f"  {p.id}: {len(p.message_log)} msgs, "
              f"{len(active_peers)} peers, "
              f"{len(p.sos_received)} SOS alerts")

    # Show mesh relay stats for BLE transports
    print(f"\n── Mesh relay stats ──")
    for p in all_phones:
        if hasattr(p.transport, 'mesh_stats'):
            stats = p.transport.mesh_stats
            print(f"  {p.id}: {stats['messages_seen']} unique msgs seen, "
                  f"relay={'ON' if stats['relay_enabled'] else 'OFF'}")

    # ── Cleanup ──
    print(f"\n── Shutting down ──")
    for p in all_phones:
        p.stop()
    shutil.rmtree(ble_dir, ignore_errors=True)
    shutil.rmtree(wifi_dir, ignore_errors=True)
    print("  Done.")


if __name__ == "__main__":
    main()
