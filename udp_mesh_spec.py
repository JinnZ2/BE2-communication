"""
udp_mesh_spec.py — LAN UDP Mesh Byte-Level Protocol Specification & Implementation

LAN UDP Mesh — Byte-Level Protocol Specification
================================================

1. PACKET STRUCTURE (all numeric fields are big-endian)

Header (8 bytes total):
----------------------
- 0x00: Version (1 byte)           -> Protocol version (e.g., 0x01)
- 0x01: Packet Type (1 byte)       -> 0x01=QUERY, 0x02=REPLY, 0x03=DISCOVER
- 0x02-0x03: Sender ID (2 bytes)   -> Unique 16-bit agent ID
- 0x04-0x05: Recipient ID (2 bytes)-> 0xFFFF = broadcast
- 0x06-0x07: Payload Length (2 b)  -> Length of payload in bytes

Payload (variable):
------------------
- Query/Reply: JSON-encoded UTF-8 dictionary
    {
      "topic": "<string>",
      "body": "<arbitrary data>"
    }

- Discover: empty or optional metadata

2. PEER DISCOVERY
-----------------
- Agents broadcast DISCOVER packets to 255.255.255.255:<port>
- Responding agents return REPLY with their ID and capabilities

3. COMMUNICATION RULES
---------------------
- UDP port fixed per agent or configurable via config
- Each message is self-contained; no fragmentation
- Retries optional; sequence number may be added if order matters
- Causality:
    - Queries -> Replies only
    - No back-propagation beyond immediate sender

4. ENCODING/DECODING
-------------------
- Header fields: struct.pack(">BBHHH")
- Payload: UTF-8 JSON
- Total packet size = 8 + payload length + 2 (CRC)
- Maximum recommended payload ~ 512 bytes

5. ENERGY / GROWTH MESSAGES (optional extensions)
-------------------------------------------------
- Shell expansion or adaptive exploration can be encoded in payload
- Example JSON:
    {
      "type": "SHELL",
      "id": 3,
      "r": 2.25,
      "E": 0.216,
      "S": [0.45, 0.12, 0.18, 0.15, 0.05, 0.05],
      "mode": "EXPLORE"
    }

6. SECURITY / INTEGRITY
---------------------------------
- CRC16-CCITT appended to every packet for verification
- Optional AES encryption for sensitive channels


LAN UDP Mesh — Byte-Level Layout
===============================

HEADER (8 bytes)
----------------
 Byte  | Field           | Size | Description
-------|-----------------|------|------------------------------------------------
 0     | Version         | 1B   | Protocol version (e.g., 0x01)
 1     | Packet Type     | 1B   | 0x01=QUERY, 0x02=REPLY, 0x03=DISCOVER
 2-3   | Sender ID       | 2B   | Unique 16-bit agent ID
 4-5   | Recipient ID    | 2B   | 0xFFFF = broadcast
 6-7   | Payload Length  | 2B   | Length of payload in bytes (max ~512)

PAYLOAD (variable, Payload Length bytes)
----------------------------------------
- QUERY / REPLY: JSON UTF-8 encoded
    {
      "topic": "<string>",
      "body": "<arbitrary data>"
    }
- DISCOVER: optional JSON metadata or empty
- SHELL / ENERGY extension:
    {
      "type": "SHELL",
      "id": <int>,
      "r": <float>,
      "E": <float>,
      "S": [a,b,c,d,e,f],
      "mode": "EXPLORE"|"EXPAND"
    }

TRAILER (2 bytes)
-----------------
 Byte          | Field | Size | Description
---------------|-------|------|--------------------------------
 8+PayloadLen  | CRC16 | 2B  | CRC-16/CCITT-False over header+payload

TOTAL PACKET SIZE
-----------------
= HEADER (8B) + Payload Length (0-512B recommended) + CRC (2B)

SERIALIZATION
-------------
- Header: struct.pack(">BBHHH")
- Payload: UTF-8 JSON bytes
- Trailer: CRC16-CCITT over header+payload, struct.pack(">H")
- Optional: AES-128/256 for encrypted channels

NOTES
-----
- Causality: Queries -> Replies only; no back-propagation
- Discovery: Broadcast DISCOVER, receive REPLY with ID/capabilities
- Deterministic: Same payload produces same structure on all compliant agents

Released CC0.
"""

import struct
import json


