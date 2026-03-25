"""
ble.py — Bluetooth Low Energy Mesh Transport

Phone-to-phone communication with no infrastructure required.
Works when cell towers, internet, and power grid are all down.

BLE is available on every modern phone. Range is ~30-100m per hop,
but messages relay through intermediate devices to extend reach
across neighborhoods, highways, and evacuation routes.

How it works:
1. Each device advertises a GATT service with a custom UUID
2. Nearby devices discover each other via BLE scanning
3. Messages are written to a GATT characteristic
4. Mesh relay: each device re-broadcasts messages it hasn't seen
5. TTL and hop tracking prevent infinite loops

Hardware requirements:
- Any phone with Bluetooth 4.0+ (virtually all phones since ~2012)
- No pairing required — uses BLE advertising + GATT

Real implementation uses `bleak` library (cross-platform BLE):
    pip install bleak

For development without hardware/phones, uses file-based simulator
(same pattern as LoRa/HAM/CB transports).

Constraints:
- ~20-244 byte MTU (negotiable, typically 23 bytes on older devices)
- ~1 Mbps theoretical, ~100 kbps practical
- ~30-100m range per hop (open air)
- Messages chunk for large payloads (like LoRa)

Usage (simulator):
    t = BLETransport(device_id="phone_01")

Usage (real BLE — requires bleak):
    t = BLETransport(device_id="phone_01", use_ble=True)

Released CC0.
"""

import os
import time
import struct
import threading
import hashlib
import tempfile
from typing import Optional, Callable
from collections import defaultdict

from core.message import Message
from core.transport import Transport

# ── Constants ──────────────────────────────────

SERVICE_UUID = "be2c0001-dead-beef-cafe-000000000001"
CHAR_MSG_UUID = "be2c0002-dead-beef-cafe-000000000001"

BLE_MTU = 200           # conservative BLE payload per chunk
CHUNK_HEADER_SIZE = 12  # magic(2) + msg_seq(2) + chunk_idx(1) + total(1) + length(2) + ttl(1) + hops(1) + flags(2)
CHUNK_PAYLOAD = BLE_MTU - CHUNK_HEADER_SIZE
CHUNK_MAGIC = b"BM"     # BLE Mesh

DEFAULT_TTL = 7          # max relay hops
DEDUP_WINDOW = 300       # seconds to remember seen message IDs


def _msg_hash(msg: Message) -> str:
    """Short hash for dedup — based on msg_id."""
    return msg.msg_id


# ── Chunking ───────────────────────────────────

