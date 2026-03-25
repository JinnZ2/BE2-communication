"""
emergency_mesh_spec.py — Emergency Phone Mesh Protocol Specification

A protocol spec for phone-to-phone emergency communication when
all infrastructure is down. No cell towers, no internet, no power grid.
Just phones talking to each other via BLE and WiFi Direct.

This file defines:
1. Message types for emergency communication
2. Mesh relay protocol with dedup and TTL
3. SOS beacon format
4. Location sharing format
5. Supply/resource coordination
6. Device capability discovery
7. Round-trip tests for all message types

Design principles:
- Works on any phone with Bluetooth 4.0+
- No app store required (could be a PWA or sideloaded APK)
- No accounts, no login, no server
- Battery-efficient (BLE for discovery, WiFi Direct for data)
- Privacy: no tracking, no persistent identity required
- Resilient: mesh self-heals as devices join/leave

Released CC0.
"""

import struct
import json
import time
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional, Any


# ═══════════════════════════════════════════════
# PROTOCOL CONSTANTS
# ═══════════════════════════════════════════════

PROTOCOL_VERSION = 0x01
PROTOCOL_MAGIC = b"EM01"  # Emergency Mesh v1

# Message types
MSG_SOS = 0x01           # Distress signal — highest priority
MSG_LOCATION = 0x02      # GPS/position update
MSG_STATUS = 0x03        # Device status check-in
MSG_SUPPLY = 0x04        # Resource availability
MSG_REQUEST = 0x05       # Request for help/resources
MSG_ACK = 0x06           # Acknowledgment
MSG_RELAY = 0x07         # Relayed message (wraps another message)
MSG_DISCOVER = 0x08      # Device discovery / capability announcement
MSG_TEXT = 0x09           # Free-form text message
MSG_EVACUATE = 0x0A      # Evacuation route / shelter info

# Priority levels
PRIORITY_CRITICAL = 0x01  # SOS, life-threatening
PRIORITY_HIGH = 0x02      # Injury, structural damage
PRIORITY_NORMAL = 0x03    # Status updates, coordination
PRIORITY_LOW = 0x04       # General info

# Max values
MAX_TTL = 15              # Maximum relay hops
MAX_PAYLOAD = 1024        # Max payload bytes (fits in WiFi Direct easily)
MAX_NICKNAME = 32         # Display name length
MAX_TEXT = 512            # Free-form text length


# ═══════════════════════════════════════════════
# PACKET FORMAT
# ═══════════════════════════════════════════════

"""
Emergency Mesh Packet Layout:

Offset  Size  Field
──────  ────  ──────────────────────────
0x00    4B    Magic bytes ("EM01")
0x04    1B    Protocol version (0x01)
0x05    1B    Message type (MSG_*)
0x06    1B    Priority (PRIORITY_*)
0x07    1B    TTL (decremented on each relay hop)
0x08    1B    Hop count (incremented on each relay)
0x09    1B    Flags (bit field)
0x0A    4B    Sender hash (first 4 bytes of SHA-256 of device ID)
0x0E    4B    Timestamp (Unix epoch, 32-bit)
0x12    2B    Sequence number (per-sender, wraps at 65535)
0x14    2B    Payload length
0x16    NB    Payload (JSON)
0x16+N  2B    CRC-16/CCITT-False
──────  ────  ──────────────────────────
Header: 22 bytes
Total:  24 + payload bytes
"""

HEADER_SIZE = 22
HEADER_FMT = ">4sBBBBBB4sIHH"  # pack format for header

# Flag bits
FLAG_NEEDS_ACK = 0x01     # sender wants acknowledgment
FLAG_IS_RELAY = 0x02      # this is a relayed copy
FLAG_ENCRYPTED = 0x04     # payload is encrypted (future)
FLAG_COMPRESSED = 0x08    # payload is compressed (future)
FLAG_HAS_GPS = 0x10       # payload includes GPS coordinates
FLAG_BATTERY_LOW = 0x20   # sender's battery is critically low


def _device_hash(device_id: str) -> bytes:
    """Generate a 4-byte device hash for compact identification."""
    return hashlib.sha256(device_id.encode()).digest()[:4]


