"""
examples/two_agents_tcp.py — Two agents communicating via TCP sockets.

Demonstrates agent communication over real TCP connections with
length-prefixed JSON framing. Both agents run on localhost.

Usage:
    python -m examples.two_agents_tcp

Released CC0.
"""

import sys
import time

sys.path.insert(0, ".")

from core import Agent, Message
from transports import TCPTransport


class ResponderAgent(Agent):
    """Responds to queries with a greeting."""

    def on_message(self, msg: Message):
        if msg.verb == "QUERY":
            question = msg.payload.get("question", "")
            print(f"  [{self.agent_id}] received QUERY: {question!r}")
            self.reply_to(msg, {"greeting": f"Hello from {self.agent_id}!"})
            print(f"  [{self.agent_id}] sent REPLY")


class RequesterAgent(Agent):
    """Sends a query and collects replies."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.replies = []

    def on_message(self, msg: Message):
        if msg.verb == "REPLY":
            greeting = msg.payload.get("greeting", "")
            self.replies.append(greeting)
            print(f"  [{self.agent_id}] received REPLY: {greeting!r}")


def main():
    print("=== Two Agents — TCP Demo ===\n")

    # Set up TCP transports on different ports
    port_a = 19100
    port_b = 19101

    transport_a = TCPTransport(host="127.0.0.1", port=port_a)
    transport_b = TCPTransport(host="127.0.0.1", port=port_b)

    # Each agent knows the other's address
    transport_a.add_peer("requester", "127.0.0.1", port_b)
    transport_b.add_peer("responder", "127.0.0.1", port_a)

    responder = ResponderAgent("responder", transport=transport_a,
                               capabilities=["greeting"])
    requester = RequesterAgent("requester", transport=transport_b)

    # Start listening
    print("Starting agents on TCP ports...")
    responder.start()
    requester.start()
    time.sleep(0.3)

    # Requester sends a query
    print("\nRequester asks: 'Who are you?'")
    requester.ask("Who are you?", recipient="responder")

    # Wait for TCP round-trip
    time.sleep(0.5)

    # Verify
    print(f"\nReplies collected: {requester.replies}")
    assert len(requester.replies) == 1
    assert "Hello from responder!" in requester.replies[0]
    print("PASS: TCP query/reply round-trip succeeded")

    # Clean shutdown
    responder.stop()
    requester.stop()
    print("\n=== Demo complete ===")


if __name__ == "__main__":
    main()
