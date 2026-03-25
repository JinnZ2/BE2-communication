“””
file_queue.py — File-Based Async Transport

Agents communicate via files in a shared directory.
One agent writes a message file, another reads it when ready.

Works across processes, survives restarts, needs no network.
Good for: truck stop → home base sync, intermittent connectivity,
LoRa relay logging.

Directory layout:
queue_dir/
inbox_{agent_id}/
{timestamp}*{msg_id}.json    ← incoming messages
outbox/
{timestamp}*{msg_id}.json    ← broadcast messages

Released CC0.
“””

import os
import json
import time
import glob
import threading
from typing import Optional, Callable
try:
from ..core.message import Message
from ..core.transport import Transport
except ImportError:
from core.message import Message
from core.transport import Transport

class FileQueueTransport(Transport):
def **init**(self, agent_id: str, queue_dir: str,
poll_interval: float = 1.0):
self.agent_id = agent_id
self.queue_dir = queue_dir
self.poll_interval = poll_interval

```
    # Directories
    self._inbox = os.path.join(queue_dir, f"inbox_{agent_id}")
    self._outbox = os.path.join(queue_dir, "outbox")
    os.makedirs(self._inbox, exist_ok=True)
    os.makedirs(self._outbox, exist_ok=True)

    self._callback: Optional[Callable[[Message], None]] = None
    self._running = False
    self._thread: Optional[threading.Thread] = None
    self._seen: set[str] = set()

@property
def transport_name(self) -> str:
    return f"FileQueue({self.queue_dir})"

def send(self, msg: Message, target: str = "") -> bool:
    """Write message to target's inbox."""
    target_inbox = os.path.join(self.queue_dir, f"inbox_{target}")
    if not os.path.isdir(target_inbox):
        return False
    return self._write_msg(msg, target_inbox)

def broadcast(self, msg: Message) -> int:
    """Write message to outbox (all agents poll this)."""
    self._write_msg(msg, self._outbox)
    # Also write to each known inbox
    sent = 0
    for entry in os.scandir(self.queue_dir):
        if (entry.is_dir()
                and entry.name.startswith("inbox_")
                and entry.name != f"inbox_{self.agent_id}"):
            if self._write_msg(msg, entry.path):
                sent += 1
    return sent

def receive(self) -> Optional[Message]:
    """Read next unprocessed message from inbox."""
    files = sorted(glob.glob(os.path.join(self._inbox, "*.json")))
    for fpath in files:
        if fpath in self._seen:
            continue
        self._seen.add(fpath)
        msg = self._read_msg(fpath)
        if msg:
            return msg
    return None

def start_listening(self, callback: Callable[[Message], None]):
    self._callback = callback
    self._running = True
    self._thread = threading.Thread(
        target=self._poll_loop, daemon=True
    )
    self._thread.start()

def stop_listening(self):
    self._running = False
    if self._thread:
        self._thread.join(timeout=3.0)

def close(self):
    self._running = False

# ── Internal ───────────────────────────────

def _poll_loop(self):
    while self._running:
        msg = self.receive()
        if msg and self._callback:
            self._callback(msg)
        else:
            time.sleep(self.poll_interval)

def _write_msg(self, msg: Message, directory: str) -> bool:
    try:
        fname = f"{int(time.time()*1000)}_{msg.msg_id}.json"
        fpath = os.path.join(directory, fname)
        with open(fpath, "w") as f:
            f.write(msg.to_bytes().decode("utf-8"))
        return True
    except OSError:
        return False

def _read_msg(self, fpath: str) -> Optional[Message]:
    try:
        with open(fpath, "r") as f:
            raw = f.read().encode("utf-8")
        return Message.from_bytes(raw)
    except (OSError, ValueError):
        return None
```