def _crc16_ccitt(data: bytes) -> int:
    """CRC-16/CCITT-False — same as UDP mesh spec."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc = crc << 1
            crc &= 0xFFFF
    return crc


# ═══════════════════════════════════════════════
# PACKET CLASS
# ═══════════════════════════════════════════════

@dataclass
class EmergencyPacket:
    """An emergency mesh protocol packet."""

    msg_type: int
    sender_id: str
    payload: dict = field(default_factory=dict)
    priority: int = PRIORITY_NORMAL
    ttl: int = 7
    hops: int = 0
    flags: int = 0
    seq: int = 0
    timestamp: int = 0

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = int(time.time())

    def encode(self) -> bytes:
        """Encode packet to wire format."""
        payload_bytes = json.dumps(self.payload).encode("utf-8")
        sender_hash = _device_hash(self.sender_id)

        header = struct.pack(
            HEADER_FMT,
            PROTOCOL_MAGIC,
            PROTOCOL_VERSION,
            self.msg_type,
            self.priority,
            self.ttl,
            self.hops,
            self.flags,
            sender_hash,
            self.timestamp,
            self.seq,
            len(payload_bytes),
        )

        frame = header + payload_bytes
        crc = _crc16_ccitt(frame)
        return frame + struct.pack(">H", crc)

    @classmethod
    def decode(cls, raw: bytes) -> Optional["EmergencyPacket"]:
        """Decode wire format to packet. Returns None if invalid."""
        if len(raw) < HEADER_SIZE + 2:  # header + CRC
            return None

        # Verify CRC
        frame = raw[:-2]
        expected_crc = struct.unpack(">H", raw[-2:])[0]
        actual_crc = _crc16_ccitt(frame)
        if expected_crc != actual_crc:
            return None

        # Parse header
        try:
            (magic, version, msg_type, priority, ttl, hops, flags,
             sender_hash, timestamp, seq, payload_len) = struct.unpack(
                HEADER_FMT, raw[:HEADER_SIZE]
            )
        except struct.error:
            return None

        if magic != PROTOCOL_MAGIC:
            return None
        if version != PROTOCOL_VERSION:
            return None

        # Parse payload
        payload_data = raw[HEADER_SIZE:HEADER_SIZE + payload_len]
        if len(payload_data) < payload_len:
            return None

        try:
            payload = json.loads(payload_data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

        return cls(
            msg_type=msg_type,
            sender_id=f"hash:{sender_hash.hex()}",
            payload=payload,
            priority=priority,
            ttl=ttl,
            hops=hops,
            flags=flags,
            seq=seq,
            timestamp=timestamp,
        )

    def __repr__(self):
        type_names = {
            MSG_SOS: "SOS", MSG_LOCATION: "LOCATION",
            MSG_STATUS: "STATUS", MSG_SUPPLY: "SUPPLY",
            MSG_REQUEST: "REQUEST", MSG_ACK: "ACK",
            MSG_RELAY: "RELAY", MSG_DISCOVER: "DISCOVER",
            MSG_TEXT: "TEXT", MSG_EVACUATE: "EVACUATE",
        }
        name = type_names.get(self.msg_type, f"0x{self.msg_type:02X}")
        return (f"EmergencyPacket({name}, sender={self.sender_id}, "
                f"ttl={self.ttl}, hops={self.hops}, "
                f"payload={self.payload})")


# ═══════════════════════════════════════════════
# MESSAGE BUILDERS
# ═══════════════════════════════════════════════

def sos_packet(sender_id: str, message: str,
               lat: float = 0.0, lon: float = 0.0,
               needs: str = "") -> EmergencyPacket:
    """Create an SOS distress packet — highest priority."""
    payload = {"message": message[:MAX_TEXT]}
    flags = 0
    if lat != 0.0 or lon != 0.0:
        payload["lat"] = lat
        payload["lon"] = lon
        flags |= FLAG_HAS_GPS
    if needs:
        payload["needs"] = needs
    return EmergencyPacket(
        msg_type=MSG_SOS,
        sender_id=sender_id,
        payload=payload,
        priority=PRIORITY_CRITICAL,
        ttl=MAX_TTL,  # SOS gets maximum relay reach
        flags=flags | FLAG_NEEDS_ACK,
    )


def location_packet(sender_id: str, lat: float, lon: float,
                     accuracy_m: float = 0.0,
                     note: str = "") -> EmergencyPacket:
    """Share GPS location."""
    payload = {"lat": lat, "lon": lon}
    if accuracy_m > 0:
        payload["accuracy_m"] = accuracy_m
    if note:
        payload["note"] = note[:MAX_TEXT]
    return EmergencyPacket(
        msg_type=MSG_LOCATION,
        sender_id=sender_id,
        payload=payload,
        priority=PRIORITY_NORMAL,
        flags=FLAG_HAS_GPS,
    )


def supply_packet(sender_id: str, supplies: dict) -> EmergencyPacket:
    """Announce available supplies/resources."""
    return EmergencyPacket(
        msg_type=MSG_SUPPLY,
        sender_id=sender_id,
        payload=supplies,
        priority=PRIORITY_NORMAL,
    )


def text_packet(sender_id: str, text: str,
                nickname: str = "") -> EmergencyPacket:
    """Free-form text message."""
    payload = {"text": text[:MAX_TEXT]}
    if nickname:
        payload["from"] = nickname[:MAX_NICKNAME]
    return EmergencyPacket(
        msg_type=MSG_TEXT,
        sender_id=sender_id,
        payload=payload,
        priority=PRIORITY_LOW,
    )


def evacuate_packet(sender_id: str, route: str,
                    shelter: str = "",
                    lat: float = 0.0, lon: float = 0.0) -> EmergencyPacket:
    """Share evacuation route or shelter information."""
    payload = {"route": route[:MAX_TEXT]}
    if shelter:
        payload["shelter"] = shelter
    flags = 0
    if lat != 0.0 or lon != 0.0:
        payload["lat"] = lat
        payload["lon"] = lon
        flags |= FLAG_HAS_GPS
    return EmergencyPacket(
        msg_type=MSG_EVACUATE,
        sender_id=sender_id,
        payload=payload,
        priority=PRIORITY_HIGH,
        flags=flags,
    )


def discover_packet(sender_id: str,
                     capabilities: list,
                     battery_pct: int = 100,
                     nickname: str = "") -> EmergencyPacket:
    """Announce device capabilities for mesh coordination."""
    payload = {
        "capabilities": capabilities,
        "battery_pct": battery_pct,
    }
    if nickname:
        payload["nickname"] = nickname[:MAX_NICKNAME]
    flags = FLAG_BATTERY_LOW if battery_pct < 15 else 0
    return EmergencyPacket(
        msg_type=MSG_DISCOVER,
        sender_id=sender_id,
        payload=payload,
        priority=PRIORITY_LOW,
        flags=flags,
    )


# ═══════════════════════════════════════════════
# MESH RELAY PROTOCOL
# ═══════════════════════════════════════════════

class MeshRelay:
    """
    Mesh relay logic for emergency communication.

    Rules:
    1. Every device relays messages it hasn't seen before
    2. TTL decrements on each hop (prevents infinite loops)
    3. SOS messages get maximum TTL (15 hops)
    4. Dedup by (sender_hash, seq) tuple
    5. Higher priority messages relay first
    6. Battery-critical devices reduce relay to SOS-only
    """

    def __init__(self, device_id: str, battery_saver: bool = False):
        self.device_id = device_id
        self.battery_saver = battery_saver
        # Dedup: set of (sender_hash, seq) tuples
        self._seen: set[tuple[bytes, int]] = set()
        self._relay_count = 0

    def should_relay(self, pkt: EmergencyPacket) -> bool:
        """Decide whether to relay this packet."""
        if pkt.ttl <= 0:
            return False

        # Generate dedup key
        sender_hash = _device_hash(pkt.sender_id)
        key = (sender_hash, pkt.seq)
        if key in self._seen:
            return False

        # Battery saver: only relay SOS
        if self.battery_saver and pkt.msg_type != MSG_SOS:
            return False

        return True

    def prepare_relay(self, pkt: EmergencyPacket) -> EmergencyPacket:
        """Prepare a packet for relay (decrement TTL, increment hops)."""
        sender_hash = _device_hash(pkt.sender_id)
        self._seen.add((sender_hash, pkt.seq))
        self._relay_count += 1

        return EmergencyPacket(
            msg_type=pkt.msg_type,
            sender_id=pkt.sender_id,  # keep original sender
            payload=pkt.payload,
            priority=pkt.priority,
            ttl=pkt.ttl - 1,
            hops=pkt.hops + 1,
            flags=pkt.flags | FLAG_IS_RELAY,
            seq=pkt.seq,
            timestamp=pkt.timestamp,
        )

    def mark_seen(self, pkt: EmergencyPacket):
        """Mark a packet as seen without relaying."""
        sender_hash = _device_hash(pkt.sender_id)
        self._seen.add((sender_hash, pkt.seq))

    @property
    def stats(self) -> dict:
        return {
            "device_id": self.device_id,
            "unique_seen": len(self._seen),
            "relayed": self._relay_count,
            "battery_saver": self.battery_saver,
        }


# ═══════════════════════════════════════════════
# APP ARCHITECTURE SPEC
# ═══════════════════════════════════════════════

"""
EMERGENCY MESH APP — ARCHITECTURE

