"""
transports/local.py — In-process LocalHub and LocalTransport.

Thread-safe queues, no network. For testing and single-machine sims.

Released CC0.
"""

import queue
import threading
from typing import Callable, Dict, Optional

from core.message import Message
from core.transport import Transport


class LocalHub:
    """
    In-process message router.

    Agents register via their LocalTransport. Messages are routed through
    thread-safe queues — no sockets, no serialization overhead.
    """

    def __init__(self):
        self._agents: Dict[str, "LocalTransport"] = {}
        self._lock = threading.Lock()

    def register(self, agent_id: str, transport: "LocalTransport"):
        with self._lock:
            self._agents[agent_id] = transport

    def unregister(self, agent_id: str):
        with self._lock:
            self._agents.pop(agent_id, None)

    def route(self, msg: Message, target: str):
        """Deliver a message to a specific agent."""
        with self._lock:
            t = self._agents.get(target)
        if t:
            t._enqueue(msg)

    def broadcast(self, msg: Message):
        """Deliver a message to all registered agents."""
        with self._lock:
            targets = list(self._agents.values())
        for t in targets:
            t._enqueue(msg)


class LocalTransport(Transport):
    """
    Transport backed by a LocalHub. Messages stay in-process.

    Usage::

        hub = LocalHub()
        t = LocalTransport("my_agent", hub)
    """

    def __init__(self, agent_id: str, hub: LocalHub):
        self.agent_id = agent_id
        self.hub = hub
        self._inbox: queue.Queue = queue.Queue()
        self._callback: Optional[Callable[[Message], None]] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._running = False
        hub.register(agent_id, self)

    def send(self, msg: Message, target: str) -> None:
        self.hub.route(msg, target)

    def broadcast(self, msg: Message) -> None:
        self.hub.broadcast(msg)

    def receive(self) -> Optional[Message]:
        try:
            return self._inbox.get_nowait()
        except queue.Empty:
            return None

    def start_listening(self, callback: Callable[[Message], None]) -> None:
        self._callback = callback
        self._running = True
        self._listener_thread = threading.Thread(
            target=self._listen_loop, daemon=True
        )
        self._listener_thread.start()

    def stop_listening(self) -> None:
        self._running = False
        # Unblock the listener if it's waiting
        self._inbox.put(None)
        if self._listener_thread:
            self._listener_thread.join(timeout=1.0)

    def close(self) -> None:
        self.stop_listening()
        self.hub.unregister(self.agent_id)

    # ── internals ────────────────────────────

    def _enqueue(self, msg: Message):
        self._inbox.put(msg)

    def _listen_loop(self):
        while self._running:
            try:
                msg = self._inbox.get(timeout=0.1)
            except queue.Empty:
                continue
            if msg is None:
                break
            if self._callback:
                self._callback(msg)
