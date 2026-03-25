“””
cb.py — CB Radio Transport

Unlicensed radio communication — no license required.
Default channel 19 (trucker channel).

CB is audio-based, so this transport works by:
1. Encoding messages as audio tones (FSK/AFSK modem)
2. Keying PTT (Push-To-Talk) via serial DTR/RTS
3. Decoding received audio back to bytes

Hardware options:
- Any CB radio with external speaker/mic jacks
- USB soundcard for audio I/O
- Serial cable for PTT control (DTR pin)
- Or: a CB-to-serial bridge (like a packet TNC)

For development without hardware, uses file-based simulator
(same pattern as LoRa and HAM).

Constraints:
- 4 watts max power (legal limit)
- ~1200 baud practical (AFSK 1200)
- Half-duplex (one talks, others listen)
- Channel congestion on 19 (expect interference)
- No encryption (FCC Part 95)

Usage (simulator):
t = CBTransport(handle=“Northbound_01”)

Usage (with audio interface — future):
t = CBTransport(
handle=“Northbound_01”,
audio_device=“hw:1,0”,
ptt_port=”/dev/ttyUSB0”,
channel=19,
)

Released CC0.
“””

import os
import time
import struct
import threading
import tempfile
from typing import Optional, Callable
from collections import defaultdict

try:
from ..core.message import Message
from ..core.transport import Transport
except ImportError:
from core.message import Message
from core.transport import Transport

CHUNK_MAGIC = b”LC”
CHUNK_HEADER_SIZE = 8
CB_MTU = 200  # smaller than LoRa — audio channel is noisier

def _chunk_message(data: bytes, msg_seq: int) -> list[bytes]:
chunk_payload = CB_MTU - CHUNK_HEADER_SIZE
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

# ── Radio Backends ─────────────────────────────

class SimulatedRadio:
“”“File-based CB simulator. Same shared-channel pattern.”””

```
def __init__(self, handle: str, channel_dir: Optional[str] = None):
    self.handle = handle
    self.channel_dir = channel_dir or os.path.join(
        tempfile.gettempdir(), "cb_sim_ch19"
    )
    os.makedirs(self.channel_dir, exist_ok=True)
    self._seen: set[str] = set()

def transmit(self, data: bytes) -> bool:
    try:
        fname = f"{int(time.time() * 10000)}_{self.handle}.bin"
        fpath = os.path.join(self.channel_dir, fname)
        with open(fpath, "wb") as f:
            f.write(data)
        return True
    except OSError:
        return False

def receive(self, timeout: float = 1.0) -> Optional[bytes]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            files = sorted(os.listdir(self.channel_dir))
            for fname in files:
                if fname in self._seen:
                    continue
                if self.handle in fname:
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
```

# ── CB Transport ───────────────────────────────

class CBTransport(Transport):
def **init**(self, handle: str,
channel: int = 19,
channel_dir: Optional[str] = None):
“””
Args:
handle: CB handle / identifier (e.g. “Northbound_01”).
channel: CB channel (1-40, default 19).
channel_dir: Shared dir for simulator.
“””
self.handle = handle
self.channel = channel
self._msg_seq: int = 0

```
    # Currently simulator only — real audio backend is a future module
    self._radio = SimulatedRadio(handle, channel_dir)

    self._reassembly: dict[int, dict[int, bytes]] = defaultdict(dict)
    self._reassembly_meta: dict[int, int] = {}

    self._callback: Optional[Callable[[Message], None]] = None
    self._running = False
    self._thread: Optional[threading.Thread] = None
    self._send_lock = threading.Lock()

@property
def transport_name(self) -> str:
    return f"CB(ch{self.channel}:{self.handle})"

def send(self, msg: Message, target: str = "") -> bool:
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
    self._radio.close()

def _transmit(self, msg: Message) -> bool:
    data = msg.to_bytes()
    with self._send_lock:
        self._msg_seq = (self._msg_seq + 1) % 65536
        chunks = _chunk_message(data, self._msg_seq)
        for chunk in chunks:
            if not self._radio.transmit(chunk):
                return False
            if len(chunks) > 1:
                time.sleep(0.15)  # CB needs longer gaps
    return True

def _listen_loop(self):
    while self._running:
        raw = self._radio.receive(timeout=0.5)
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
                msg_obj = Message.from_bytes(full_data)
                if msg_obj and self._callback:
                    self._callback(msg_obj)
            del self._reassembly[msg_seq]
            self._reassembly_meta.pop(msg_seq, None)

        # Expire stale
        current = self._msg_seq
        stale = [s for s in self._reassembly
                 if (current - s) % 65536 > 50]
        for s in stale:
            del self._reassembly[s]
            self._reassembly_meta.pop(s, None)
```