Target Platforms:
- Android (primary) — WiFi Direct + BLE both available
- iOS — Multipeer Connectivity (wraps BLE + WiFi)
- Web (PWA) — Web Bluetooth API (BLE only, limited)

┌─────────────────────────────────────────────┐
│                   UI Layer                   │
│                                             │
│  ┌─────────┐ ┌──────────┐ ┌──────────────┐ │
│  │   SOS   │ │   Map    │ │   Messages   │ │
│  │ Button  │ │ (Nearby) │ │   (Chat)     │ │
│  └────┬────┘ └────┬─────┘ └──────┬───────┘ │
│       │           │              │          │
│  ┌────┴───────────┴──────────────┴───────┐  │
│  │          Agent Protocol Core          │  │
│  │  (Message, Agent, Transport ABC)      │  │
│  └────┬──────────────────────────┬───────┘  │
│       │                          │          │
│  ┌────┴────────┐  ┌─────────────┴────────┐ │
│  │ BLE Transport│  │ WiFi Direct Transport│ │
│  │ (discovery + │  │ (bulk data once      │ │
│  │  mesh relay) │  │  BLE finds peers)    │ │
│  └──────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────┘

Screens:
1. SOS — Big red button. One tap sends distress + GPS.
2. Map — Shows nearby devices as dots. Tap for details.
3. Messages — Simple chat. Text, location, supply offers.
4. Supplies — What you have, what you need. Matchmaking.
5. Mesh — Network status, relay stats, battery info.