class UDPMeshPacket:
    """
    LAN UDP Mesh — Byte-Level Protocol with CRC16 Integrity
    Layout: [Header 8B] + [Payload NB] + [CRC 2B]
    """
    HEADER_FORMAT = ">BBHHH"
    CRC_FORMAT = ">H"
    VERSION = 0x01

    TYPE_QUERY = 0x01
    TYPE_REPLY = 0x02
    TYPE_DISCOVER = 0x03
    BROADCAST_ID = 0xFFFF

    MAX_RECOMMENDED_PAYLOAD = 512

    def __init__(self, packet_type, sender_id, recipient_id=BROADCAST_ID, payload=None):
        self.packet_type = packet_type
        self.sender_id = sender_id
        self.recipient_id = recipient_id
        self.payload = payload or {}

    @staticmethod
    def crc16_ccitt(data: bytes) -> int:
        """Standard CRC-16/CCITT-False (poly 0x1021, init 0xFFFF)."""
        crc = 0xFFFF
        for byte in data:
            crc ^= (byte << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
                crc &= 0xFFFF
        return crc

    def encode(self) -> bytes:
        """Serialize packet to bytes: header + JSON payload + CRC16."""
        payload_bytes = json.dumps(self.payload).encode('utf-8')

        if len(payload_bytes) > self.MAX_RECOMMENDED_PAYLOAD:
            print(f"Warning: Payload size {len(payload_bytes)} exceeds "
                  f"{self.MAX_RECOMMENDED_PAYLOAD}B recommendation.")

        header = struct.pack(
            self.HEADER_FORMAT,
            self.VERSION,
            self.packet_type,
            self.sender_id,
            self.recipient_id,
            len(payload_bytes)
        )

        body = header + payload_bytes
        crc_val = self.crc16_ccitt(body)
        return body + struct.pack(self.CRC_FORMAT, crc_val)

    @classmethod
    def decode(cls, raw_bytes: bytes):
        """Deserialize raw bytes into a UDPMeshPacket, verifying CRC."""
        if len(raw_bytes) < 10:  # 8B header + 2B CRC minimum
            return None

        header_bytes = raw_bytes[:8]
        _, _, _, _, p_len = struct.unpack(cls.HEADER_FORMAT, header_bytes)

        expected_total = 8 + p_len + 2
        if len(raw_bytes) < expected_total:
            return None

        payload_bytes = raw_bytes[8:8 + p_len]
        received_crc = struct.unpack(cls.CRC_FORMAT, raw_bytes[8 + p_len:8 + p_len + 2])[0]

        calculated_crc = cls.crc16_ccitt(header_bytes + payload_bytes)
        if received_crc != calculated_crc:
            return None  # CRC mismatch

        version, p_type, s_id, r_id, _ = struct.unpack(cls.HEADER_FORMAT, header_bytes)

        if version != cls.VERSION:
            return None

        try:
            payload = json.loads(payload_bytes.decode('utf-8')) if p_len > 0 else {}
        except json.JSONDecodeError:
            payload = {"error": "decode_fail"}

        return cls(p_type, s_id, r_id, payload)

    def __repr__(self):
        type_names = {0x01: "QUERY", 0x02: "REPLY", 0x03: "DISCOVER"}
        t = type_names.get(self.packet_type, f"0x{self.packet_type:02X}")
        r = "BROADCAST" if self.recipient_id == self.BROADCAST_ID else f"0x{self.recipient_id:04X}"
        return f"UDPMeshPacket({t}, sender=0x{self.sender_id:04X}, to={r}, payload={self.payload})"


# ─────────────────────────────────────────────
# Inline tests
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== UDP Mesh Packet — Round-trip Tests ===\n")

    # Test 1: Basic QUERY encode/decode
    pkt = UDPMeshPacket(
        UDPMeshPacket.TYPE_QUERY,
        sender_id=0x00A1,
        payload={"topic": "TEMP", "body": "READ"}
    )
    raw = pkt.encode()
    print(f"Original:  {pkt}")
    print(f"Encoded:   {len(raw)} bytes -> {raw.hex()}")

    decoded = UDPMeshPacket.decode(raw)
    print(f"Decoded:   {decoded}")
    assert decoded is not None
    assert decoded.packet_type == UDPMeshPacket.TYPE_QUERY
    assert decoded.sender_id == 0x00A1
    assert decoded.recipient_id == UDPMeshPacket.BROADCAST_ID
    assert decoded.payload == {"topic": "TEMP", "body": "READ"}
    print("PASS: round-trip QUERY\n")

    # Test 2: DISCOVER broadcast
    disc = UDPMeshPacket(UDPMeshPacket.TYPE_DISCOVER, sender_id=0x0042)
    raw_disc = disc.encode()
    decoded_disc = UDPMeshPacket.decode(raw_disc)
    print(f"Discover:  {decoded_disc}")
    assert decoded_disc is not None
    assert decoded_disc.packet_type == UDPMeshPacket.TYPE_DISCOVER
    assert decoded_disc.payload == {}
    print("PASS: round-trip DISCOVER\n")

    # Test 3: REPLY with directed recipient
    reply = UDPMeshPacket(
        UDPMeshPacket.TYPE_REPLY,
        sender_id=0x0042,
        recipient_id=0x00A1,
        payload={"topic": "TEMP", "body": "22.5C"}
    )
    raw_reply = reply.encode()
    decoded_reply = UDPMeshPacket.decode(raw_reply)
    print(f"Reply:     {decoded_reply}")
    assert decoded_reply is not None
    assert decoded_reply.recipient_id == 0x00A1
    print("PASS: round-trip directed REPLY\n")

    # Test 4: CRC corruption detection
    corrupted = bytearray(raw)
    corrupted[10] ^= 0xFF  # flip a payload byte
    bad = UDPMeshPacket.decode(bytes(corrupted))
    assert bad is None
    print("PASS: corrupted packet rejected\n")

    # Test 5: Truncated packet
    assert UDPMeshPacket.decode(raw[:5]) is None
    print("PASS: truncated packet rejected\n")

    # Test 6: SHELL/ENERGY extension payload
    shell_pkt = UDPMeshPacket(
        UDPMeshPacket.TYPE_QUERY,
        sender_id=0x0003,
        payload={
            "type": "SHELL",
            "id": 3,
            "r": 2.25,
            "E": 0.216,
            "S": [0.45, 0.12, 0.18, 0.15, 0.05, 0.05],
            "mode": "EXPLORE"
        }
    )
    raw_shell = shell_pkt.encode()
    decoded_shell = UDPMeshPacket.decode(raw_shell)
    print(f"Shell:     {decoded_shell}")
    assert decoded_shell is not None
    assert decoded_shell.payload["type"] == "SHELL"
    assert decoded_shell.payload["mode"] == "EXPLORE"
    print("PASS: round-trip SHELL extension\n")

    print("=== All tests passed ===")
