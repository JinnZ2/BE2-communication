"""
examples/two_agents_local.py — Two agents communicating via LocalHub.

Demonstrates opportunistic discovery and query/reply flow using
in-process transport. No network required.

Usage:
    python -m examples.two_agents_local

Released CC0.
"""

import sys
import time

sys.path.insert(0, ".")

from core import Agent, Message
from transports import LocalHub, LocalTransport


class MathAgent(Agent):
    """An agent that answers math questions."""

    def on_message(self, msg: Message):
        if msg.verb == "QUERY":
            question = msg.payload.get("question", "")
            print(f"  [{self.agent_id}] received QUERY: {question!r}")
            self.reply_to(msg, {"answer": "42"})
            print(f"  [{self.agent_id}] sent REPLY: 42")


class CuriousAgent(Agent):
    """An agent that asks questions and prints replies."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.replies = []

    def on_message(self, msg: Message):
        if msg.verb == "ANNOUNCE":
            caps = msg.payload.get("capabilities", [])
            print(f"  [{self.agent_id}] discovered {msg.sender} "
                  f"with capabilities: {caps}")

        elif msg.verb == "REPLY":
            answer = msg.payload.get("answer")
            self.replies.append(answer)
            print(f"  [{self.agent_id}] received REPLY: {answer}")


def main():
    print("=== Two Agents — LocalHub Demo ===\n")

    # Create a shared hub
    hub = LocalHub()

    # Create two agents
    math_t = LocalTransport("math_agent", hub)
    curious_t = LocalTransport("curious_agent", hub)

    math = MathAgent("math_agent", transport=math_t, capabilities=["math"])
    curious = CuriousAgent("curious_agent", transport=curious_t)

    # Start both agents (each announces itself)
    print("Starting agents...")
    math.start()
    curious.start()

    # Let announcements propagate
    time.sleep(0.3)

    # Curious agent asks a question
    print("\nCurious agent asks: 'What is the answer?'")
    curious.ask("What is the answer?", recipient="math_agent")

    # Wait for reply
    time.sleep(0.3)

    # Verify
    print(f"\nReplies collected: {curious.replies}")
    assert curious.replies == ["42"], f"Expected ['42'], got {curious.replies}"
    assert "math_agent" in curious.state.known_peers
    assert "curious_agent" in math.state.known_peers
    print("PASS: Query/Reply round-trip succeeded")

    # Clean shutdown
    math.stop()
    curious.stop()
    print("\n=== Demo complete ===")


if __name__ == "__main__":
    main()