Startup Flow:
1. App opens → starts BLE advertising + scanning
2. Discovers nearby devices → shows count on screen
3. User can immediately send SOS or text
4. No login, no account, no internet required
5. Device ID is random, regenerated on each install

Battery Management:
- BLE scanning in low-duty-cycle mode (~10% active)
- WiFi Direct only activated when large data transfer needed
- Battery saver mode: SOS relay only, no WiFi Direct
- Below 10%: stop all relay, display-only mode

Privacy:
- No persistent device ID across sessions (opt-in)
- No location sharing unless user explicitly sends it
- Messages are not stored after app close (opt-in history)
- No analytics, no tracking, no cloud
"""


# ═══════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("=== Emergency Mesh Protocol — Tests ===\n")

    # Test 1: SOS packet round-trip
    print("── Test 1: SOS packet ──")
    sos = sos_packet(
        "phone_alice",
        "Trapped in basement, need rescue",
        lat=44.8113, lon=-91.4985,
        needs="medical",
    )
    encoded = sos.encode()
    decoded = EmergencyPacket.decode(encoded)
    assert decoded is not None
    assert decoded.msg_type == MSG_SOS
    assert decoded.priority == PRIORITY_CRITICAL
    assert decoded.payload["message"] == "Trapped in basement, need rescue"
    assert decoded.payload["lat"] == 44.8113
    assert decoded.flags & FLAG_HAS_GPS
    assert decoded.flags & FLAG_NEEDS_ACK
    print(f"  Original:  {sos}")
    print(f"  Encoded:   {len(encoded)} bytes")
    print(f"  Decoded:   {decoded}")
    print(f"  PASS: SOS round-trip")

    # Test 2: Location packet
    print("\n── Test 2: Location packet ──")
    loc = location_packet("phone_bob", 44.8200, -91.5000,
                          accuracy_m=10, note="On the roof")
    encoded = loc.encode()
    decoded = EmergencyPacket.decode(encoded)
    assert decoded is not None
    assert decoded.msg_type == MSG_LOCATION
    assert decoded.payload["lat"] == 44.8200
    print(f"  {decoded}")
    print(f"  PASS: Location round-trip")

    # Test 3: Supply packet
    print("\n── Test 3: Supply packet ──")
    sup = supply_packet("phone_carol", {
        "water_liters": 20,
        "first_aid": True,
        "flashlights": 5,
        "blankets": 10,
        "radio": "battery_powered",
    })
    encoded = sup.encode()
    decoded = EmergencyPacket.decode(encoded)
    assert decoded is not None
    assert decoded.payload["water_liters"] == 20
    print(f"  {decoded}")
    print(f"  PASS: Supply round-trip")

    # Test 4: Text message
    print("\n── Test 4: Text message ──")
    txt = text_packet("phone_dave", "Is anyone at the community center?",
                      nickname="Dave")
    encoded = txt.encode()
    decoded = EmergencyPacket.decode(encoded)
    assert decoded is not None
    assert decoded.payload["text"] == "Is anyone at the community center?"
    assert decoded.payload["from"] == "Dave"
    print(f"  {decoded}")
    print(f"  PASS: Text round-trip")

    # Test 5: Evacuation route
    print("\n── Test 5: Evacuation packet ──")
    evac = evacuate_packet(
        "phone_eve",
        route="Take Hwy 53 North to Shelter at High School",
        shelter="Superior High School Gym",
        lat=46.7208, lon=-92.1041,
    )
    encoded = evac.encode()
    decoded = EmergencyPacket.decode(encoded)
    assert decoded is not None
    assert decoded.msg_type == MSG_EVACUATE
    assert decoded.priority == PRIORITY_HIGH
    print(f"  {decoded}")
    print(f"  PASS: Evacuation round-trip")

    # Test 6: Discovery packet
    print("\n── Test 6: Discovery packet ──")
    disc = discover_packet(
        "phone_frank",
        capabilities=["ble", "wifi_direct", "gps"],
        battery_pct=72,
        nickname="Frank",
    )
    encoded = disc.encode()
    decoded = EmergencyPacket.decode(encoded)
    assert decoded is not None
    assert "wifi_direct" in decoded.payload["capabilities"]
    assert decoded.payload["battery_pct"] == 72
    print(f"  {decoded}")
    print(f"  PASS: Discovery round-trip")

    # Test 7: CRC integrity check
    print("\n── Test 7: Integrity check ──")
    pkt = sos_packet("test", "help")
    good_bytes = pkt.encode()
    # Corrupt one byte
    bad_bytes = bytearray(good_bytes)
    bad_bytes[15] ^= 0xFF
    bad_bytes = bytes(bad_bytes)
    assert EmergencyPacket.decode(bad_bytes) is None
    print(f"  PASS: Corrupted packet rejected")

    # Test 8: Truncated packet
    truncated = good_bytes[:10]
    assert EmergencyPacket.decode(truncated) is None
    print(f"  PASS: Truncated packet rejected")

    # Test 9: Mesh relay logic
    print("\n── Test 9: Mesh relay ──")
    relay = MeshRelay("relay_device")
    original = sos_packet("sender_01", "help!", lat=44.0, lon=-91.0)
    original.seq = 42

    assert relay.should_relay(original) is True
    relayed = relay.prepare_relay(original)
    assert relayed.ttl == original.ttl - 1
    assert relayed.hops == original.hops + 1
    assert relayed.flags & FLAG_IS_RELAY

    # Should NOT relay same packet again (dedup)
    assert relay.should_relay(original) is False
    print(f"  Original: TTL={original.ttl}, hops={original.hops}")
    print(f"  Relayed:  TTL={relayed.ttl}, hops={relayed.hops}")
    print(f"  Dedup:    second relay blocked (correct)")
    print(f"  PASS: Mesh relay logic")

    # Test 10: Battery saver mode
    print("\n── Test 10: Battery saver ──")
    saver = MeshRelay("low_battery", battery_saver=True)
    sos_msg = sos_packet("someone", "emergency!")
    sos_msg.seq = 1
    text_msg = text_packet("someone", "hello")
    text_msg.seq = 2

    assert saver.should_relay(sos_msg) is True
    assert saver.should_relay(text_msg) is False
    print(f"  SOS relay in battery saver: YES")
    print(f"  Text relay in battery saver: NO")
    print(f"  PASS: Battery saver mode")

    # Test 11: TTL exhaustion
    print("\n── Test 11: TTL exhaustion ──")
    expired = sos_packet("far_away", "help")
    expired.ttl = 0
    expired.seq = 99
    relay2 = MeshRelay("edge_device")
    assert relay2.should_relay(expired) is False
    print(f"  TTL=0 packet relay: blocked (correct)")
    print(f"  PASS: TTL exhaustion")

    # Summary
    print("\n=== All tests passed ===")

    print(f"\nPacket sizes:")
    for name, pkt in [("SOS", sos), ("Location", loc), ("Supply", sup),
                       ("Text", txt), ("Evacuate", evac), ("Discover", disc)]:
        size = len(pkt.encode())
        print(f"  {name:12s}: {size} bytes")
