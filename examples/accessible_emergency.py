"""
examples/accessible_emergency.py — Accessible Emergency Alerts for Deaf Users

Demonstrates how Classic Bluetooth profiles push emergency alerts to
devices deaf and hard-of-hearing users already own — without any
app installation on the receiving device.

Scenario: Severe weather knocks out cell towers and power.
  - Maria is deaf and home alone
  - Her phone forms a BLE mesh with neighbors
  - Emergency alerts reach her through:
    * Car dashboard (AVRCP: "⚠ SOS — Tornado warning, seek shelter")
    * LED Bluetooth speaker (A2DP: SOS light pattern)
    * Fitness watch (AVRCP: "Now Playing" notification)
  - She sends her own SOS with location
  - Neighbors coordinate supplies via text alerts on screens

Five devices in play:
  - Phone A (Maria): deaf user, sends/receives via Classic BT
  - Phone B (neighbor): sends tornado warning
  - Phone C (responder): coordinates evacuation
  - Car dashboard: receives AVRCP metadata (passive display)
  - LED speaker: receives A2DP haptic patterns (passive display)

Usage:
    python -m examples.accessible_emergency

Released CC0.
"""

import sys
import os
import time
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import Agent, Message
from transports.ble import BLETransport
from transports.classic_bt import (
    ClassicBTTransport, AVRCPAlert, HFPChannel, HapticEncoder,
    ALERT_SOS, ALERT_URGENT, ALERT_INFO, ALERT_LOCATION,
)


# ── Accessible Phone Agent ───────────────────

