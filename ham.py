“””
ham.py — HAM Radio Transport

Packet radio communication over amateur radio frequencies.
Works with any Terminal Node Controller (TNC) that provides
a KISS interface — hardware TNCs, Direwolf, Mobilinkd, etc.

Two modes:
1. KISS TNC (default) — connects to a TNC via TCP or serial
that handles the AX.25 framing and radio keying.
2. Simulated — file-based for development without hardware.

AX.25 packet format (simplified):
[dest_call] [src_call] [control] [pid] [payload]
Max payload: ~256 bytes (standard) or ~1024 (extended)

Legal requirements:
- Valid amateur radio license required for transmission
- Callsign must be included in every transmission
- No encryption allowed (messages are plaintext by design)
- This protocol is already plaintext/JSON — compliant by nature

Usage (with Direwolf TNC on localhost):
t = HAMTransport(
callsign=“KD0ABC”,
tnc_host=“127.0.0.1”,
tnc_port=8001,
)

Usage (simulator):
t = HAMTransport(callsign=“SIM01”)

Released CC0.
“””

import socket
import struct
import threading
import time
import os
import tempfile
from typing import Optional, Callable
from collections import defaultdict

try:
from ..core.message import Message
from ..core.transport import Transport
except ImportError:
from core.message import Message
from core.transport import Transport

# KISS protocol constants

KISS_FEND = 0xC0
KISS_FESC = 0xDB
KISS_TFEND = 0xDC
KISS_TFESC = 0xDD
KISS_DATA_FRAME = 0x00

# Agent protocol chunk format (same as LoRa)

CHUNK_MAGIC = b”LC”
CHUNK_HEADER_SIZE = 8
HAM_MTU = 240  # conservative for AX.25

def _kiss_escape(data: bytes) -> bytes:
“”“KISS byte-stuffing.”””
out = bytearray()
for b in data:
if b == KISS_FEND:
out.extend([KISS_FESC, KISS_TFEND])
elif b == KISS_FESC:
out.extend([KISS_FESC, KISS_TFESC])
else:
out.append(b)
return bytes(out)

def _kiss_unescape(data: bytes) -> bytes:
“”“Reverse KISS byte-stuffing.”””
out = bytearray()
i = 0
while i < len(data):
if data[i] == KISS_FESC and i + 1 < len(data):
if data[i + 1] == KISS_TFEND:
out.append(KISS_FEND)
elif data[i + 1] == KISS_TFESC:
out.append(KISS_FESC)
i += 2
else:
out.append(data[i])
i += 1
return bytes(out)

def _kiss_frame(data: bytes) -> bytes:
“”“Wrap data in a KISS frame.”””
return bytes([KISS_FEND, KISS_DATA_FRAME]) + _kiss_escape(data) + bytes([KISS_FEND])

def _extract_kiss_frames(buf: bytes) -> tuple[list[bytes], bytes]:
“”“Extract complete KISS frames from a buffer, return (frames, remainder).”””
frames = []
while True:
start = buf.find(bytes([KISS_FEND]))
if start == -1:
break
end = buf.find(bytes([KISS_FEND]), start + 1)
if end == -1:
break
frame_data = buf[start + 1:end]
if len(frame_data) > 1 and frame_data[0] == KISS_DATA_FRAME:
payload = _kiss_unescape(frame_data[1:])
frames.append(payload)
buf = buf[end + 1:]
return frames, buf

def _chunk_message(data: bytes, msg_seq: int) -> list[bytes]:
“”“Split message into HAM-sized chunks.”””
chunk_payload = HAM_MTU - CHUNK_HEADER_SIZE
chunks = []
total = (len(data) + chunk_payload - 1) // chunk_payload
for i in range(total):
start = i * chunk_payload
end = min(start + chunk_payload, len(data))
payload = data[start:end]
header = (CHUNK_MAGIC
+ struct.pack(”>HBB”, msg_seq, i, total)
+ struct.pack(”>H”, len(payload)))
chunks.append(header + payload)
return chunks

def _parse_chunk(raw: bytes) -> Optional[tuple[int, int, int, bytes]]:
if len(raw) < CHUNK_HEADER_SIZE or raw[:2] != CHUNK_MAGIC:
return None
msg_seq, chunk_idx, total = struct.unpack(”>HBB”, raw[2:6])
length = struct.unpack(”>H”, raw[6:8])[0]
payload = raw[8:8 + length]
if len(payload) < length:
return None
return msg_seq, chunk_idx, total, payload

# ── TNC Backends ───────────────────────────────

class TNCBackend:
“”“Abstract TNC interface.”””
def write(self, data: bytes) -> bool: …
def read(self, timeout: float = 1.0) -> Optional[bytes]: …
def close(self): …
def is_open(self) -> bool: …

