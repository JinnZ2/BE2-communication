"""
core/state.py — Agent state snapshot for agent-protocol.

Each agent maintains a lightweight state object that tracks identity,
capabilities, known peers, and current operational status. This state
can be shared with other agents via the STATE verb.

Released CC0.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set


@dataclass
class AgentState:
    """
    Snapshot of an agent's current state.

    Attributes:
        agent_id:       Unique identifier for the agent.
        capabilities:   List of capability strings this agent advertises.
        known_peers:    Set of agent IDs this agent has encountered.
        status:         Current operational status (ACTIVE, IDLE, STUCK, GONE).
        last_active:    Unix timestamp of last activity.
        metadata:       Freeform dict for transport-specific or app-specific data.
    """
    agent_id: str
    capabilities: List[str] = field(default_factory=list)
    known_peers: Set[str] = field(default_factory=set)
    status: str = "IDLE"
    last_active: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def touch(self):
        """Update last_active to now."""
        self.last_active = time.time()

    def add_peer(self, peer_id: str):
        """Record a newly discovered peer."""
        self.known_peers.add(peer_id)

    def to_dict(self) -> dict:
        """Serialize state for transmission via STATE verb."""
        return {
            "agent_id": self.agent_id,
            "capabilities": self.capabilities,
            "known_peers": sorted(self.known_peers),
            "status": self.status,
            "last_active": self.last_active,
            "metadata": self.metadata,
        }
