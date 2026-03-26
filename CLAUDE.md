# CLAUDE.md

## Project Overview

**BE2-communication** is an opportunistic agent communication framework with geometric computation pipelines. The repository contains three layers:

1. **Agent Protocol** (core/ + transports/) — a transport-agnostic framework where agents discover each other opportunistically using message verbs (ANNOUNCE, QUERY, STATE, OFFER, REPLY, DONE, STUCK, BYE).
2. **Emergency Mesh Protocol** — phone-to-phone communication via BLE mesh and WiFi Direct when all infrastructure is down. Protocol spec with SOS beacons, location sharing, supply coordination, and TTL-based mesh relay.
3. **Geometric Computation Pipelines** — icosahedral lattice-based signal processing with thermal gating, meta-awareness, and octahedral tensor mapping.
4. **UDP Mesh Protocol** (spec + implementation) — byte-level LAN UDP mesh for agent-to-agent communication with CRC16 integrity.

License: **CC0 — Public Domain**

## Repository Structure

```
BE2-communication/
├── CLAUDE.md                          # This file
├── README.md                          # Agent-protocol documentation
├── LICENSE                            # CC0 1.0 Universal
│
├── core/                              # Agent protocol core
│   ├── __init__.py                    # Package exports (Agent, Message, etc.)
│   ├── agent.py                       # Base Agent class with peer discovery
│   ├── message.py                     # Message dataclass + 8 verb constants + convenience constructors
│   ├── state.py                       # AgentState snapshot (status, capacity, offers, needs)
│   └── transport.py                   # Abstract Transport interface
│
├── transports/                        # Pluggable transport backends (10 transports)
│   ├── __init__.py                    # Package exports
│   ├── local.py                       # LocalHub + LocalTransport (in-process)
│   ├── tcp.py                         # TCPTransport (length-prefixed JSON)
│   ├── udp.py                         # UDPTransport (zero-config LAN broadcast)
│   ├── file_queue.py                  # FileQueueTransport (file-based async)
│   ├── lora.py                        # LoRaTransport (serial + simulator)
│   ├── ham.py                         # HAMTransport (AX.25/KISS + simulator)
│   ├── cb.py                          # CBTransport (CB radio + simulator)
│   ├── ble.py                         # BLETransport (BLE mesh with relay + dedup)
│   ├── wifi_direct.py                 # WiFiDirectTransport (P2P WiFi, no router)
│   └── classic_bt.py                  # ClassicBTTransport (AVRCP/HFP/A2DP accessibility)
│
├── examples/                          # Working demos (8 examples)
│   ├── __init__.py
│   ├── two_agents_local.py            # LocalHub query/reply demo
│   ├── two_agents_tcp.py              # TCP socket query/reply demo
│   ├── mesh_discovery.py              # Dynamic peer discovery + late arrivals
│   ├── async_file_queue.py            # File-based persistent messaging
│   ├── be2_agents.py                  # BE-2 pipeline as communicating agents
│   ├── corridor_relay.py              # Multi-transport corridor relay (CB/LoRa/HAM)
│   ├── emergency_mesh.py             # Emergency phone mesh (BLE + WiFi Direct)
│   └── accessible_emergency.py        # Deaf/HoH accessible alerts (Classic BT)
│
├── icosahedral_lightbridge.py         # Core 6-stage geometric pipeline
├── be2_lightbridge.py                 # BE-2 pipeline with meta-awareness & thermal model
├── octahedral_bridge.py               # Octahedral tensor mapping, dispatcher & FELTSensor
├── udp_mesh_spec.py                   # UDP mesh protocol spec & implementation (CRC16)
└── emergency_mesh_spec.py             # Emergency mesh protocol spec (SOS, relay, CRC16)
```

## Tech Stack

