“””
transport.py — Transport Interface

An agent doesn’t care HOW a message arrived.
TCP? LoRa? Written on paper and scanned?
It just cares: Is this intelligible? Is it useful?

Every transport implements the same interface:
send(message, target?)  — push a message out
receive()               — pull next message (non-blocking)
broadcast(message)      — send to everyone listening
listen(callback)        — start receiving in background
close()                 — shut down cleanly

Released CC0.
“””

from abc import ABC, abstractmethod
from typing import Optional, Callable
from .message import Message

class Transport(ABC):
“”“Base transport — all transports implement this.”””

```
@abstractmethod
def send(self, msg: Message, target: str = "") -> bool:
    """Send to a specific target. Returns True if sent."""
    ...

@abstractmethod
def broadcast(self, msg: Message) -> int:
    """Send to all known peers. Returns count of sends."""
    ...

@abstractmethod
def receive(self) -> Optional[Message]:
    """Non-blocking receive. Returns None if nothing waiting."""
    ...

@abstractmethod
def start_listening(self, callback: Callable[[Message], None]) -> None:
    """Start background listener that calls callback on each message."""
    ...

@abstractmethod
def stop_listening(self) -> None:
    """Stop background listener."""
    ...

@abstractmethod
def close(self) -> None:
    """Clean shutdown."""
    ...

@property
@abstractmethod
def transport_name(self) -> str:
    """Human-readable name for logging."""
    ...
```
