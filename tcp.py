“””
tcp.py — TCP Transport

Real network transport for agents on the same machine or LAN.
Each agent runs a TCP server (listener) and connects to peers as a client.

Wire format: 4-byte big-endian length prefix + message bytes.
Simple, debuggable, works on anything with sockets.

Usage:
transport = TCPTransport(host=“0.0.0.0”, port=9100)
transport.add_peer(“other_agent”, “localhost”, 9101)

Released CC0.
“””

import socket
import struct
import threading
import time
from typing import Optional, Callable
try:
from ..core.message import Message
from ..core.transport import Transport
except ImportError:
from core.message import Message
from core.transport import Transport

# Wire format helpers

def _frame(data: bytes) -> bytes:
“”“Length-prefix a message: [4 bytes big-endian length][payload]”””
return struct.pack(”>I”, len(data)) + data

def _read_frame(sock: socket.socket) -> Optional[bytes]:
“”“Read one length-prefixed frame from a socket.”””
header = _recv_exact(sock, 4)
if not header:
return None
length = struct.unpack(”>I”, header)[0]
if length > 10_000_000:  # 10MB sanity limit
return None
return _recv_exact(sock, length)

def _recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
“”“Read exactly n bytes.”””
buf = bytearray()
while len(buf) < n:
try:
chunk = sock.recv(n - len(buf))
if not chunk:
return None
buf.extend(chunk)
except (ConnectionError, OSError):
return None
return bytes(buf)

class TCPTransport(Transport):
def **init**(self, host: str = “127.0.0.1”, port: int = 9100,
timeout: float = 2.0):
self.host = host
self.port = port
self.timeout = timeout

```
    # Known peers: { agent_id: (host, port) }
    self._peers: dict[str, tuple[str, int]] = {}

    # Server
    self._server_sock: Optional[socket.socket] = None
    self._listener_thread: Optional[threading.Thread] = None
    self._callback: Optional[Callable[[Message], None]] = None
    self._running = False

# ── Peer Management ────────────────────────

def add_peer(self, agent_id: str, host: str, port: int):
    """Register a known peer's address."""
    self._peers[agent_id] = (host, port)

def remove_peer(self, agent_id: str):
    self._peers.pop(agent_id, None)

# ── Transport Interface ────────────────────

@property
def transport_name(self) -> str:
    return f"TCP({self.host}:{self.port})"

def send(self, msg: Message, target: str = "") -> bool:
    """Send to a specific peer by agent_id."""
    if target not in self._peers:
        return False
    host, port = self._peers[target]
    return self._send_to(msg, host, port)

def broadcast(self, msg: Message) -> int:
    """Send to all known peers."""
    sent = 0
    for agent_id, (host, port) in list(self._peers.items()):
        if self._send_to(msg, host, port):
            sent += 1
    return sent

def receive(self) -> Optional[Message]:
    """Not used directly — use start_listening with callback."""
    return None

def start_listening(self, callback: Callable[[Message], None]):
    """Start TCP server in background thread."""
    self._callback = callback
    self._running = True

    self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self._server_sock.settimeout(1.0)
    self._server_sock.bind((self.host, self.port))
    self._server_sock.listen(16)

    self._listener_thread = threading.Thread(
        target=self._listen_loop, daemon=True
    )
    self._listener_thread.start()

def stop_listening(self):
    self._running = False
    if self._listener_thread:
        self._listener_thread.join(timeout=3.0)

def close(self):
    self._running = False
    if self._server_sock:
        try:
            self._server_sock.close()
        except OSError:
            pass

# ── Internal ───────────────────────────────

def _listen_loop(self):
    """Accept connections, read messages, dispatch to callback."""
    while self._running:
        try:
            conn, addr = self._server_sock.accept()
            # Handle each connection in its own thread
            t = threading.Thread(
                target=self._handle_conn, args=(conn,), daemon=True
            )
            t.start()
        except socket.timeout:
            continue
        except OSError:
            break

def _handle_conn(self, conn: socket.socket):
    """Read messages from a single connection."""
    conn.settimeout(self.timeout)
    try:
        while self._running:
            raw = _read_frame(conn)
            if raw is None:
                break
            msg = Message.from_bytes(raw)
            if msg and self._callback:
                self._callback(msg)
    finally:
        conn.close()

def _send_to(self, msg: Message, host: str, port: int) -> bool:
    """Open connection, send one framed message, close."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect((host, port))
        sock.sendall(_frame(msg.to_bytes()))
        sock.close()
        return True
    except (ConnectionError, OSError, socket.timeout):
        return False
```
