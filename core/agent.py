"""
core/agent.py — Base Agent class for agent-protocol.

Agents show up and talk. No handshake ceremony, no approval flow.
Opportunistic discovery: you know who you've met, that's it.

Subclass Agent and override on_message() to build custom behaviors.

Released CC0.
"""

import threading
from typing import Any, Dict, List, Optional

from core.message import (
    ANNOUNCE, BYE, DONE, OFFER, QUERY, REPLY, STATE, STUCK, Message,
)
from core.state import AgentState
from core.transport import Transport


class Agent:
    """
    Base agent that can send, receive, and respond to protocol messages.

    Usage::

        class MyAgent(Agent):
            def on_message(self, msg):
                if msg.verb == "QUERY":
                    self.reply_to(msg, {"answer": "42"})

        hub = LocalHub()
        a = MyAgent("agent_a", transport=LocalTransport("agent_a", hub),
                     capabilities=["math"])
        a.start()
    """

    def __init__(
        self,
        agent_id: str,
        transport: Transport,
        capabilities: Optional[List[str]] = None,
    ):
        self.agent_id = agent_id
        self.transport = transport
        self.state = AgentState(
            agent_id=agent_id,
            capabilities=capabilities or [],
        )
        self._running = False
        self._lock = threading.Lock()

    # ── lifecycle ────────────────────────────

    def start(self):
        """Begin listening for messages and announce presence."""
        self._running = True
        self.state.status = "ACTIVE"
        self.state.touch()
        self.transport.start_listening(self._handle_incoming)
        self.announce()

    def stop(self):
        """Send BYE, stop listening, and release resources."""
        if not self._running:
            return
        self._send(BYE)
        self._running = False
        self.state.status = "GONE"
        self.transport.stop_listening()
        self.transport.close()

    # ── public verbs ─────────────────────────

    def announce(self):
        """Broadcast: I'm here, this is what I do."""
        self._send(ANNOUNCE, payload={"capabilities": self.state.capabilities})

    def ask(self, question: str, recipient: Optional[str] = None):
        """Send a QUERY to a specific agent or broadcast."""
        self._send(QUERY, recipient=recipient, payload={"question": question})

    def share(self, recipient: Optional[str] = None):
        """Share current state with a specific agent or broadcast."""
        self._send(STATE, recipient=recipient, payload=self.state.to_dict())

    def offer(self, description: str, data: Optional[Dict[str, Any]] = None,
              recipient: Optional[str] = None):
        """Offer a resource or capability."""
        payload: Dict[str, Any] = {"description": description}
        if data:
            payload["data"] = data
        self._send(OFFER, recipient=recipient, payload=payload)

    def stuck(self, problem: str, recipient: Optional[str] = None):
        """Signal that help is needed."""
        self._send(STUCK, recipient=recipient, payload={"problem": problem})

    def done(self, summary: str, recipient: Optional[str] = None):
        """Announce completion of a task."""
        self._send(DONE, recipient=recipient, payload={"summary": summary})

    def reply_to(self, original: Message, payload: Dict[str, Any]):
        """Send a REPLY in response to a received message."""
        msg = Message(
            verb=REPLY,
            sender=self.agent_id,
            recipient=original.sender,
            payload=payload,
            in_reply_to=original.msg_id,
        )
        self.state.touch()
        self.transport.send(msg, original.sender)

    # ── override point ───────────────────────

    def on_message(self, msg: Message):
        """
        Override this method to handle incoming messages.

        Called for every message received (broadcast or directed).
        The default implementation does nothing — agents ignore what
        they don't understand (graceful degradation).
        """

    # ── internals ────────────────────────────

    def _send(self, verb: str, recipient: Optional[str] = None,
              payload: Optional[Dict[str, Any]] = None):
        msg = Message(
            verb=verb,
            sender=self.agent_id,
            recipient=recipient,
            payload=payload or {},
        )
        self.state.touch()
        if recipient:
            self.transport.send(msg, recipient)
        else:
            self.transport.broadcast(msg)

    def _handle_incoming(self, msg: Message):
        """Dispatch an incoming message after bookkeeping."""
        if msg.sender == self.agent_id:
            return  # ignore own messages

        with self._lock:
            self.state.add_peer(msg.sender)
            self.state.touch()

            if msg.verb == ANNOUNCE:
                self.state.add_peer(msg.sender)

            self.on_message(msg)
