“””
message.py — Agent Communication Message

Format: plaintext-first, machine-parseable second.
No rigid schema. Listeners extract what makes sense to them.

Message types (verbs):
ANNOUNCE  — “I’m here, this is what I do”
QUERY     — “Do you know about X?”
STATE     — “Here’s where I am right now”
OFFER     — “I have X if you need it”
REPLY     — “Here’s what you asked about”
DONE      — “I finished X”
STUCK     — “I need help with X”
BYE       — “I’m leaving”

Released CC0.
“””

import time
import uuid
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

VALID_VERBS = frozenset({
“ANNOUNCE”, “QUERY”, “STATE”, “OFFER”,
“REPLY”, “DONE”, “STUCK”, “BYE”,
})

@dataclass
class Message:
verb: str                              # What kind of speech act
sender: str                            # Who’s talking
body: Any = None                       # Payload (string, dict, whatever)
topic: str = “”                        # What domain / subject
recipient: str = “”                    # Empty = broadcast to all
in_reply_to: str = “”                  # Message ID this responds to
msg_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
timestamp: float = field(default_factory=time.time)

```
def __post_init__(self):
    self.verb = self.verb.upper()

# ── Serialization ──────────────────────────

def to_bytes(self) -> bytes:
    """Serialize to wire format. JSON for now — swap later if needed."""
    return json.dumps(asdict(self), default=str).encode("utf-8")

@classmethod
def from_bytes(cls, raw: bytes) -> Optional["Message"]:
    """
    Best-effort parse. Returns None if unintelligible.
    This is the 'graceful degradation' — malformed messages
    don't crash anything, they just get ignored.
    """
    try:
        d = json.loads(raw.decode("utf-8"))
        return cls(**{k: v for k, v in d.items()
                     if k in cls.__dataclass_fields__})
    except Exception:
        return None

# ── Human-readable ─────────────────────────

def __str__(self) -> str:
    target = f" → {self.recipient}" if self.recipient else " → *"
    topic = f" [{self.topic}]" if self.topic else ""
    body_preview = ""
    if self.body:
        s = str(self.body)
        body_preview = f" | {s[:80]}{'…' if len(s) > 80 else ''}"
    return f"{self.verb}{target} from {self.sender}{topic}{body_preview}"

# ── Convenience constructors ───────────────

@classmethod
def announce(cls, sender: str, capabilities: list[str],
             **kwargs) -> "Message":
    return cls(verb="ANNOUNCE", sender=sender,
               body={"capabilities": capabilities}, **kwargs)

@classmethod
def query(cls, sender: str, question: str, topic: str = "",
          recipient: str = "", **kwargs) -> "Message":
    return cls(verb="QUERY", sender=sender, body=question,
               topic=topic, recipient=recipient, **kwargs)

@classmethod
def state(cls, sender: str, snapshot: dict,
          **kwargs) -> "Message":
    return cls(verb="STATE", sender=sender, body=snapshot, **kwargs)

@classmethod
def offer(cls, sender: str, what: str, topic: str = "",
          recipient: str = "", **kwargs) -> "Message":
    return cls(verb="OFFER", sender=sender, body=what,
               topic=topic, recipient=recipient, **kwargs)

@classmethod
def reply(cls, sender: str, body: Any,
          original: "Message", **kwargs) -> "Message":
    return cls(verb="REPLY", sender=sender, body=body,
               recipient=original.sender,
               in_reply_to=original.msg_id,
               topic=original.topic, **kwargs)

@classmethod
def done(cls, sender: str, what: str, **kwargs) -> "Message":
    return cls(verb="DONE", sender=sender, body=what, **kwargs)

@classmethod
def stuck(cls, sender: str, problem: str, topic: str = "",
          **kwargs) -> "Message":
    return cls(verb="STUCK", sender=sender, body=problem,
               topic=topic, **kwargs)

@classmethod
def bye(cls, sender: str, **kwargs) -> "Message":
    return cls(verb="BYE", sender=sender, **kwargs)
```
