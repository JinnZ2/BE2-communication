“””
local.py — In-Process Transport

Shared message bus for agents in the same process.
No network, no sockets — just a thread-safe queue per agent.
Perfect for testing and single-machine simulations.

Usage:
hub = LocalHub()
t1 = LocalTransport(“agent_a”, hub)
t2 = LocalTransport(“agent_b”, hub)

Released CC0.
“””

import threading
import queue
import time
from typing import Optional, Callable
try:
from ..core.message import Message
from ..core.transport import Transport
except ImportError:
from core.message import Message
from core.transport import Transport

class LocalHub:
“””
Central message bus for in-process agents.
Agents register, hub routes messages.
“””

```
def __init__(self):
    self._agents: dict[str, queue.Queue] = {}
    self._lock = threading.Lock()

def register(self, agent_id: str) -> queue.Queue:
    with self._lock:
        q = queue.Queue(maxsize=1000)
        self._agents[agent_id] = q
        return q

def unregister(self, agent_id: str):
    with self._lock:
        self._agents.pop(agent_id, None)

def send(self, msg: Message, target: str) -> bool:
    with self._lock:
        q = self._agents.get(target)
    if q:
        try:
            q.put_nowait(msg)
            return True
        except queue.Full:
            return False
    return False

def broadcast(self, msg: Message, sender: str) -> int:
    with self._lock:
        targets = [(aid, q) for aid, q in self._agents.items()
                   if aid != sender]
    sent = 0
    for aid, q in targets:
        try:
            q.put_nowait(msg)
            sent += 1
        except queue.Full:
            pass
    return sent
```

class LocalTransport(Transport):
def **init**(self, agent_id: str, hub: LocalHub):
self.agent_id = agent_id
self.hub = hub
self._queue = hub.register(agent_id)
self._callback: Optional[Callable[[Message], None]] = None
self._running = False
self._thread: Optional[threading.Thread] = None

```
@property
def transport_name(self) -> str:
    return f"Local({self.agent_id})"

def send(self, msg: Message, target: str = "") -> bool:
    return self.hub.send(msg, target)

def broadcast(self, msg: Message) -> int:
    return self.hub.broadcast(msg, self.agent_id)

def receive(self) -> Optional[Message]:
    try:
        return self._queue.get_nowait()
    except queue.Empty:
        return None

def start_listening(self, callback: Callable[[Message], None]):
    self._callback = callback
    self._running = True
    self._thread = threading.Thread(
        target=self._listen_loop, daemon=True
    )
    self._thread.start()

def _listen_loop(self):
    while self._running:
        try:
            msg = self._queue.get(timeout=0.1)
            if self._callback:
                self._callback(msg)
        except queue.Empty:
            continue

def stop_listening(self):
    self._running = False
    if self._thread:
        self._thread.join(timeout=2.0)

def close(self):
    self._running = False
    self.hub.unregister(self.agent_id)
```
