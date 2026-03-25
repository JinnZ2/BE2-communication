"""
be2_agents.py — BE-2 Pipeline as Communicating Agents

Maps the geometric computation pipeline onto the agent protocol:
- EncoderAgent:   receives 3D vectors, emits nibbles
- ValidatorAgent: receives nibbles, validates lattice walk
- GrowthAgent:    receives valid nibbles, expands φ-spiral
- MetaAgent:      monitors all agents, intervenes on stress

Each agent is autonomous. They discover each other, negotiate,
and hand off work through messages — not function calls.

Run: python examples/be2_agents.py
"""

import sys
import os
import math
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import Agent, Message, AgentState
from transports import LocalHub, LocalTransport

# ── Constants ──────────────────────────────────

PHI = (1 + 5**0.5) / 2
GOLDEN_ANGLE = 2 * math.pi * (1 - 1 / PHI)

ICOSA_ADJ = {
    0:  [1, 5, 4, 8, 11],  1:  [0, 2, 5, 6, 11],
    2:  [1, 3, 6, 7, 11],  3:  [2, 4, 7, 8, 11],
    4:  [0, 3, 8, 9, 5],   5:  [0, 1, 4, 9, 10],
    6:  [1, 2, 10, 7, 5],  7:  [2, 3, 6, 8, 10],
    8:  [0, 3, 4, 7, 9],   9:  [4, 5, 8, 10, 11],
    10: [5, 6, 7, 9, 11],  11: [1, 2, 3, 9, 10],
}

def icosahedron_vertices():
    verts = []
    for s1 in (-1, 1):
        for s2 in (-PHI, PHI):
            verts.append((0.0, float(s1), float(s2)))
            verts.append((float(s2), 0.0, float(s1)))
            verts.append((float(s1), float(s2), 0.0))
    return verts

VERTICES = icosahedron_vertices()

# ── Encoder Agent ──────────────────────────────

class EncoderAgent(Agent):
    """Receives 3D vectors, finds nearest icosahedral vertex, emits nibble."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_vertex = None
        self.entropy_threshold = 1.5

    def on_message(self, msg: Message):
        if msg.verb == "QUERY" and msg.topic == "encode":
            vector = msg.body
            result = self._encode(vector)
            self.reply_to(msg, result)

            if result["status"] == "STABLE":
                # Forward to validator
                self.ask(
                    result["nibble"],
                    topic="validate",
                    recipient="validator_01",
                )

    def _encode(self, vector):
        best_dist, best_idx = float('inf'), 0
        for i, v in enumerate(VERTICES):
            d = math.dist(vector, v)
            if d < best_dist:
                best_dist, best_idx = d, i

        if self.last_vertex is not None:
            entropy = math.dist(VERTICES[self.last_vertex], VERTICES[best_idx])
            if entropy > self.entropy_threshold:
                return {"status": "HALTED", "reason": "entropy_exceeded"}

        self.last_vertex = best_idx
        return {
            "status": "STABLE",
            "vertex": best_idx,
            "nibble": format(best_idx, '04b'),
        }

# ── Validator Agent ────────────────────────────

class ValidatorAgent(Agent):
    """Receives nibbles, validates against icosahedral edge-walk."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_pos = 0

    def on_message(self, msg: Message):
        if msg.verb == "QUERY" and msg.topic == "validate":
            nibble = msg.body
            result = self._validate(nibble)
            self.reply_to(msg, result)

            if result["status"] == "STABLE":
                # Forward to growth
                self.ask(
                    result,
                    topic="grow",
                    recipient="growth_01",
                )
            else:
                # Signal recalibration needed
                self.signal_stuck(
                    f"Dark fringe at position {self.current_pos}",
                    topic="recalibrate",
                )

    def _validate(self, nibble):
        if len(nibble) != 4:
            return {"status": "ERROR", "reason": "invalid_nibble_length"}

        if nibble[2] == "0":
            return {"status": "RECALIBRATE", "position": self.current_pos}

        neighbor_idx = int(nibble[:2], 2) % len(ICOSA_ADJ[self.current_pos])
        next_pos = ICOSA_ADJ[self.current_pos][neighbor_idx]
        self.current_pos = next_pos
        return {
            "status": "STABLE",
            "position": next_pos,
            "nibble": format(next_pos, '04b'),
        }

# ── Growth Agent ───────────────────────────────

