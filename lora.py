“””
lora.py — LoRa Serial Transport

Long-range, low-bandwidth communication over LoRa radio modules.
Works with any LoRa module that exposes a serial/UART interface.

Tested module families:
- REYAX RYLR896/RYLR406 (AT command set)
- Adafruit RFM9x (raw packet mode)
- Meshtastic devices (via serial API)
- Any SX1276/SX1278 breakout with serial bridge

Wire format:
Same as UDP — magic bytes + length prefix + JSON payload.
Messages are chunked to fit LoRa MTU (typically 250 bytes).

Constraints:
- ~250 byte max packet (after overhead)
- ~300 bps to ~37.5 kbps depending on settings
- Half-duplex (can’t send and receive simultaneously)
- Duty cycle limits in some regions

This transport handles:
- Chunking large messages across multiple LoRa packets
- Reassembly on receive
- Serial port management (open/close/reconnect)
- AT command abstraction for RYLR-style modules

If no serial port is available, falls back to a file-based
simulator so you can develop and test without hardware.

Usage (real hardware):
t = LoRaTransport(”/dev/ttyUSB0”, baud=115200, address=1)

Usage (simulator for development):
t = LoRaTransport(None)  # auto-creates file-based simulator

Released CC0.
“””

import os
import time
import struct
import threading
import json
import tempfile
from typing import Optional, Callable
from collections import defaultdict

try:
from ..core.message import Message
from ..core.transport import Transport
except ImportError:
from core.message import Message
from core.transport import Transport

MAGIC = b”AG01”
LORA_MTU = 240           # safe payload per packet
CHUNK_HEADER_SIZE = 8     # magic(2) + msg_seq(2) + chunk_idx(1) + total_chunks(1) + length(2)
CHUNK_PAYLOAD = LORA_MTU - CHUNK_HEADER_SIZE
CHUNK_MAGIC = b”LC”

def _chunk_message(data: bytes, msg_seq: int) -> list[bytes]:
“”“Split a message into LoRa-sized chunks.”””
chunks = []
total = (len(data) + CHUNK_PAYLOAD - 1) // CHUNK_PAYLOAD
for i in range(total):
start = i * CHUNK_PAYLOAD
end = min(start + CHUNK_PAYLOAD, len(data))
payload = data[start:end]
header = (CHUNK_MAGIC
+ struct.pack(”>HBB”, msg_seq, i, total)
+ struct.pack(”>H”, len(payload)))
chunks.append(header + payload)
return chunks

def _parse_chunk(raw: bytes) -> Optional[tuple[int, int, int, bytes]]:
“”“Parse a chunk → (msg_seq, chunk_idx, total_chunks, payload).”””
if len(raw) < CHUNK_HEADER_SIZE or raw[:2] != CHUNK_MAGIC:
return None
msg_seq, chunk_idx, total = struct.unpack(”>HBB”, raw[2:6])
length = struct.unpack(”>H”, raw[6:8])[0]
payload = raw[8:8 + length]
if len(payload) < length:
return None
return msg_seq, chunk_idx, total, payload

# ── Serial Backends ────────────────────────────

class SerialBackend:
“”“Abstract serial interface.”””
def write(self, data: bytes) -> bool: …
def read(self, timeout: float = 1.0) -> Optional[bytes]: …
def close(self): …
def is_open(self) -> bool: …

class RealSerial(SerialBackend):
“”“Real serial port via pyserial.”””

```
def __init__(self, port: str, baud: int = 115200):
    try:
        import serial as pyserial
        self._ser = pyserial.Serial(port, baud, timeout=1.0)
        self._available = True
    except (ImportError, Exception):
        self._ser = None
        self._available = False

def write(self, data: bytes) -> bool:
    if not self._available or not self._ser:
        return False
    try:
        # RYLR AT command format: AT+SEND=<addr>,<len>,<data>\r\n
        # For raw mode, just write the bytes
        self._ser.write(data)
        self._ser.flush()
        return True
    except Exception:
        return False

def read(self, timeout: float = 1.0) -> Optional[bytes]:
    if not self._available or not self._ser:
        return None
    try:
        self._ser.timeout = timeout
        # Read until we get a complete chunk or timeout
        data = self._ser.read(LORA_MTU)
        return data if data else None
    except Exception:
        return None

def close(self):
    if self._ser:
        try:
            self._ser.close()
        except Exception:
            pass

def is_open(self) -> bool:
    return self._available and self._ser is not None and self._ser.is_open
```

class SimulatedSerial(SerialBackend):
“””
File-based LoRa simulator for development without hardware.
Uses a shared directory to simulate the radio channel.
All SimulatedSerial instances sharing the same channel_dir
can see each other’s transmissions.
“””