class KissTNC(TNCBackend):
“”“TCP connection to a KISS TNC (Direwolf, Mobilinkd, etc).”””

```
def __init__(self, host: str = "127.0.0.1", port: int = 8001):
    self._host = host
    self._port = port
    self._sock: Optional[socket.socket] = None
    self._buf = b""
    self._connect()

def _connect(self):
    try:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(2.0)
        self._sock.connect((self._host, self._port))
    except (ConnectionError, OSError):
        self._sock = None

def write(self, data: bytes) -> bool:
    if not self._sock:
        return False
    try:
        frame = _kiss_frame(data)
        self._sock.sendall(frame)
        return True
    except (ConnectionError, OSError):
        return False

def read(self, timeout: float = 1.0) -> Optional[bytes]:
    if not self._sock:
        return None
    try:
        self._sock.settimeout(timeout)
        chunk = self._sock.recv(2048)
        if not chunk:
            return None
        self._buf += chunk
        frames, self._buf = _extract_kiss_frames(self._buf)
        return frames[0] if frames else None
    except (socket.timeout, ConnectionError, OSError):
        return None

def close(self):
    if self._sock:
        try:
            self._sock.close()
        except OSError:
            pass

def is_open(self) -> bool:
    return self._sock is not None
```

class SimulatedTNC(TNCBackend):
“”“File-based HAM radio simulator.”””

```
def __init__(self, callsign: str, channel_dir: Optional[str] = None):
    self.callsign = callsign
    self.channel_dir = channel_dir or os.path.join(
        tempfile.gettempdir(), "ham_sim_channel"
    )
    os.makedirs(self.channel_dir, exist_ok=True)
    self._seen: set[str] = set()

def write(self, data: bytes) -> bool:
    try:
        fname = f"{int(time.time() * 10000)}_{self.callsign}.bin"
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
                if self.callsign in fname:
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

def is_open(self) -> bool:
    return True
```

# ── HAM Transport ──────────────────────────────

class HAMTransport(Transport):
def **init**(self, callsign: str,
tnc_host: str = “127.0.0.1”,
tnc_port: int = 8001,
channel_dir: Optional[str] = None):
“””
Args:
callsign: Amateur radio callsign (required for legal compliance).
tnc_host: KISS TNC host (TCP).
tnc_port: KISS TNC port.
channel_dir: Shared dir for simulator mode.
“””
self.callsign = callsign
self._msg_seq: int = 0

```
    # Try real TNC first, fall back to simulator
    self._backend = KissTNC(tnc_host, tnc_port)
    if not self._backend.is_open():
        self._backend = SimulatedTNC(callsign, channel_dir)

    # Reassembly
    self._reassembly: dict[int, dict[int, bytes]] = defaultdict(dict)
    self._reassembly_meta: dict[int, int] = {}

    self._callback: Optional[Callable[[Message], None]] = None
    self._running = False
    self._thread: Optional[threading.Thread] = None
    self._send_lock = threading.Lock()

@property
def transport_name(self) -> str:
    backend = "TNC" if isinstance(self._backend, KissTNC) else "sim"
    return f"HAM({self.callsign}:{backend})"

def send(self, msg: Message, target: str = "") -> bool:
    # HAM is broadcast by nature (everyone on frequency hears)
    # Inject callsign into message for legal compliance
    return self._transmit(msg)

def broadcast(self, msg: Message) -> int:
    return 1 if self._transmit(msg) else 0

def receive(self) -> Optional[Message]:
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
    data = msg.to_bytes()
    with self._send_lock:
        self._msg_seq = (self._msg_seq + 1) % 65536
        chunks = _chunk_message(data, self._msg_seq)
        for chunk in chunks:
            if not self._backend.write(chunk):
                return False
            if len(chunks) > 1:
                time.sleep(0.1)  # longer inter-chunk for radio
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
        self._reassembly[msg_seq][chunk_idx] = payload
        self._reassembly_meta[msg_seq] = total

        if len(self._reassembly[msg_seq]) >= total:
            full_data = b""
            for i in range(total):
                if i not in self._reassembly[msg_seq]:
                    break
                full_data += self._reassembly[msg_seq][i]
            else:
                msg = Message.from_bytes(full_data)
                if msg and self._callback:
                    self._callback(msg)
            del self._reassembly[msg_seq]
            self._reassembly_meta.pop(msg_seq, None)

        self._cleanup_stale()

def _cleanup_stale(self, max_age_seq: int = 50):
    current = self._msg_seq
    stale = [
        seq for seq in self._reassembly
        if (current - seq) % 65536 > max_age_seq
    ]
    for seq in stale:
        del self._reassembly[seq]
        self._reassembly_meta.pop(seq, None)
```
