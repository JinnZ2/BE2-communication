# CLAUDE.md

## Project Overview

**BE2-communication** is an opportunistic agent communication framework with geometric computation pipelines. The repository contains two main components:

1. **Agent Protocol** (documented in README, not yet implemented) — a transport-agnostic framework where agents discover each other opportunistically using message verbs (ANNOUNCE, QUERY, STATE, OFFER, REPLY, DONE, STUCK, BYE).
2. **Geometric Computation Pipelines** (implemented) — icosahedral lattice-based signal processing pipelines with thermal gating and meta-awareness.
3. **UDP Mesh Protocol** (spec + implementation) — byte-level LAN UDP mesh for agent-to-agent communication with CRC16 integrity.

License: **CC0 — Public Domain**

## Repository Structure

```
BE2-communication/
├── CLAUDE.md                      # This file
├── README.md                      # Agent-protocol documentation
├── LICENSE                        # CC0 1.0 Universal
├── be2_lightbridge.py             # Full BE-2 pipeline with meta-awareness & thermal model
├── icosahedral_lightbridge.py     # Core 6-stage geometric pipeline
├── octahedral_bridge.py           # Octahedral tensor mapping, dispatcher & FELTSensor
└── udp_mesh_spec.py               # UDP mesh protocol spec & implementation (CRC16)
```

The README describes a planned `core/`, `transports/`, and `examples/` directory structure that is **not yet implemented**.

## Tech Stack

- **Language**: Python (3.7+ required for dataclasses)
- **Dependencies**: Standard library (`math`, `random`, `struct`, `json`, `dataclasses`, `typing`) plus `numpy` (for `octahedral_bridge.py`)
- **No build system**: No setup.py, pyproject.toml, or requirements.txt
- **No external tooling**: No linter, formatter, or CI/CD configured

## Code Architecture

### icosahedral_lightbridge.py — Core Pipeline

A 6-stage gated pipeline where each stage can halt forward progress:

```
3D vector → LightBridgeEncoder → HamiltonianResolver → HamiltonianValidator
         → NautilusGrowth → UrgencyGuard → SubstrateHandshake
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

Payload is JSON-encoded UTF-8. Supports optional SHELL/ENERGY extension messages for growth/exploration signaling.

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

`INIT`, `STABLE`, `HALTED`, `RECALIBRATE`, `HARD_STOP`, `STALL_GROWTH`, `REJECTED`, `COMMITTED`, `IDLE_RECOVERY`, `SURVIVAL`

## Running the Code

All files are self-contained with inline tests:

```bash
python icosahedral_lightbridge.py   # Runs core pipeline tests
python be2_lightbridge.py           # Runs BE-2 governed pipeline tests
python udp_mesh_spec.py             # Runs UDP mesh round-trip & integrity tests
python octahedral_bridge.py         # Runs tensor mapping, dispatcher & FELTSensor tests
```

Note: `octahedral_bridge.py` requires `numpy` (`pip install numpy`).

There is no test framework (pytest/unittest). Tests run via `if __name__ == "__main__":` blocks.

## Known Issues

- **Unicode quotes**: Both Python files contain Unicode curly quotes (`\u201c`, `\u201d`) in docstrings instead of ASCII quotes, which cause `SyntaxError` on execution.
- **Unimplemented modules**: The `core/`, `transports/`, and `examples/` directories described in the README do not exist yet.

## Development Conventions

- **Gate pattern**: Each pipeline stage can halt processing; energy only flows forward on STABLE/PROCEED status.
- **Nibble encoding**: Vertex indices are stored as 4-bit values (0-11).
- **Dataclass state propagation**: A single `PipelineState` object is mutated and passed through all stages.
- **Stage naming**: Lowercase with underscores in code, PascalCase for class names.
- **No external dependencies**: Keep the project standard-library-only.
- **CC0 license**: All contributions are public domain.

## Git Workflow

- **Main branch**: `master` (remote tracks as `main`)
- **Feature branches**: `claude/<description>` pattern
- **Commit style**: Short descriptive messages (e.g., "Create icosahedral_lightbridge.py")
