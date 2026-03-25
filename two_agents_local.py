“””
two_agents_local.py — Two agents meet and talk

Demonstrates the full lifecycle:
1. Both agents start (announce themselves)
2. They discover each other automatically
3. Agent A asks a question
4. Agent B answers
5. Both shut down cleanly

No network required — uses in-process LocalHub.

Run: python -m examples.two_agents_local
or: python examples/two_agents_local.py
“””

import sys
import os
import time

# Handle running from repo root or examples dir

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(**file**))))

from core import Agent, Message
from transports import LocalHub, LocalTransport

# ── Custom Agents ──────────────────────────────

class EncoderAgent(Agent):
“”“Knows about geometric encoding.”””

```
def on_message(self, msg: Message):
    if msg.verb == "QUERY" and "vertex" in str(msg.body).lower():
        self.reply_to(msg, {
            "answer": "12 vertices, 30 edges, 20 faces",
            "source": "icosahedral geometry"
        })
```

class ValidatorAgent(Agent):
“”“Knows about lattice validation.”””

```
def on_message(self, msg: Message):
    if msg.verb == "QUERY" and "adjacen" in str(msg.body).lower():
        self.reply_to(msg, {
            "answer": "Each vertex has exactly 5 neighbors",
            "source": "ICOSA_ADJ lookup"
        })
    elif msg.verb == "REPLY":
        print(f"  [{self.id}] Got answer: {msg.body}")
```

# ── Run ────────────────────────────────────────

def main():
hub = LocalHub()

```
encoder = EncoderAgent(
    agent_id="encoder_01",
    agent_type="LightBridgeEncoder",
    transport=LocalTransport("encoder_01", hub),
    capabilities=["geometric_encoding", "vertex_mapping"],
)

validator = ValidatorAgent(
    agent_id="validator_01",
    agent_type="HamiltonianValidator",
    transport=LocalTransport("validator_01", hub),
    capabilities=["lattice_validation", "adjacency_check"],
)

print("=" * 55)
print("TWO AGENTS — LOCAL HUB")
print("=" * 55)

# 1. Start both agents (they announce automatically)
print("\n── Starting agents ──")
encoder.start()
validator.start()
time.sleep(0.3)  # let announcements propagate

# 2. Check peer discovery
print(f"\n── Peer discovery ──")
print(f"  Encoder knows: {list(encoder.peers.keys())}")
print(f"  Validator knows: {list(validator.peers.keys())}")

# 3. Validator asks Encoder a question
print(f"\n── Validator asks about vertices ──")
validator.ask(
    "How many vertices does the icosahedron have?",
    topic="geometry",
    recipient="encoder_01",
)
time.sleep(0.3)

# 4. Encoder asks Validator a question
print(f"\n── Encoder asks about adjacency ──")
encoder.ask(
    "What's the adjacency count per vertex?",
    topic="lattice",
    recipient="validator_01",
)
time.sleep(0.3)

# 5. Share state
print(f"\n── State sharing ──")
encoder.state.status = "ACTIVE"
encoder.state.current_task = "encoding vector stream"
encoder.state.capacity = 0.7
encoder.share_state()
time.sleep(0.2)

# Check validator saw encoder's state
if "encoder_01" in validator.peers:
    peer = validator.peers["encoder_01"]
    print(f"  Validator sees encoder: {peer}")

# 6. Signal stuck
print(f"\n── Encoder gets stuck ──")
encoder.signal_stuck(
    "Vector falls between two vertices, need disambiguation",
    topic="resolver",
)
time.sleep(0.2)

# 7. Find help
print(f"\n── Validator looks for help ──")
helpers = validator.find_peers(capability="geometric_encoding")
for h in helpers:
    print(f"  Found: {h}")

# 8. Message log
print(f"\n── Message log (encoder) ──")
for msg in encoder.message_log[-5:]:
    print(f"  {msg}")

# 9. Shutdown
print(f"\n── Shutting down ──")
encoder.stop()
validator.stop()
print("  Done.")
```

if **name** == “**main**”:
main()