class AccessiblePhone(Agent):
    """
    A phone that bridges BLE mesh alerts to Classic Bluetooth
    displays for deaf/HoH users.

    Incoming BLE mesh messages get pushed to all nearby Classic BT
    devices — car screens, speakers, watches — as visual/haptic alerts.
    """

    def __init__(self, *args, classic_bt: ClassicBTTransport = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.classic_bt = classic_bt
        self.alerts_received = []
        self.alerts_pushed = 0

    def on_message(self, msg: Message):
        self.alerts_received.append({
            "from": msg.sender,
            "verb": msg.verb,
            "body": msg.body,
            "time": msg.timestamp,
        })

        # Push every incoming alert to Classic BT displays
        if self.classic_bt:
            if msg.verb == "STUCK":
                # SOS — push with maximum visibility
                text = msg.body if isinstance(msg.body, str) else str(msg.body)
                self.classic_bt.send_sos(msg.sender, text)
                self.alerts_pushed += 1
                print(f"  [{self.id}] \u26a0 SOS pushed to Classic BT displays")

            elif msg.verb == "STATE" and msg.topic == "location":
                loc = msg.body if isinstance(msg.body, dict) else {}
                lat = loc.get("lat", 0.0)
                lon = loc.get("lon", 0.0)
                note = loc.get("note", loc.get("address", ""))
                self.classic_bt.send_location(msg.sender, lat, lon, note)
                self.alerts_pushed += 1
                print(f"  [{self.id}] \u25cb Location pushed to displays")

            elif msg.verb == "OFFER" and msg.topic == "supplies":
                supplies = msg.body if isinstance(msg.body, dict) else {}
                self.classic_bt.send_supply_alert(msg.sender, supplies)
                self.alerts_pushed += 1
                print(f"  [{self.id}] \u2139 Supply info pushed to displays")

            elif msg.verb == "STATE" and msg.topic == "evacuate":
                text = msg.body if isinstance(msg.body, str) else str(msg.body)
                self.classic_bt.broadcast(msg)
                self.alerts_pushed += 1
                print(f"  [{self.id}] \u2757 Evacuation pushed to displays")

        # Log what we see
        if msg.verb == "STUCK":
            print(f"  [{self.id}] Received SOS from {msg.sender}: {msg.body}")
        elif msg.verb == "REPLY":
            print(f"  [{self.id}] Reply from {msg.sender}: {msg.body}")


class ResponderPhone(Agent):
    """A responder/neighbor phone on the BLE mesh."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sos_received = []

    def on_message(self, msg: Message):
        if msg.verb == "STUCK":
            self.sos_received.append(msg)
            print(f"  [{self.id}] Received SOS from {msg.sender}")
            # Auto-reply with acknowledgment
            self.reply_to(msg, {
                "status": "help_coming",
                "eta_minutes": 5,
                "message": "On my way, hang tight!",
            })


def main():
    # Create shared simulator directories
    ble_dir = tempfile.mkdtemp(prefix="ble_accessible_")
    cbt_dir = tempfile.mkdtemp(prefix="classic_bt_")

    print("=" * 65)
    print("ACCESSIBLE EMERGENCY \u2014 EVERY SCREEN IS A LIFELINE")
    print("=" * 65)
    print()
    print("Scenario: Severe weather, cell towers down.")
    print("Maria is deaf and home alone. Her phone connects to")
    print("neighbors via BLE mesh, and pushes alerts to every")
    print("nearby Bluetooth display she can see or feel.")
    print()
    print(f"  BLE mesh dir:      {ble_dir}")
    print(f"  Classic BT dir:    {cbt_dir}")

    # ── Create agents ──

    # Maria's Classic BT transport (talks to her car, speaker, watch)
    maria_cbt = ClassicBTTransport(
        "maria_cbt", channel_dir=cbt_dir,
        enable_avrcp=True, enable_hfp=True, enable_a2dp=True,
    )

    # Maria's phone: BLE mesh + Classic BT bridge
    maria = AccessiblePhone(
        "maria", "AccessiblePhone",
        BLETransport("maria", channel_dir=ble_dir, relay_enabled=True),
        capabilities=["ble", "classic_bt", "accessibility"],
        classic_bt=maria_cbt,
    )

    # Neighbor Bob: sends tornado warning
    bob = ResponderPhone(
        "bob", "ResponderPhone",
        BLETransport("bob", channel_dir=ble_dir, relay_enabled=True),
        capabilities=["ble", "weather_radio"],
    )

    # Responder Carol: coordinates evacuation
    carol = ResponderPhone(
        "carol", "ResponderPhone",
        BLETransport("carol", channel_dir=ble_dir, relay_enabled=True),
        capabilities=["ble", "first_aid", "vehicle"],
    )

    # Simulated "passive" Classic BT devices (car, speaker)
    # These are represented by a listener on the same Classic BT channel
    car_display = ClassicBTTransport(
        "car_dashboard", channel_dir=cbt_dir,
        enable_avrcp=True, enable_hfp=False, enable_a2dp=False,
    )
    led_speaker = ClassicBTTransport(
        "led_speaker", channel_dir=cbt_dir,
        enable_avrcp=False, enable_hfp=False, enable_a2dp=True,
    )

    car_alerts: list[dict] = []
    speaker_alerts: list[dict] = []

    def car_callback(msg: Message):
        car_alerts.append({"from": msg.sender, "body": msg.body})
        print(f"  [\U0001f697 Car] Screen shows: {msg.body}")

    def speaker_callback(msg: Message):
        speaker_alerts.append({"from": msg.sender, "body": msg.body})
        print(f"  [\U0001f50a Speaker] Light pattern activated")

    all_agents = [maria, bob, carol]

    # ── Phase 1: Mesh formation ──
    print("\n\u2500\u2500 Phase 1: Mesh formation \u2500\u2500")
    for a in all_agents:
        a.start()
    car_display.start_listening(car_callback)
    led_speaker.start_listening(speaker_callback)
    time.sleep(0.5)
    print(f"  BLE mesh: {len(all_agents)} phones connected")
    print(f"  Classic BT: car dashboard + LED speaker listening")

    # ── Phase 2: Tornado warning from Bob ──
    print("\n\u2500\u2500 Phase 2: Bob sends tornado warning \u2500\u2500")
    bob.signal_stuck(
        "Tornado warning! Seek shelter immediately. Basement or interior room."
    )
    time.sleep(3.5)  # extra time for BLE relay + SOS repeat (3x with 1s intervals)

    print(f"\n  Maria's Classic BT pushed {maria.alerts_pushed} alert(s) to displays")

    # ── Phase 3: Maria sends her location ──
    print("\n\u2500\u2500 Phase 3: Maria shares her location \u2500\u2500")
    loc_msg = Message.state("maria", {
        "lat": 44.8113,
        "lon": -91.4985,
        "accuracy_m": 10,
        "address": "456 Elm St, Apt 2B",
        "note": "I am in the bathroom, ground floor",
    })
    loc_msg.topic = "location"
    maria.transport.broadcast(loc_msg)
    maria._log_message(loc_msg)
    # Also push to her own Classic BT (so her car shows it)
    maria_cbt.send_location("maria", 44.8113, -91.4985,
                            "456 Elm St, bathroom")
    time.sleep(1.0)

    # ── Phase 4: Carol shares supplies & evacuation ──
    print("\n\u2500\u2500 Phase 4: Carol coordinates supplies \u2500\u2500")
    supply_msg = Message.offer("carol", {
        "water_liters": 15,
        "first_aid_kit": True,
        "flashlights": 4,
        "blankets": 8,
        "vehicle_seats": 3,
    }, topic="supplies")
    carol.transport.broadcast(supply_msg)
    carol._log_message(supply_msg)
    time.sleep(1.0)

    evac_msg = Message.state("carol", {
        "route": "Elm St -> Main St -> High School Gym",
        "shelter": "Lincoln High School Gymnasium",
        "capacity": "200 people",
    })
    evac_msg.topic = "evacuate"
    carol.transport.broadcast(evac_msg)
    carol._log_message(evac_msg)
    time.sleep(1.0)

    # ── Phase 5: Show what each device saw ──
    print("\n\u2500\u2500 Phase 5: Accessibility report \u2500\u2500")

    print(f"\n  Maria's phone:")
    print(f"    Alerts received via BLE mesh: {len(maria.alerts_received)}")
    print(f"    Alerts pushed to Classic BT:  {maria.alerts_pushed}")

    stats = maria_cbt.accessibility_stats
    print(f"\n  Classic BT delivery stats:")
    print(f"    AVRCP (screens):  {stats['avrcp_alerts_sent']} alerts sent")
    print(f"    HFP (text):       {stats['hfp_commands_sent']} commands sent")
    print(f"    A2DP (haptic):    {stats['a2dp_patterns_sent']} patterns sent")
    print(f"    Total:            {stats['total_alerts']} transmissions")

    print(f"\n  Passive devices reached:")
    print(f"    Car dashboard:    {len(car_alerts)} alert(s) displayed")
    print(f"    LED speaker:      {len(speaker_alerts)} pattern(s) played")

    # ── Phase 6: Show AVRCP formatting ──
    print(f"\n\u2500\u2500 Phase 6: What screens actually show \u2500\u2500")
    print(f"\n  Car dashboard / fitness watch / smart speaker:")
    samples = [
        (ALERT_SOS, "bob", "Tornado warning! Seek shelter immediately"),
        (ALERT_LOCATION, "maria", "Location: 44.8113, -91.4985 (456 Elm St)"),
        (ALERT_INFO, "carol", "Supplies available: water, first aid, vehicle"),
    ]
    for priority, sender, text in samples:
        meta = AVRCPAlert.format_metadata(priority, sender, text)
        print(f"\n    Track:  {meta['title']}")
        print(f"    Artist: {meta['artist']}")
        print(f"    Album:  {meta['album']}")

    # ── Phase 7: Haptic pattern demo ──
    print(f"\n\u2500\u2500 Phase 7: Haptic alert patterns \u2500\u2500")
    for name in [ALERT_SOS, ALERT_URGENT, ALERT_INFO, ALERT_LOCATION]:
        dur = HapticEncoder.pattern_duration_ms(name)
        samples = HapticEncoder.encode_pattern(name)
        print(f"  {name:10s}: {dur:4d}ms, {len(samples)} PCM samples")

    # ── Cleanup ──
    print(f"\n\u2500\u2500 Shutting down \u2500\u2500")
    for a in all_agents:
        a.stop()
    car_display.stop_listening()
    led_speaker.stop_listening()
    car_display.close()
    led_speaker.close()
    maria_cbt.close()
    shutil.rmtree(ble_dir, ignore_errors=True)
    shutil.rmtree(cbt_dir, ignore_errors=True)
    print("  Done. Every screen was a lifeline.")


if __name__ == "__main__":
    main()
