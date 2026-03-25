"""
core/transport.py — Abstract transport interface for agent-protocol.

Transports are pluggable: agents don't care how messages arrive.
TCP, UDP, LoRa, file queue, HAM radio — same interface.

To add a transport, subclass Transport and implement all abstract methods.

Released CC0.
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional

from core.message import Message


class Transport(ABC):
    """
    Abstract base class for all transports.

    A transport moves Message objects between agents. It does not
    interpret message content — that is the agent's job.
    """

    @abstractmethod
    def send(self, msg: Message, target: str) -> None:
        """Send a message to a specific agent by ID."""

    @abstractmethod
    def broadcast(self, msg: Message) -> None:
        """Send a message to all reachable agents."""

    @abstractmethod
    def receive(self) -> Optional[Message]:
        """Non-blocking pull. Returns a Message or None."""

    @abstractmethod
    def start_listening(self, callback: Callable[[Message], None]) -> None:
        """Start background receive loop, calling callback for each message."""

    @abstractmethod
    def stop_listening(self) -> None:
        """Stop the background receive loop."""

    @abstractmethod
    def close(self) -> None:
        """Release all resources (sockets, files, threads)."""
