“””
state.py — Agent State Snapshot

When agents meet, first exchange is “where are you?”
This is the equivalent of walking up and reading the room.

The snapshot is intentionally loose — agents add whatever
fields make sense for their domain. The core fields are
just enough to know: who, what, how healthy, what do you need.

Released CC0.
“””

import time
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class AgentState:
agent_id: str
agent_type: str = “”               # What kind of agent (encoder, validator, etc.)
status: str = “IDLE”               # IDLE, ACTIVE, BUSY, STUCK, SURVIVAL, OFFLINE
current_task: str = “”             # What are you doing right now
capacity: float = 1.0             # 0.0 = maxed out, 1.0 = fully available
needs: list[str] = field(default_factory=list)   # What do you need from others
offers: list[str] = field(default_factory=list)   # What can you provide
extras: dict[str, Any] = field(default_factory=dict)  # Domain-specific state
timestamp: float = field(default_factory=time.time)

```
def to_dict(self) -> dict:
    return {
        "agent_id": self.agent_id,
        "agent_type": self.agent_type,
        "status": self.status,
        "current_task": self.current_task,
        "capacity": self.capacity,
        "needs": self.needs,
        "offers": self.offers,
        "extras": self.extras,
        "timestamp": self.timestamp,
    }

@classmethod
def from_dict(cls, d: dict) -> Optional["AgentState"]:
    try:
        return cls(**{k: v for k, v in d.items()
                     if k in cls.__dataclass_fields__})
    except Exception:
        return None

@property
def is_available(self) -> bool:
    return self.status in ("IDLE", "ACTIVE") and self.capacity > 0.2

@property
def needs_help(self) -> bool:
    return self.status == "STUCK" or len(self.needs) > 0

def __str__(self) -> str:
    task = f" doing '{self.current_task}'" if self.current_task else ""
    cap = f" cap={self.capacity:.0%}"
    return f"[{self.agent_id}] {self.status}{task}{cap}"
```