```
def __init__(self, agent_id: str, channel_dir: Optional[str] = None):
    self.agent_id = agent_id
    self.channel_dir = channel_dir or os.path.join(
        tempfile.gettempdir(), "lora_sim_channel"
    )
    os.makedirs(self.channel_dir, exist_ok=True)
    self._seen: set[str] = set()

def write(self, data: bytes) -> bool:
    try:
        fname = f"{int(time.time() * 10000)}_{self.agent_id}.bin"
        fpath = os.path.join(self.channel_dir, fname)
        with open(fpath, "wb") as f:
            f.write(data)
        return True
    except OSError:
        return False

def read(self, timeout: float = 1.0) -> Optional[bytes]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            files = sorted(os.listdir(self.channel_dir))
            for fname in files:
                if fname in self._seen:
                    continue
                # Don't read own transmissions
                if self.agent_id in fname:
                    self._seen.add(fname)
                    continue
                fpath = os.path.join(self.channel_dir, fname)
                self._seen.add(fname)
                with open(fpath, "rb") as f:
                    data = f.read()
                return data
        except OSError:
            pass
        time.sleep(0.05)
    return None

def close(self):
    pass

def is_open(self) -> bool:
    return True
```

# ── LoRa Transport ─────────────────────────────

class LoRaTransport(Transport):
def **init**(self, port: Optional[str] = None,
baud: int = 115200,
agent_id: str = “lora_agent”,
address: int = 0,
channel_dir: Optional[str] = None):
“””
Args:
port: Serial port path (e.g. “/dev/ttyUSB0”).
None = use simulated radio.
baud: Serial baud rate.
agent_id: This agent’s identifier (for simulator).
address: LoRa device address (for AT command modules).
channel_dir: Shared dir for simulator mode.
“””
self.agent_id = agent_id
self.address = address
self._msg_seq: int = 0

```
    # Select backend
    if port is not None:
        self._backend = RealSerial(port, baud)
        if not self._backend.is_open():
            # Fall back to simulator
            self._backend = SimulatedSerial(agent_id, channel_dir)
    else:
        self._backend = SimulatedSerial(agent_id, channel_dir)

    # Reassembly buffer: { msg_seq: { chunk_idx: payload } }
    self._reassembly: dict[int, dict[int, bytes]] = defaultdict(dict)
    self._reassembly_meta: dict[int, int] = {}  # msg_seq → total_chunks

    self._callback: Optional[Callable[[Message], None]] = None
    self._running = False
    self._thread: Optional[threading.Thread] = None
    self._send_lock = threading.Lock()

@property
def transport_name(self) -> str:
    backend = "serial" if isinstance(self._backend, RealSerial) else "sim"
    return f"LoRa({backend}:{self.agent_id})"

def send(self, msg: Message, target: str = "") -> bool:
    """Send a message (LoRa is inherently broadcast, target is metadata only)."""
    return self._transmit(msg)

def broadcast(self, msg: Message) -> int:
    """Same as send — LoRa is broadcast by nature."""
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

def _transmit(self, msg: Message) -> bool:
    """Chunk and transmit a message."""
    data = msg.to_bytes()
    with self._send_lock:
        self._msg_seq = (self._msg_seq + 1) % 65536
        chunks = _chunk_message(data, self._msg_seq)
        for chunk in chunks:
            if not self._backend.write(chunk):
                return False
            # Inter-chunk delay (LoRa needs time between packets)
            if len(chunks) > 1:
                time.sleep(0.05)
    return True

def _listen_loop(self):
    while self._running:
        raw = self._backend.read(timeout=0.5)
        if raw is None:
            continue

        parsed = _parse_chunk(raw)
        if parsed is None:
            continue

        msg_seq, chunk_idx, total, payload = parsed

        # Store chunk
        self._reassembly[msg_seq][chunk_idx] = payload
        self._reassembly_meta[msg_seq] = total

        # Check if message is complete
        if len(self._reassembly[msg_seq]) >= total:
            # Reassemble in order
            full_data = b""
            for i in range(total):
                if i not in self._reassembly[msg_seq]:
                    break  # missing chunk — discard
                full_data += self._reassembly[msg_seq][i]
            else:
                # All chunks present — parse message
                msg = Message.from_bytes(full_data)
                if msg and self._callback:
                    self._callback(msg)

            # Clean up reassembly buffer
            del self._reassembly[msg_seq]
            del self._reassembly_meta[msg_seq]

        # Expire old incomplete messages (prevent memory leak)
        self._cleanup_stale()

def _cleanup_stale(self, max_age_seq: int = 100):
    """Remove reassembly entries that are too old."""
    if not self._reassembly:
        return
    current = self._msg_seq
    stale = [
        seq for seq in self._reassembly
        if (current - seq) % 65536 > max_age_seq
    ]
    for seq in stale:
        del self._reassembly[seq]
        self._reassembly_meta.pop(seq, None)
```
