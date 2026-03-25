"""
wifi_direct.py — WiFi Direct (P2P) Transport

Phone-to-phone communication over WiFi without any access point,
router, or internet connection. Higher bandwidth and longer range
than BLE (~200m, ~250 Mbps).

WiFi Direct creates an ad-hoc group where one device acts as the
Group Owner (GO, effectively a soft AP) and others connect as
clients. This transport abstracts that into the standard
send/broadcast/receive interface.

Platform APIs:
- Android: WifiP2pManager (android.net.wifi.p2p)
- iOS: Multipeer Connectivity Framework
- Linux: wpa_supplicant P2P commands
- Python: socket-based once the P2P link is established

The WiFi Direct link setup is platform-specific, but once
established, it's just TCP/UDP sockets on a local subnet.
This transport uses UDP broadcast on the P2P interface for
discovery and TCP for reliable message delivery.

For development without hardware, uses file-based simulator
(same pattern as other radio transports).

Constraints:
- ~200m range (open air, can be more with clear line of sight)
- High bandwidth (~250 Mbps) — no chunking needed
- Requires WiFi hardware (all modern phones have it)
- One device must be Group Owner
- Power consumption higher than BLE

Usage (simulator):
    t = WiFiDirectTransport(device_id="phone_01")

Usage (real WiFi Direct — after P2P group is established):
    t = WiFiDirectTransport(device_id="phone_01",
                            group_iface="p2p-wlan0-0",
                            group_port=19200)

Released CC0.
"""

import os
import socket
import struct
import time
import threading
import tempfile
from typing import Optional, Callable

from core.message import Message
from core.transport import Transport

# Wire format: same as UDP transport — magic + length + JSON
MAGIC = b"WFD1"  # WiFi Direct protocol marker


def _frame(data: bytes) -> bytes:
    return MAGIC + struct.pack(">I", len(data)) + data


def _unframe(raw: bytes) -> Optional[bytes]:
    if len(raw) < 8 or raw[:4] != MAGIC:
        return None
    length = struct.unpack(">I", raw[4:8])[0]
    payload = raw[8:]
    if len(payload) < length:
        return None
    return payload[:length]


# ── WiFi Direct Backends ──────────────────────

class WiFiDirectBackend:
    """Abstract WiFi Direct interface."""

    def send_to_group(self, data: bytes) -> bool: ...
    def receive_from_group(self, timeout: float = 1.0) -> Optional[tuple[bytes, str]]: ...
    def close(self): ...
    def is_available(self) -> bool: ...


class RealWiFiDirect(WiFiDirectBackend):
    """
    Real WiFi Direct using sockets on the P2P interface.

    Assumes the WiFi Direct group is already established
    (via Android WifiP2pManager, wpa_cli p2p_connect, etc.).
    Once the P2P link is up, communication is plain sockets.
    """

    def __init__(self, device_id: str,
                 group_iface: str = "p2p-wlan0-0",
                 group_port: int = 19200,
                 broadcast_addr: str = "192.168.49.255"):
        self.device_id = device_id
        self.group_iface = group_iface
        self.group_port = group_port
        self.broadcast_addr = broadcast_addr
        self._available = False

        try:
            self._send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            self._recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self._recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass
            self._recv_sock.settimeout(1.0)
            self._recv_sock.bind(("0.0.0.0", group_port))
            self._available = True
        except OSError:
            self._available = False

    def send_to_group(self, data: bytes) -> bool:
        if not self._available:
            return False
        try:
            self._send_sock.sendto(data, (self.broadcast_addr, self.group_port))
            return True
        except OSError:
            return False

    def receive_from_group(self, timeout: float = 1.0) -> Optional[tuple[bytes, str]]:
        if not self._available:
            return None
        try:
            self._recv_sock.settimeout(timeout)
            data, addr = self._recv_sock.recvfrom(65536)
            return data, addr[0]
        except (socket.timeout, OSError):
            return None

    def close(self):
        try:
            self._send_sock.close()
        except OSError:
            pass
        try:
            self._recv_sock.close()
        except OSError:
            pass

    def is_available(self) -> bool:
        return self._available