- **Language**: Python 3.9+ (pipeline files use PEP 585 generic type syntax)
- **Dependencies**: Standard library (`math`, `random`, `struct`, `json`, `socket`, `threading`, `queue`, `uuid`, `time`, `pathlib`, `abc`, `dataclasses`, `typing`) plus `numpy` (for `octahedral_bridge.py`)
- **Optional**: `pyserial` for real LoRa/HAM hardware, `bleak` for BLE (simulator fallback included for all)
- **No build system**: No setup.py, pyproject.toml, or requirements.txt
- **No external tooling**: No linter, formatter, or CI/CD configured

## Code Architecture

### core/ — Agent Protocol

Transport-agnostic agent framework. Agents arrive, announce, listen, negotiate.

| Module | Key Classes | Purpose |
|--------|-------------|---------|
| `message.py` | `Message` | Dataclass with verb, sender, body, topic, recipient, msg_id, timestamp. Serializes via `to_bytes()`/`from_bytes()`. Convenience constructors: `Message.announce()`, `.query()`, `.state()`, `.offer()`, `.reply()`, `.done()`, `.stuck()`, `.bye()` |
| `transport.py` | `Transport` (ABC) | Abstract interface: `send()`, `broadcast()`, `receive()`, `start_listening()`, `stop_listening()`, `close()`, `transport_name` |
| `state.py` | `AgentState` | Tracks agent_id, agent_type, status, capacity, offers, needs, extras. Methods: `to_dict()`, `from_dict()`, `is_available`, `needs_help` |
| `agent.py` | `Agent` | Base class with `announce()`, `ask()`, `share_state()`, `offer()`, `reply_to()`, `signal_stuck()`, `signal_done()`, `find_peers()`, `on_message()`. Maintains `peers` dict and `message_log`. Built-in ANNOUNCE/STATE/BYE handling |

### transports/ — Pluggable Backends

| Module | Key Classes | Description |
|--------|-------------|-------------|
| `local.py` | `LocalHub`, `LocalTransport` | Thread-safe in-process queues. For testing and single-machine sims |
| `tcp.py` | `TCPTransport` | Real TCP sockets with 4-byte length-prefixed JSON framing. `add_peer()` to register remote agents |
| `udp.py` | `UDPTransport` | Zero-config LAN broadcast via UDP. Auto-learns peer addresses from incoming messages |
| `file_queue.py` | `FileQueueTransport` | File-based message passing via per-agent inbox dirs. Atomic writes, survives restarts |
| `lora.py` | `LoRaTransport` | LoRa serial radio with chunking/reassembly. Falls back to file-based simulator |
| `ham.py` | `HAMTransport` | AX.25/KISS TNC for amateur radio. KISS framing + chunking. Falls back to simulator |
| `cb.py` | `CBTransport` | CB radio (channel 19). Audio-based with simulator for development |
| `ble.py` | `BLETransport` | Bluetooth Low Energy mesh with relay, dedup, TTL, SOS flags. Falls back to simulator |
| `wifi_direct.py` | `WiFiDirectTransport` | WiFi Direct (P2P) for high-bandwidth phone-to-phone. Falls back to simulator |
| `classic_bt.py` | `ClassicBTTransport` | Classic Bluetooth accessibility — pushes alerts to AVRCP screens, HFP text channel, A2DP haptic patterns |

### classic_bt.py — Classic Bluetooth Accessibility Transport

Repurposes Classic Bluetooth profiles to push emergency alerts to consumer devices deaf and hard-of-hearing users already own — car dashboards, smart speakers, fitness watches, LED speakers, hearing aids.

| Class | Profile | Purpose |
|-------|---------|---------|
| `AVRCPAlert` | AVRCP | Formats alerts as track metadata (title/artist/album) displayed on any Bluetooth screen |
| `HFPChannel` | HFP | Encodes alerts as AT commands on the hands-free text channel |
| `HapticEncoder` | A2DP | Generates PCM audio waveforms that produce recognizable light/vibration patterns on speakers |
| `ClassicBTTransport` | All | Transport ABC implementation that broadcasts across all three profiles simultaneously |

Key methods: `send_sos()` (repeated broadcast with haptic SOS pattern), `send_location()`, `send_supply_alert()`.

### emergency_mesh_spec.py — Emergency Phone Mesh Protocol