class GrowthAgent(Agent):
    """Expands nodes in φ-distributed spiral."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.node_count = 0

    def on_message(self, msg: Message):
        if msg.verb == "QUERY" and msg.topic == "grow":
            self.node_count += 1
            r = math.sqrt(self.node_count)
            theta = self.node_count * GOLDEN_ANGLE
            x, y = r * math.cos(theta), r * math.sin(theta)

            result = {
                "node": self.node_count,
                "position": (round(x, 4), round(y, 4)),
            }
            self.reply_to(msg, result)
            self.signal_done(f"Node {self.node_count} placed")

            # Report to meta
            self.state.current_task = f"node_{self.node_count}"
            self.state.capacity = max(0.0, 1.0 - self.node_count * 0.05)
            self.share_state()

# ── Meta Agent ─────────────────────────────────

class MetaAgent(Agent):
    """Monitors all agents, intervenes on stress."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.interventions = []

    def on_message(self, msg: Message):
        # Watch for stuck signals
        if msg.verb == "STUCK":
            intervention = {
                "time": time.time(),
                "agent": msg.sender,
                "problem": msg.body,
                "action": "IDLE_RECOVERY",
            }
            self.interventions.append(intervention)
            print(f"  [META] Intervention: {msg.sender} → IDLE_RECOVERY")

            # Tell the stuck agent to recalibrate
            self.reply_to(msg, {"action": "RECALIBRATE", "wait_cycles": 2})

        # Watch for capacity drops
        if msg.verb == "STATE":
            if isinstance(msg.body, dict):
                cap = msg.body.get("capacity", 1.0)
                if cap < 0.3:
                    print(f"  [META] Warning: {msg.sender} capacity at {cap:.0%}")
                    self.offer(
                        "thermal_pause",
                        topic="governance",
                        recipient=msg.sender,
                    )

# ── Main Simulation ────────────────────────────

def main():
    hub = LocalHub()

    encoder = EncoderAgent(
        "encoder_01", "LightBridgeEncoder",
        LocalTransport("encoder_01", hub),
        capabilities=["geometric_encoding"],
    )
    validator = ValidatorAgent(
        "validator_01", "HamiltonianValidator",
        LocalTransport("validator_01", hub),
        capabilities=["lattice_validation"],
    )
    growth = GrowthAgent(
        "growth_01", "NautilusGrowth",
        LocalTransport("growth_01", hub),
        capabilities=["phi_expansion"],
    )
    meta = MetaAgent(
        "meta_01", "MetaAwareness",
        LocalTransport("meta_01", hub),
        capabilities=["governance", "thermal_management"],
    )

    agents = [encoder, validator, growth, meta]

    print("=" * 60)
    print("BE-2 AGENT NETWORK")
    print("=" * 60)

    # Start all agents
    for a in agents:
        a.start()
    time.sleep(0.3)

    print(f"\n── Peer discovery ──")
    for a in agents:
        peers = [p for p in a.peers.keys()]
        print(f"  {a.id}: knows {peers}")

    # Feed vectors through the pipeline via messages
    test_vectors = [
        (-1.0, -1.6, 0.0),     # → vertex 2, nibble=0010, bit2=1
        (0.0, -1.0, 1.6),      # → vertex 3, nibble=0011, bit2=1
        (0.0, 1.0, -1.6),      # → vertex 6, nibble=0110, bit2=1
        (-1.6, 0.0, 1.0),      # → vertex 7, nibble=0111, bit2=1
        (1.6, 0.0, 1.0),       # → vertex 10, nibble=1010, bit2=1
        (1.0, 1.6, 0.0),       # → vertex 11, nibble=1011, bit2=1
        (-1.0, -1.5, 0.1),     # near vertex 2
        (0.1, -0.9, 1.7),      # near vertex 3
    ]

    print(f"\n── Processing {len(test_vectors)} vectors ──")
    # Create an external "source" agent to feed vectors
    source = Agent(
        "source_01", "VectorSource",
        LocalTransport("source_01", hub),
    )
    source.start()
    time.sleep(0.1)

    for i, v in enumerate(test_vectors):
        source.ask(v, topic="encode", recipient="encoder_01")

    # Let the pipeline drain
    time.sleep(1.0)

    print(f"\n── Growth agent state ──")
    print(f"  Nodes placed: {growth.node_count}")
    print(f"  Capacity: {growth.state.capacity:.0%}")

    print(f"\n── Meta interventions ──")
    if meta.interventions:
        for iv in meta.interventions:
            print(f"  {iv['agent']}: {iv['action']} — {iv['problem']}")
    else:
        print("  None (clean run)")

    print(f"\n── Message counts ──")
    for a in agents:
        print(f"  {a.id}: {len(a.message_log)} messages")

    # Shutdown
    print(f"\n── Shutting down ──")
    source.stop()
    for a in agents:
        a.stop()
    print("  Done.")

if __name__ == "__main__":
    main()
