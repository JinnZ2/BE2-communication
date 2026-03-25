"""
transports/file_queue.py — File-based async transport for agent-protocol.

File-based message passing. Works across processes, survives restarts.

Each agent watches an inbox directory for new .msg files. Messages are
written atomically (write-to-tmp then rename) to avoid partial reads.

Released CC0.
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from core.message import Message
from core.transport import Transport


class FileQueueTransport(Transport):
    """
    File-based async transport.

    Messages are JSON files dropped into per-agent inbox directories
    under a shared queue root.

    Usage::

        t = FileQueueTransport("my_agent", "/shared/queue_dir")
        t.start_listening(callback)
    """

    def __init__(self, agent_id: str, queue_dir: str,
                 poll_interval: float = 0.25):
        self.agent_id = agent_id
        self.queue_dir = Path(queue_dir)
        self.poll_interval = poll_interval
        self._inbox_dir = self.queue_dir / agent_id
        self._broadcast_dir = self.queue_dir / "_broadcast"
        self._callback: Optional[Callable[[Message], None]] = None
        self._poll_thread: Optional[threading.Thread] = None
        self._running = False
        self._seen: set = set()

        # Ensure directories exist
        self._inbox_dir.mkdir(parents=True, exist_ok=True)
        self._broadcast_dir.mkdir(parents=True, exist_ok=True)

    @property
    def transport_name(self) -> str:
        return f"FileQueue({self.agent_id})"

    def send(self, msg: Message, target: str = "") -> bool:
        target_dir = self.queue_dir / target
        target_dir.mkdir(parents=True, exist_ok=True)
        self._write_message(msg, target_dir)
        return True

    def broadcast(self, msg: Message) -> int:
        self._write_message(msg, self._broadcast_dir)
        return 1

    def receive(self) -> Optional[Message]:
        for msg_file in sorted(self._inbox_dir.glob("*.msg")):
            if msg_file.name in self._seen:
                continue
            self._seen.add(msg_file.name)
            msg = self._read_message(msg_file)
            if msg:
                return msg
        # Also check broadcast
        for msg_file in sorted(self._broadcast_dir.glob("*.msg")):
            if msg_file.name in self._seen:
                continue
            self._seen.add(msg_file.name)
            msg = self._read_message(msg_file)
            if msg:
                return msg
        return None

    def start_listening(self, callback: Callable[[Message], None]) -> None:
        self._callback = callback
        self._running = True
        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True
        )
        self._poll_thread.start()

    def stop_listening(self) -> None:
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=2.0)

    def close(self) -> None:
        self.stop_listening()

    # ── internals ────────────────────────────

    def _write_message(self, msg: Message, target_dir: Path):
        """Atomic write: tmp file then rename to prevent partial reads."""
        filename = f"{msg.timestamp:.6f}_{msg.msg_id}.msg"
        fd, tmp_path = tempfile.mkstemp(
            dir=str(target_dir), suffix=".tmp"
        )
        try:
            os.write(fd, msg.to_bytes())
        finally:
            os.close(fd)
        os.rename(tmp_path, str(target_dir / filename))

    @staticmethod
    def _read_message(path: Path) -> Optional[Message]:
        try:
            data = path.read_bytes()
            return Message.from_bytes(data)
        except (json.JSONDecodeError, KeyError, OSError):
            return None  # graceful degradation

    def _poll_loop(self):
        while self._running:
            self._scan_dir(self._inbox_dir)
            self._scan_dir(self._broadcast_dir)
            time.sleep(self.poll_interval)

    def _scan_dir(self, directory: Path):
        try:
            files = sorted(directory.glob("*.msg"))
        except OSError:
            return
        for msg_file in files:
            if msg_file.name in self._seen:
                continue
            self._seen.add(msg_file.name)
            msg = self._read_message(msg_file)
            if msg and self._callback:
                self._callback(msg)