Protocol spec for phone-to-phone emergency communication when infrastructure is down.

**Packet layout**: `[Header 22B] + [Payload NB] + [CRC16 2B]`

| Header Field | Offset | Size | Description |
|--------------|--------|------|-------------|
| Magic | 0x00 | 4B | "EM01" |
| Version | 0x04 | 1B | Protocol version (0x01) |
| Message Type | 0x05 | 1B | SOS, LOCATION, STATUS, SUPPLY, TEXT, EVACUATE, etc. |
| Priority | 0x06 | 1B | CRITICAL, HIGH, NORMAL, LOW |
| TTL | 0x07 | 1B | Relay hop limit (max 15) |
| Hop Count | 0x08 | 1B | Incremented on each relay |
| Flags | 0x09 | 1B | NEEDS_ACK, IS_RELAY, HAS_GPS, BATTERY_LOW |
| Sender Hash | 0x0A | 4B | SHA-256 prefix of device ID |
| Timestamp | 0x0E | 4B | Unix epoch |
| Sequence | 0x12 | 2B | Per-sender sequence number |
| Payload Len | 0x14 | 2B | JSON payload size |

Key classes: `EmergencyPacket` (encode/decode), `MeshRelay` (dedup + TTL relay logic).

Message builders: `sos_packet()`, `location_packet()`, `supply_packet()`, `text_packet()`, `evacuate_packet()`, `discover_packet()`.

### icosahedral_lightbridge.py — Core Pipeline

A 6-stage gated pipeline where each stage can halt forward progress:

```
3D vector -> LightBridgeEncoder -> HamiltonianResolver -> HamiltonianValidator
          -> NautilusGrowth -> UrgencyGuard -> SubstrateHandshake
```

| Stage | Purpose |
|-------|---------|
| `LightBridgeEncoder` | Maps 3D vector to nearest icosahedral vertex (4-bit nibble) |
| `HamiltonianResolver` | Disambiguates when input falls between vertices |
| `HamiltonianValidator` | Verifies nibble is a legal edge-walk on the lattice |
| `NautilusGrowth` | Golden-angle-spaced node expansion |
| `UrgencyGuard` | Thermal envelope gating (pressure/temperature limits) |
| `SubstrateHandshake` | Final commit gate; converts nibble to physical torque |

Central data object: `PipelineState` dataclass flows through all stages.

Orchestrator: `GeometricPipeline` class with `step()` and `run()` methods.

### be2_lightbridge.py — Extended Pipeline

Builds on the core pipeline and adds:

| Component | Purpose |
|-----------|---------|
| `WhiteoutSimulator` | Models arctic/polar vortex environmental stress |
| `ThermalModel` | Internal heat accumulation with cooling pulses |
| `MetaAwareness` | Supervisor layer with decision hierarchy: SURVIVAL > IDLE_RECOVERY > CONTINUE |
| `BE2Pipeline` | Governed pipeline with dynamic thermal evolution |

Key behaviors:
- **Recovery mode**: Injects null nibbles for cooling
- **Survival mode**: Redirects all energy to substrate preservation
- **Thermal cycling**: 480C start, +8C/step heat, 40C cooling pulses

### udp_mesh_spec.py — UDP Mesh Protocol

Byte-level LAN UDP protocol for agent communication with CRC16 integrity.

**Packet layout**: `[Header 8B] + [Payload NB] + [CRC16 2B]`

| Header Field | Offset | Size | Description |
|--------------|--------|------|-------------|
| Version | 0x00 | 1B | Protocol version (0x01) |
| Packet Type | 0x01 | 1B | 0x01=QUERY, 0x02=REPLY, 0x03=DISCOVER |
| Sender ID | 0x02 | 2B | Unique 16-bit agent ID |
| Recipient ID | 0x04 | 2B | 0xFFFF = broadcast |
| Payload Length | 0x06 | 2B | Payload size in bytes (max ~512 recommended) |

Key class: `UDPMeshPacket` with `encode()` / `decode()` methods and CRC-16/CCITT-False integrity verification.

