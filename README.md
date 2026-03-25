# BE2-communication
Agent communication


# agent-protocol

Opportunistic agent communication framework. No permission gates, no central registry. Agents arrive, announce themselves, listen for what's available, and negotiate on the fly.

## Principles

1. **No permission required** — agents show up and talk. No handshake ceremony, no approval flow.
2. **Opportunistic discovery** — you know who you've met, that's it. No global directory.
3. **Transport-agnostic** — agents don't care how messages arrive. TCP, UDP, LoRa, file queue, HAM radio — same protocol.
4. **Graceful degradation** — malformed messages get ignored, not crashed on. Silent agents get worked around, not waited on.
5. **Human-readable** — messages are plaintext-parseable. You can debug by reading the wire.

## Architecture

```
┌──────────────────────────────────────────┐
│              Agent                        │
│  announce() → "I'm here, I do X"         │
│  ask()      → "Do you know about Y?"     │
│  share()    → "Here's where I am"        │
│  offer()    → "I have Z if you need it"  │
│  stuck()    → "I need help with W"       │
│  on_message() → override to respond      │
├──────────────────────────────────────────┤
│          Transport (pluggable)            │
│  LocalHub  │  TCP  │  FileQueue  │  ...   │
└──────────────────────────────────────────┘
```

## Message Verbs

| Verb | Meaning |
|------|---------|
| `ANNOUNCE` | I'm here, this is what I do |
| `QUERY` | Do you know about X? |
| `STATE` | Here's where I am right now |
| `OFFER` | I have X if you need it |
| `REPLY` | Here's what you asked about |
| `DONE` | I finished X |
| `STUCK` | I need help with X |
| `BYE` | I'm leaving |

## Quick Start

```python
from core import Agent, Message
from transports import LocalHub, LocalTransport

# Create a shared hub (in-process)
hub = LocalHub()

# Create two agents
class MyAgent(Agent):
    def on_message(self, msg):
        if msg.verb == "QUERY":
            self.reply_to(msg, {"answer": "42"})

a = MyAgent("agent_a", transport=LocalTransport("agent_a", hub),
            capabilities=["math"])
b = Agent("agent_b", transport=LocalTransport("agent_b", hub))

a.start()
b.start()

# b asks, a answers
b.ask("What is the answer?", recipient="agent_a")
```

## Transports

### LocalHub (in-process)
Thread-safe queues, no network. For testing and single-machine sims.

### TCP
Real sockets, length-prefixed framing. For LAN or same-machine multi-process.

```python
from transports import TCPTransport

t = TCPTransport(host="127.0.0.1", port=9100)
t.add_peer("other_agent", "127.0.0.1", 9101)
```

### FileQueue (async)
File-based message passing. Works across processes, survives restarts. For intermittent connectivity, truck-stop-to-base sync.

```python
from transports import FileQueueTransport

t = FileQueueTransport("my_agent", "/shared/queue_dir")
```

### Adding a Transport
Implement `core.Transport`:
- `send(msg, target)` — direct send
- `broadcast(msg)` — send to all
- `receive()` — non-blocking pull
- `start_listening(callback)` — background receive
- `stop_listening()` / `close()` — cleanup

## Repo Structure

```
BE2-communication/
├── core/                              # Agent protocol core
│   ├── __init__.py                    # Package exports (Agent, Message, etc.)
│   ├── agent.py                       # Base Agent class
│   ├── message.py                     # Message dataclass + verb constants
│   ├── state.py                       # AgentState snapshot
│   └── transport.py                   # Abstract Transport interface
├── transports/                        # Pluggable transport backends
│   ├── __init__.py                    # Package exports
│   ├── local.py                       # LocalHub + LocalTransport (in-process)
│   ├── tcp.py                         # TCPTransport (length-prefixed JSON)
│   └── file_queue.py                  # FileQueueTransport (file-based async)
├── examples/                          # Working demos
│   ├── __init__.py
│   ├── two_agents_local.py            # LocalHub query/reply demo
│   └── two_agents_tcp.py              # TCP socket query/reply demo
├── icosahedral_lightbridge.py         # Core 6-stage geometric pipeline
├── be2_lightbridge.py                 # BE-2 pipeline with meta-awareness & thermal model
├── octahedral_bridge.py               # Octahedral tensor mapping & sovereign dispatcher
├── udp_mesh_spec.py                   # UDP mesh protocol spec & implementation (CRC16)
├── CLAUDE.md                          # Project architecture guide
├── README.md                          # This file
└── LICENSE                            # CC0 1.0 Universal
```

## License

CC0 — Public Domain.