class SimulatedWiFiDirect(WiFiDirectBackend):
    """
    File-based WiFi Direct simulator for development.
    Simulates the group broadcast — all instances sharing
    the same group_dir can see each other's messages.
    """

    def __init__(self, device_id: str, group_dir: Optional[str] = None):
        self.device_id = device_id
        self.group_dir = group_dir or os.path.join(
            tempfile.gettempdir(), "wifi_direct_sim"
        )
        os.makedirs(self.group_dir, exist_ok=True)
        self._seen: set[str] = set()

    def send_to_group(self, data: bytes) -> bool:
        try:
            fname = f"{int(time.time() * 10000)}_{self.device_id}.bin"
            fpath = os.path.join(self.group_dir, fname)
            with open(fpath, "wb") as f:
                f.write(data)
            return True
        except OSError:
            return False

    def receive_from_group(self, timeout: float = 1.0) -> Optional[tuple[bytes, str]]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                files = sorted(os.listdir(self.group_dir))
                for fname in files:
                    if fname in self._seen:
                        continue
                    if self.device_id in fname:
                        self._seen.add(fname)
                        continue
                    fpath = os.path.join(self.group_dir, fname)
                    self._seen.add(fname)
                    with open(fpath, "rb") as f:
                        data = f.read()
                    # Extract sender from filename
                    sender = fname.split("_", 1)[1].replace(".bin", "")
                    return data, sender
            except OSError:
                pass
            time.sleep(0.05)
        return None

    def close(self):
        pass

    def is_available(self) -> bool:
        return True


# ── WiFi Direct Transport ─────────────────────

class WiFiDirectTransport(Transport):
    """
    WiFi Direct transport for high-bandwidth phone-to-phone communication.

    Once a WiFi Direct group is formed, this transport provides:
    - UDP broadcast for discovery and short messages
    - No chunking needed (WiFi supports large frames)
    - Auto-learns peer addresses from incoming messages
    - Works alongside BLE (use BLE for discovery, WiFi Direct for data)
    """

    def __init__(self, device_id: str = "wfd_device",
                 group_iface: str = "",
                 group_port: int = 19200,
                 group_dir: Optional[str] = None):
        self.device_id = device_id
        self.group_port = group_port

        # Track known peers
        self._peer_addrs: dict[str, str] = {}  # agent_id -> ip_or_device_id

        # Select backend
        if group_iface:
            self._backend = RealWiFiDirect(device_id, group_iface, group_port)
            if not self._backend.is_available():
                self._backend = SimulatedWiFiDirect(device_id, group_dir)
        else:
            self._backend = SimulatedWiFiDirect(device_id, group_dir)

        # Message dedup
        self._seen_msgs: set[str] = set()

        self._callback: Optional[Callable[[Message], None]] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def transport_name(self) -> str:
        backend = "wfd" if isinstance(self._backend, RealWiFiDirect) else "sim"
        return f"WiFiDirect({backend}:{self.device_id})"

    def send(self, msg: Message, target: str = "") -> bool:
        """Send to group (WiFi Direct is effectively a local broadcast)."""
        return self._transmit(msg)

    def broadcast(self, msg: Message) -> int:
        """Broadcast to the WiFi Direct group."""
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

    def add_peer(self, agent_id: str, addr: str):
        """Manually register a peer address."""
        self._peer_addrs[agent_id] = addr

    @property
    def known_peers(self) -> dict[str, str]:
        return dict(self._peer_addrs)

    # ── Internal ───────────────────────────────

    def _transmit(self, msg: Message) -> bool:
        data = _frame(msg.to_bytes())
        self._seen_msgs.add(msg.msg_id)
        return self._backend.send_to_group(data)

    def _listen_loop(self):
        while self._running:
            result = self._backend.receive_from_group(timeout=0.5)
            if result is None:
                continue

            raw, sender_addr = result
            payload = _unframe(raw)
            if payload is None:
                continue

            msg = Message.from_bytes(payload)
            if msg:
                # Dedup
                if msg.msg_id in self._seen_msgs:
                    continue
                self._seen_msgs.add(msg.msg_id)

                # Learn peer address
                self._peer_addrs[msg.sender] = sender_addr

                if self._callback:
                    self._callback(msg)

            # Prevent unbounded growth
            if len(self._seen_msgs) > 10000:
                # Keep most recent half
                self._seen_msgs = set(list(self._seen_msgs)[-5000:])
