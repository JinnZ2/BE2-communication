"""
core/message.py — Message format for agent-protocol.

Messages are the sole unit of communication between agents. Each message
carries a verb, sender, optional recipient, and a freeform payload dict.
Wire format is JSON-over-UTF-8 so humans can debug by reading the wire.

Released CC0.
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ─────────────────────────────────────────────
# Verb constants
# ─────────────────────────────────────────────

ANNOUNCE = "ANNOUNCE"
QUERY = "QUERY"
STATE = "STATE"
OFFER = "OFFER"
REPLY = "REPLY"
DONE = "DONE"
STUCK = "STUCK"
BYE = "BYE"

ALL_VERBS = {ANNOUNCE, QUERY, STATE, OFFER, REPLY, DONE, STUCK, BYE}


# ─────────────────────────────────────────────
# Message dataclass
# ─────────────────────────────────────────────

@dataclass
class Message:
    """
    A single protocol message.

    Attributes:
        verb:       One of the ALL_VERBS constants.
        sender:     ID of the sending agent.
        recipient:  ID of the target agent, or None for broadcast.
        payload:    Arbitrary dict of data.
        msg_id:     Unique message identifier (auto-generated).
        timestamp:  Unix timestamp (auto-generated).
        in_reply_to: msg_id of the message this is responding to (optional).
    """
    verb: str
    sender: str
    recipient: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    msg_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    in_reply_to: Optional[str] = None

    def serialize(self) -> bytes:
        """Encode message to JSON bytes for wire transmission."""
        return json.dumps({
            "verb": self.verb,
            "sender": self.sender,
            "recipient": self.recipient,
            "payload": self.payload,
            "msg_id": self.msg_id,
            "timestamp": self.timestamp,
            "in_reply_to": self.in_reply_to,
        }).encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes) -> "Message":
        """Decode JSON bytes back into a Message."""
        d = json.loads(data.decode("utf-8"))
        return cls(
            verb=d["verb"],
            sender=d["sender"],
            recipient=d.get("recipient"),
            payload=d.get("payload", {}),
            msg_id=d.get("msg_id", uuid.uuid4().hex[:12]),
            timestamp=d.get("timestamp", time.time()),
            in_reply_to=d.get("in_reply_to"),
        )

    def __repr__(self):
        to = self.recipient or "BROADCAST"
        return f"Message({self.verb}, {self.sender}->{to}, payload={self.payload})"
