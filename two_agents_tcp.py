“””
two_agents_tcp.py — Two agents over TCP

Same interaction as the local example, but over real TCP sockets.
Each agent listens on its own port.

Run: python examples/two_agents_tcp.py
“””

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(**file**))))

from core import Agent, Message
from transports import TCPTransport

class EncoderAgent(Agent):
def on_message(self, msg: Message):
if msg.verb == “QUERY”:
self.reply_to(msg, {“answer”: “12 vertices on the icosahedron”})

class ValidatorAgent(Agent):
def on_message(self, msg: Message):
if msg.verb == “REPLY”:
print(f”  [{self.id}] Got answer: {msg.body}”)

def main():
# Each agent gets its own port
t_enc = TCPTransport(host=“127.0.0.1”, port=9200)
t_val = TCPTransport(host=“127.0.0.1”, port=9201)

```
# Tell each transport where the other lives
t_enc.add_peer("validator_01", "127.0.0.1", 9201)
t_val.add_peer("encoder_01", "127.0.0.1", 9200)

encoder = EncoderAgent(
    agent_id="encoder_01",
    agent_type="LightBridgeEncoder",
    transport=t_enc,
    capabilities=["geometric_encoding"],
)

validator = ValidatorAgent(
    agent_id="validator_01",
    agent_type="HamiltonianValidator",
    transport=t_val,
    capabilities=["lattice_validation"],
)

print("=" * 55)
print("TWO AGENTS — TCP TRANSPORT")
print("=" * 55)

encoder.start()
validator.start()
time.sleep(0.5)

print(f"\n── Peer discovery ──")
print(f"  Encoder knows: {list(encoder.peers.keys())}")
print(f"  Validator knows: {list(validator.peers.keys())}")

print(f"\n── Validator asks encoder ──")
validator.ask(
    "How many vertices?",
    topic="geometry",
    recipient="encoder_01",
)
time.sleep(0.5)

print(f"\n── Shutting down ──")
encoder.stop()
validator.stop()
print("  Done.")
```

if **name** == “**main**”:
main()
