"""
udp.py — UDP Broadcast Transport

Zero-config LAN discovery. Agents broadcast on a shared port,
anyone listening picks it up. No peer registration needed.

Two modes:
- Broadcast: send to 255.255.255.255 (all devices on subnet)
- Multicast: send to a multicast group (more targeted, works across subnets)

Default is broadcast — simplest, works on any LAN.

Tradeoffs vs TCP:
+ No connection setup — fire and forget
+ Natural broadcast — everyone hears everything
+ Works for discovery without knowing peer addresses
- No delivery guarantee (messages can be lost)
- No ordering guarantee
- Max ~65KB per message (practical limit ~1400 bytes for MTU safety)

Usage:
t = UDPTransport(port=9200)
# That's it. No add_peer() needed. Just broadcast.

Released CC0.
"""

import socket
import struct
import threading
import json
from typing import Optional, Callable

from core.message import Message
from core.transport import Transport

# Wire format: 4-byte magic + 4-byte length + payload

# Magic bytes identify agent-protocol packets vs random UDP noise

MAGIC = b"AG01"


def _frame(data: bytes) -> bytes:
    return MAGIC + struct.pack(">I", len(data)) + data


def _unframe(raw: bytes) -> Optional[bytes]:
    if len(raw) < 8:
        return None
    if raw[:4] != MAGIC:
        return None  # not our protocol — ignore gracefully
    length = struct.unpack(">I", raw[4:8])[0]
    payload = raw[8:]
    if len(payload) < length:
        return None  # truncated — ignore
    return payload[:length]


class UDPTransport(Transport):
    def __init__(self, port: int = 9200,
                 bind_addr: str = "0.0.0.0",
                 broadcast_addr: str = "255.255.255.255",
                 max_packet: int = 4096):
        self.port = port
        self.bind_addr = bind_addr
        self.broadcast_addr = broadcast_addr
        self.max_packet = max_packet

        # Send socket (broadcast-enabled)
        self._send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Receive socket
        self._recv_sock: Optional[socket.socket] = None
        self._callback: Optional[Callable[[Message], None]] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Track known peer addresses for direct send
        # { agent_id: (host, port) } — populated from incoming messages
        self._peer_addrs: dict[str, tuple[str, int]] = {}

    @property
    def transport_name(self) -> str:
        return f"UDP(:{self.port})"

    def send(self, msg: Message, target: str = "") -> bool:
        """Send to a specific peer (if we've seen them before)."""
        if target in self._peer_addrs:
            addr = self._peer_addrs[target]
            return self._send_to(msg, addr)
        # Don't know where they are — broadcast instead
        return self.broadcast(msg) > 0

    def broadcast(self, msg: Message) -> int:
        """Broadcast to all devices on the subnet."""
        return 1 if self._send_to(msg, (self.broadcast_addr, self.port)) else 0

    def receive(self) -> Optional[Message]:
        """Not used directly — use start_listening."""
        return None

    def start_listening(self, callback: Callable[[Message], None]):
        self._callback = callback
        self._running = True

        self._recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # SO_REUSEPORT allows multiple agents on same machine/port
        try:
            self._recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass  # not available on all platforms

        self._recv_sock.settimeout(1.0)
        self._recv_sock.bind((self.bind_addr, self.port))

        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop_listening(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)

    def close(self):
        self._running = False
        try:
            self._send_sock.close()
        except OSError:
            pass
        if self._recv_sock:
            try:
                self._recv_sock.close()
            except OSError:
                pass

    # ── Peer tracking ──────────────────────────

    def add_peer(self, agent_id: str, host: str, port: int):
        """Manually register a peer address for direct sends."""
        self._peer_addrs[agent_id] = (host, port)

    @property
    def known_peers(self) -> dict[str, tuple[str, int]]:
        return dict(self._peer_addrs)

    # ── Internal ───────────────────────────────

    def _listen_loop(self):
        while self._running:
            try:
                data, addr = self._recv_sock.recvfrom(self.max_packet)
                payload = _unframe(data)
                if payload is None:
                    continue  # not our protocol or truncated
                msg = Message.from_bytes(payload)
                if msg:
                    # Learn peer address from incoming message
                    self._peer_addrs[msg.sender] = addr
                    if self._callback:
                        self._callback(msg)
            except socket.timeout:
                continue
            except OSError:
                break

    def _send_to(self, msg: Message, addr: tuple[str, int]) -> bool:
        try:
            raw = _frame(msg.to_bytes())
            if len(raw) > self.max_packet:
                return False  # too big for UDP
            self._send_sock.sendto(raw, addr)
            return True
        except (OSError, socket.error):
            return False