def _chunk_message(data: bytes, msg_seq: int, ttl: int = DEFAULT_TTL,
                   hops: int = 0, flags: int = 0) -> list[bytes]:
    """Split a message into BLE-sized chunks with mesh headers."""
    chunks = []
    total = max(1, (len(data) + CHUNK_PAYLOAD - 1) // CHUNK_PAYLOAD)
    for i in range(total):
        start = i * CHUNK_PAYLOAD
        end = min(start + CHUNK_PAYLOAD, len(data))
        payload = data[start:end]
        header = (CHUNK_MAGIC
                  + struct.pack(">HBB", msg_seq, i, total)
                  + struct.pack(">H", len(payload))
                  + struct.pack(">BB", ttl, hops)
                  + struct.pack(">H", flags))
        chunks.append(header + payload)
    return chunks


def _parse_chunk(raw: bytes) -> Optional[tuple[int, int, int, bytes, int, int, int]]:
    """Parse chunk -> (msg_seq, chunk_idx, total, payload, ttl, hops, flags)."""
    if len(raw) < CHUNK_HEADER_SIZE or raw[:2] != CHUNK_MAGIC:
        return None
    msg_seq, chunk_idx, total = struct.unpack(">HBB", raw[2:6])
    length = struct.unpack(">H", raw[6:8])[0]
    ttl, hops = struct.unpack(">BB", raw[8:10])
    flags = struct.unpack(">H", raw[10:12])[0]
    payload = raw[12:12 + length]
    if len(payload) < length:
        return None
    return msg_seq, chunk_idx, total, payload, ttl, hops, flags


# ── Flag constants ─────────────────────────────

FLAG_SOS = 0x0001          # emergency distress signal
FLAG_LOCATION = 0x0002     # contains GPS coordinates
FLAG_RELAY = 0x0004        # this is a relayed message (not original sender)
FLAG_ACK_REQUEST = 0x0008  # sender wants acknowledgment


# ── BLE Backends ───────────────────────────────

class BLEBackend:
    """Abstract BLE interface."""

    def advertise(self, data: bytes) -> bool: ...
    def scan_read(self, timeout: float = 1.0) -> Optional[bytes]: ...
    def close(self): ...
    def is_available(self) -> bool: ...


class RealBLE(BLEBackend):
    """
    Real BLE using bleak library.

    Uses GATT server to advertise and GATT client to scan/read.
    Requires `pip install bleak`.
    """

    def __init__(self, device_id: str):
        self.device_id = device_id
        self._available = False
        try:
            import bleak  # noqa: F401
            self._available = True
        except ImportError:
            pass

    def advertise(self, data: bytes) -> bool:
        if not self._available:
            return False
        # Real BLE GATT write would go here
        # bleak.BleakClient + write_gatt_char
        return False  # placeholder for real implementation

    def scan_read(self, timeout: float = 1.0) -> Optional[bytes]:
        if not self._available:
            return None
        # Real BLE scan + GATT read would go here
        # bleak.BleakScanner + BleakClient.read_gatt_char
        return None  # placeholder for real implementation

    def close(self):
        pass

    def is_available(self) -> bool:
        return self._available


class SimulatedBLE(BLEBackend):
    """
    File-based BLE simulator for development.
    Simulates the broadcast nature of BLE advertising.
    All instances sharing the same channel_dir can see each other.
    """

    def __init__(self, device_id: str, channel_dir: Optional[str] = None):
        self.device_id = device_id
        self.channel_dir = channel_dir or os.path.join(
            tempfile.gettempdir(), "ble_mesh_sim"
        )
        os.makedirs(self.channel_dir, exist_ok=True)
        self._seen: set[str] = set()

    def advertise(self, data: bytes) -> bool:
        try:
            fname = f"{int(time.time() * 10000)}_{self.device_id}.bin"
            fpath = os.path.join(self.channel_dir, fname)
            with open(fpath, "wb") as f:
                f.write(data)
            return True
        except OSError:
            return False

    def scan_read(self, timeout: float = 1.0) -> Optional[bytes]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                files = sorted(os.listdir(self.channel_dir))
                for fname in files:
                    if fname in self._seen:
                        continue
                    if self.device_id in fname:
                        self._seen.add(fname)
                        continue
                    fpath = os.path.join(self.channel_dir, fname)
                    self._seen.add(fname)
                    with open(fpath, "rb") as f:
                        return f.read()
            except OSError:
                pass
            time.sleep(0.05)
        return None

    def close(self):
        pass

    def is_available(self) -> bool:
        return True


# ── BLE Mesh Transport ────────────────────────

class BLETransport(Transport):
    """
    BLE mesh transport for phone-to-phone emergency communication.

    Features:
    - Automatic mesh relay (store-and-forward)
    - Message deduplication (prevents broadcast storms)
    - TTL-based hop limiting
    - SOS flag for emergency priority
    - Chunking for messages larger than BLE MTU
    """

    def __init__(self, device_id: str = "ble_device",
                 use_ble: bool = False,
                 channel_dir: Optional[str] = None,
                 relay_enabled: bool = True,
                 ttl: int = DEFAULT_TTL):
        self.device_id = device_id
        self.relay_enabled = relay_enabled
        self.default_ttl = ttl
        self._msg_seq: int = 0

        # Select backend
        if use_ble:
            self._backend = RealBLE(device_id)
            if not self._backend.is_available():
                self._backend = SimulatedBLE(device_id, channel_dir)
        else:
            self._backend = SimulatedBLE(device_id, channel_dir)

        # Reassembly buffer
        self._reassembly: dict[int, dict[int, bytes]] = defaultdict(dict)
        self._reassembly_meta: dict[int, tuple[int, int, int, int]] = {}  # seq -> (total, ttl, hops, flags)

        # Dedup: track seen message hashes to prevent rebroadcast loops
        self._seen_msgs: dict[str, float] = {}  # msg_hash -> timestamp

        self._callback: Optional[Callable[[Message], None]] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._send_lock = threading.Lock()

    @property
    def transport_name(self) -> str:
        backend = "ble" if isinstance(self._backend, RealBLE) else "sim"
        return f"BLE({backend}:{self.device_id})"

    def send(self, msg: Message, target: str = "") -> bool:
        """Send a message. BLE is inherently broadcast; target is metadata."""
        return self._transmit(msg, flags=0)

    def send_sos(self, msg: Message) -> bool:
        """Send with SOS priority flag."""
        return self._transmit(msg, flags=FLAG_SOS)

    def send_location(self, msg: Message) -> bool:
        """Send with location flag."""
        return self._transmit(msg, flags=FLAG_LOCATION)

    def broadcast(self, msg: Message) -> int:
        """Broadcast to all nearby BLE devices."""
        return 1 if self._transmit(msg) else 0

    def receive(self) -> Optional[Message]:
        """Not used directly — use start_listening."""
        return None

    def start_listening(self, callback: Callable[[Message], None]):
        self._callback = callback
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop_listening(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)

    def close(self):
        self._running = False
        self._backend.close()

    # ── Internal ───────────────────────────────

    def _transmit(self, msg: Message, flags: int = 0) -> bool:
        """Chunk and transmit a message via BLE."""
        data = msg.to_bytes()
        msg_hash = _msg_hash(msg)

        # Mark as seen (don't relay our own messages back)
        self._seen_msgs[msg_hash] = time.time()

        with self._send_lock:
            self._msg_seq = (self._msg_seq + 1) % 65536
            chunks = _chunk_message(data, self._msg_seq,
                                    ttl=self.default_ttl, hops=0, flags=flags)
            for chunk in chunks:
                if not self._backend.advertise(chunk):
                    return False
                if len(chunks) > 1:
                    time.sleep(0.02)  # brief gap between chunks
        return True

    def _relay(self, data: bytes, ttl: int, hops: int, flags: int):
        """Re-broadcast a message with decremented TTL."""
        if not self.relay_enabled or ttl <= 0:
            return

        with self._send_lock:
            self._msg_seq = (self._msg_seq + 1) % 65536
            chunks = _chunk_message(data, self._msg_seq,
                                    ttl=ttl - 1, hops=hops + 1,
                                    flags=flags | FLAG_RELAY)
            for chunk in chunks:
                self._backend.advertise(chunk)
                if len(chunks) > 1:
                    time.sleep(0.02)

    def _listen_loop(self):
        while self._running:
            raw = self._backend.scan_read(timeout=0.5)
            if raw is None:
                continue

            parsed = _parse_chunk(raw)
            if parsed is None:
                continue

            msg_seq, chunk_idx, total, payload, ttl, hops, flags = parsed

            # Store chunk
            self._reassembly[msg_seq][chunk_idx] = payload
            self._reassembly_meta[msg_seq] = (total, ttl, hops, flags)

            # Check if complete
            if len(self._reassembly[msg_seq]) >= total:
                full_data = b""
                for i in range(total):
                    if i not in self._reassembly[msg_seq]:
                        break
                    full_data += self._reassembly[msg_seq][i]
                else:
                    # All chunks present
                    msg = Message.from_bytes(full_data)
                    if msg:
                        msg_hash = _msg_hash(msg)

                        # Dedup check
                        if msg_hash not in self._seen_msgs:
                            self._seen_msgs[msg_hash] = time.time()

                            # Deliver to local callback
                            if self._callback:
                                self._callback(msg)

                            # Mesh relay: re-broadcast if TTL allows
                            if self.relay_enabled and ttl > 1:
                                self._relay(full_data, ttl, hops, flags)

                # Clean up
                del self._reassembly[msg_seq]
                self._reassembly_meta.pop(msg_seq, None)

            # Expire old state
            self._cleanup()

    def _cleanup(self):
        """Remove stale reassembly entries and old dedup records."""
        # Stale reassembly
        current = self._msg_seq
        stale = [s for s in self._reassembly
                 if (current - s) % 65536 > 100]
        for s in stale:
            del self._reassembly[s]
            self._reassembly_meta.pop(s, None)

        # Expired dedup entries
        now = time.time()
        expired = [h for h, t in self._seen_msgs.items()
                   if now - t > DEDUP_WINDOW]
        for h in expired:
            del self._seen_msgs[h]

    @property
    def mesh_stats(self) -> dict:
        """Return mesh statistics for monitoring."""
        return {
            "device_id": self.device_id,
            "messages_seen": len(self._seen_msgs),
            "relay_enabled": self.relay_enabled,
            "default_ttl": self.default_ttl,
            "pending_reassembly": len(self._reassembly),
        }
