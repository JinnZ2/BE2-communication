"""
transports/tcp.py — TCP socket transport for agent-protocol.

Real sockets, length-prefixed framing. For LAN or same-machine
multi-process communication.

Wire format: [4 bytes big-endian length] + [JSON message bytes]

Released CC0.
"""

import json
import queue
import socket
import struct
import threading
from typing import Callable, Dict, Optional, Tuple

from core.message import Message
from core.transport import Transport


class TCPTransport(Transport):
    """
    TCP transport with length-prefixed JSON framing.

    Usage::

        t = TCPTransport(host="127.0.0.1", port=9100)
        t.add_peer("other_agent", "127.0.0.1", 9101)
        t.start_listening(callback)
        t.send(msg, "other_agent")
    """

    HEADER_FMT = ">I"  # 4-byte big-endian unsigned int
    HEADER_SIZE = 4

    def __init__(self, host: str = "127.0.0.1", port: int = 9100):
        self.host = host
        self.port = port
        self._peers: Dict[str, Tuple[str, int]] = {}
        self._inbox: queue.Queue = queue.Queue()
        self._callback: Optional[Callable[[Message], None]] = None
        self._server_socket: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._running = False

    @property
    def transport_name(self) -> str:
        return f"TCP({self.host}:{self.port})"

    def add_peer(self, agent_id: str, host: str, port: int):
        """Register a known peer's address for direct sends."""
        self._peers[agent_id] = (host, port)

    def send(self, msg: Message, target: str = "") -> bool:
        addr = self._peers.get(target)
        if not addr:
            return False
        return self._tcp_send(msg, addr)

    def broadcast(self, msg: Message) -> int:
        count = 0
        for addr in list(self._peers.values()):
            if self._tcp_send(msg, addr):
                count += 1
        return count

    def receive(self) -> Optional[Message]:
        try:
            return self._inbox.get_nowait()
        except queue.Empty:
            return None

    def start_listening(self, callback: Callable[[Message], None]) -> None:
        self._callback = callback
        self._running = True
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.settimeout(0.5)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(8)
        self._accept_thread = threading.Thread(
            target=self._accept_loop, daemon=True
        )
        self._accept_thread.start()

    def stop_listening(self) -> None:
        self._running = False
        if self._accept_thread:
            self._accept_thread.join(timeout=2.0)

    def close(self) -> None:
        self.stop_listening()
        if self._server_socket:
            self._server_socket.close()
            self._server_socket = None

    # ── internals ────────────────────────────

    def _tcp_send(self, msg: Message, addr: Tuple[str, int]) -> bool:
        data = msg.to_bytes()
        frame = struct.pack(self.HEADER_FMT, len(data)) + data
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect(addr)
                s.sendall(frame)
            return True
        except OSError:
            return False

    def _accept_loop(self):
        while self._running:
            try:
                conn, _ = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle_conn, args=(conn,), daemon=True
            ).start()

    def _handle_conn(self, conn: socket.socket):
        try:
            conn.settimeout(2.0)
            header = self._recv_exact(conn, self.HEADER_SIZE)
            if not header:
                return
            length = struct.unpack(self.HEADER_FMT, header)[0]
            data = self._recv_exact(conn, length)
            if not data:
                return
            msg = Message.from_bytes(data)
            if msg:
                if self._callback:
                    self._callback(msg)
                else:
                    self._inbox.put(msg)
        except (OSError, json.JSONDecodeError, KeyError):
            pass  # malformed messages get ignored
        finally:
            conn.close()

    @staticmethod
    def _recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)
