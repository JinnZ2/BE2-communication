“””
agent.py — Base Agent

An agent shows up, announces itself, listens for what’s available,
and negotiates on the fly. No permission gates, no central registry.

Lifecycle:
1. Create agent with a transport
2. agent.start()  → announces presence, starts listening
3. agent.ask()    → fire a question (don’t block waiting)
4. agent.share()  → publish your current state
5. agent.stop()   → say goodbye, shut down

Agents maintain a local directory of peers they’ve heard from.
No central registry. You know who you’ve met, that’s it.

Override on_message() to define how your agent responds to
incoming messages. The base implementation handles:
- ANNOUNCE → add to peer directory
- QUERY    → pass to on_query() (override this)
- STATE    → update peer state cache
- BYE      → remove from peer directory

Released CC0.
“””

import time
import threading
from typing import Optional, Callable, Any
from .message import Message
from .state import AgentState
from .transport import Transport

class Agent:
def **init**(self, agent_id: str, agent_type: str = “”,
transport: Optional[Transport] = None,
capabilities: Optional[list[str]] = None):
self.id = agent_id
self.agent_type = agent_type
self.transport = transport
self.capabilities = capabilities or []

```
    # Internal state
    self.state = AgentState(
        agent_id=agent_id,
        agent_type=agent_type,
        offers=self.capabilities,
    )

    # Peer directory — who have we met?
    # { agent_id: AgentState }
    self.peers: dict[str, AgentState] = {}

    # Message log (bounded ring buffer)
    self._log: list[Message] = []
    self._log_max = 500

    # Callbacks for specific verbs
    self._handlers: dict[str, list[Callable[[Message], None]]] = {}

    self._running = False

# ── Lifecycle ──────────────────────────────

def start(self):
    """Announce presence and start listening."""
    self._running = True
    if self.transport:
        self.transport.start_listening(self._on_raw_message)
        self.announce()

def stop(self):
    """Say goodbye and shut down."""
    self._running = False
    if self.transport:
        self.transport.broadcast(Message.bye(self.id))
        self.transport.stop_listening()
        self.transport.close()

# ── Sending ────────────────────────────────

def announce(self):
    """Broadcast: I'm here, this is what I do."""
    msg = Message.announce(self.id, self.capabilities)
    self._send_broadcast(msg)

def ask(self, question: str, topic: str = "",
        recipient: str = "") -> Message:
    """
    Fire a question. Don't wait for response.
    Returns the sent message (use msg_id to match replies).
    """
    msg = Message.query(self.id, question, topic=topic,
                        recipient=recipient)
    if recipient:
        self._send_direct(msg, recipient)
    else:
        self._send_broadcast(msg)
    return msg

def share_state(self):
    """Publish current state snapshot to everyone."""
    self.state.timestamp = time.time()
    msg = Message.state(self.id, self.state.to_dict())
    self._send_broadcast(msg)

def offer(self, what: str, topic: str = "",
          recipient: str = ""):
    """Announce you have something available."""
    msg = Message.offer(self.id, what, topic=topic,
                        recipient=recipient)
    if recipient:
        self._send_direct(msg, recipient)
    else:
        self._send_broadcast(msg)

def reply_to(self, original: Message, body: Any):
    """Respond to a specific message."""
    msg = Message.reply(self.id, body, original)
    self._send_direct(msg, original.sender)

def signal_stuck(self, problem: str, topic: str = ""):
    """Broadcast that you need help."""
    self.state.status = "STUCK"
    msg = Message.stuck(self.id, problem, topic=topic)
    self._send_broadcast(msg)

def signal_done(self, what: str):
    """Broadcast task completion."""
    msg = Message.done(self.id, what)
    self._send_broadcast(msg)

# ── Receiving / Dispatch ───────────────────

def _on_raw_message(self, msg: Message):
    """Central dispatcher — routes incoming messages."""
    if not msg or not self._running:
        return

    # Don't process own messages
    if msg.sender == self.id:
        return

    # If addressed to someone else, ignore
    if msg.recipient and msg.recipient != self.id:
        return

    # Log it
    self._log_message(msg)

    # Built-in handling
    self._handle_builtin(msg)

    # Custom handlers
    for handler in self._handlers.get(msg.verb, []):
        try:
            handler(msg)
        except Exception:
            pass  # graceful degradation

    # Override point
    self.on_message(msg)

def _handle_builtin(self, msg: Message):
    """Default handling for core verbs."""
    if msg.verb == "ANNOUNCE":
        # Someone showed up — add to peer directory
        caps = []
        if isinstance(msg.body, dict):
            caps = msg.body.get("capabilities", [])
        self.peers[msg.sender] = AgentState(
            agent_id=msg.sender,
            offers=caps,
            status="ACTIVE",
            timestamp=msg.timestamp,
        )

    elif msg.verb == "STATE":
        # Peer state update
        if isinstance(msg.body, dict):
            peer_state = AgentState.from_dict(msg.body)
            if peer_state:
                self.peers[msg.sender] = peer_state

    elif msg.verb == "BYE":
        # Peer leaving
        if msg.sender in self.peers:
            self.peers[msg.sender].status = "OFFLINE"

# ── Override Points ────────────────────────

def on_message(self, msg: Message):
    """
    Override this to define agent behavior.
    Called for every incoming message after built-in handling.
    """
    pass

def on_query(self, msg: Message) -> Optional[Any]:
    """
    Override to answer queries.
    Return value (if any) is sent back as a REPLY.
    """
    return None

# ── Handler Registration ───────────────────

def on(self, verb: str, handler: Callable[[Message], None]):
    """Register a callback for a specific verb."""
    verb = verb.upper()
    if verb not in self._handlers:
        self._handlers[verb] = []
    self._handlers[verb].append(handler)

# ── Peer Discovery ─────────────────────────

def find_peers(self, capability: str = "",
               status: str = "") -> list[AgentState]:
    """Find peers matching criteria."""
    results = []
    for peer in self.peers.values():
        if capability and capability not in peer.offers:
            continue
        if status and peer.status != status:
            continue
        results.append(peer)
    return results

def find_help(self, need: str) -> list[AgentState]:
    """Find peers that offer what you need."""
    return self.find_peers(capability=need, status="ACTIVE")

# ── Internal ───────────────────────────────

def _send_broadcast(self, msg: Message):
    if self.transport:
        self.transport.broadcast(msg)
    self._log_message(msg)

def _send_direct(self, msg: Message, target: str):
    if self.transport:
        self.transport.send(msg, target)
    self._log_message(msg)

def _log_message(self, msg: Message):
    self._log.append(msg)
    if len(self._log) > self._log_max:
        self._log = self._log[-self._log_max:]

@property
def message_log(self) -> list[Message]:
    return list(self._log)

def __str__(self) -> str:
    peers = len([p for p in self.peers.values()
                 if p.status != "OFFLINE"])
    return (f"Agent({self.id}, type={self.agent_type}, "
            f"peers={peers}, status={self.state.status})")
```