### octahedral_bridge.py — Octahedral Tensor Mapping & Sovereign Dispatcher

Maps the 8 stable positions of a diamond cubic unit cell to tensor states via sp3 hybrid orbital projections. Requires `numpy`.

| Class | Purpose |
|-------|---------|
| `OctahedralBridge` | Constructs orbital tensors for 8 unit cell positions; senses state via eigenvalue spectrum and anisotropy |
| `MightyAtomDispatcher` | Finds lowest-entropy paths through the 8x8 transition cost matrix (cost 0-3); supports single and two-hop relays |
| `SovereignDispatcher` | Integrates dispatcher + FELTSensor; halts on high friction or low coherence |
| `FELTSensor` | Phase 6 handshake — monitors felt_level (0.0-2.0) and triggers Micro-Clarification halt when threshold crossed |

Key constant: `TRANSITION_MATRIX` — 8x8 numpy array of transition costs (0=same, 1=direct, 2=relay, 3=avoid).

### Shared Constants

- `PHI` — Golden ratio: `(1 + sqrt(5)) / 2`
- `GOLDEN_ANGLE` — `2*pi*(1 - 1/phi)`
- `ICOSA_ADJ` — Full 12-vertex icosahedron adjacency matrix (5 neighbors each)
- `VERTICES` — 12 icosahedral vertices from `(0, +/-1, +/-phi)` permutations

### Pipeline Status Values

`INIT`, `STABLE`, `HALTED`, `RECALIBRATE`, `HARD_STOP`, `STALL_GROWTH`, `STALLED`, `REJECTED`, `COMMITTED`, `IDLE_RECOVERY`, `SURVIVAL`

## Running the Code

Pipeline modules are self-contained with inline tests:

```bash
python icosahedral_lightbridge.py   # Core pipeline tests
python be2_lightbridge.py           # BE-2 governed pipeline tests
python udp_mesh_spec.py             # UDP mesh round-trip & integrity tests
python octahedral_bridge.py         # Tensor mapping, dispatcher & FELTSensor tests
python emergency_mesh_spec.py       # Emergency mesh protocol tests
```

Agent protocol examples (run from repo root):

```bash
python -m examples.two_agents_local   # LocalHub query/reply demo
python -m examples.two_agents_tcp     # TCP socket query/reply demo
python -m examples.mesh_discovery     # Dynamic peer discovery
python -m examples.async_file_queue   # File-based persistent messaging
python -m examples.be2_agents         # BE-2 pipeline as agents
python -m examples.corridor_relay     # Multi-transport corridor relay
python -m examples.emergency_mesh     # Emergency phone mesh (BLE + WiFi Direct)
python -m examples.accessible_emergency  # Deaf/HoH accessible alerts (Classic BT)
```

Note: `octahedral_bridge.py` requires `numpy` (`pip install numpy`).

There is no test framework (pytest/unittest). Tests run via `if __name__ == "__main__":` blocks.

## Development Conventions

- **Gate pattern**: Each pipeline stage can halt processing; energy only flows forward on STABLE/PROCEED status.
- **Nibble encoding**: Vertex indices are stored as 4-bit values (0-11).
- **Dataclass state propagation**: A single `PipelineState` object is mutated and passed through all stages.
- **Message-based protocol**: Agents communicate via `Message` objects with standard verbs.
- **Transport-agnostic**: Agent logic never depends on transport implementation.
- **Graceful degradation**: Malformed messages get ignored, not crashed on. Silent agents get worked around, not waited on.
- **Stage naming**: Lowercase with underscores in code, PascalCase for class names.
- **Standard-library preference**: Keep core and transports stdlib-only. `numpy` allowed for physics modules. `pyserial` optional for radio transports.
- **CC0 license**: All contributions are public domain.

## Git Workflow

- **Main branch**: `master` (remote tracks as `main`)
- **Feature branches**: `claude/<description>` pattern
- **Commit style**: Short descriptive messages (e.g., "Create icosahedral_lightbridge.py")
