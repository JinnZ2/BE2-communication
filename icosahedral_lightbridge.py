"""
icosahedral_lightbridge.py — Unified Geometric Computation Pipeline

Flow:
3D vector -> LightBridgeEncoder -> HamiltonianResolver -> HamiltonianValidator
-> NautilusGrowth -> UrgencyGuard -> SubstrateHandshake

Each stage gates the next. Energy only flows forward on STABLE/PROCEED.
Any stage can halt the pipeline (entropy guard, thermal limit, lattice violation).

Released CC0.
"""

import math
from dataclasses import dataclass, field
from typing import Optional

# ─────────────────────────────────────────────

# Constants

# ─────────────────────────────────────────────

PHI = (1 + 5**0.5) / 2
GOLDEN_ANGLE = 2 * math.pi * (1 - 1 / PHI)

# Complete icosahedron adjacency (12 vertices, 5 neighbors each)

ICOSA_ADJ = {
    0:  [1, 5, 4, 8, 11],
    1:  [0, 2, 5, 6, 11],
    2:  [1, 3, 6, 7, 11],
    3:  [2, 4, 7, 8, 11],
    4:  [0, 3, 8, 9, 5],
    5:  [0, 1, 4, 9, 10],
    6:  [1, 2, 10, 7, 5],
    7:  [2, 3, 6, 8, 10],
    8:  [0, 3, 4, 7, 9],
    9:  [4, 5, 8, 10, 11],
    10: [5, 6, 7, 9, 11],
    11: [1, 2, 3, 9, 10],
}


def icosahedron_vertices() -> list[tuple[float, float, float]]:
    """12 vertices of a unit icosahedron."""
    verts = []
    for s1 in (-1, 1):
        for s2 in (-PHI, PHI):
            verts.append((0.0,   float(s1), float(s2)))
            verts.append((float(s2), 0.0,   float(s1)))
            verts.append((float(s1), float(s2), 0.0))
    return verts


VERTICES = icosahedron_vertices()

# ─────────────────────────────────────────────

# Pipeline status — single type flows through all stages

# ─────────────────────────────────────────────


@dataclass
class PipelineState:
    vector_in: tuple[float, float, float]
    nibble: Optional[str] = None
    vertex_idx: Optional[int] = None
    status: str = "INIT"
    message: str = ""
    node_position: Optional[tuple[float, float]] = None
    torque_level: Optional[int] = None
    stage: str = "pending"

# ─────────────────────────────────────────────

# Stage 1: LightBridgeEncoder
#
# 3D vector -> nearest icosahedral vertex -> 4-bit nibble
#
# Gates on movement entropy (no extractive jumps)

# ─────────────────────────────────────────────


class LightBridgeEncoder:
    def __init__(self, entropy_threshold: float = 1.5):
        self.vertices = VERTICES
        self.entropy_threshold = entropy_threshold
        self.last_vertex: Optional[int] = None

    def encode(self, state: PipelineState) -> PipelineState:
        best_dist = float('inf')
        best_idx = 0

        for i, v in enumerate(self.vertices):
            d = math.dist(state.vector_in, v)
            if d < best_dist:
                best_dist = d
                best_idx = i

        # Entropy gate: reject non-linear jumps
        if self.last_vertex is not None:
            move_entropy = math.dist(
                self.vertices[self.last_vertex],
                self.vertices[best_idx]
            )
            if move_entropy > self.entropy_threshold:
                state.status = "HALTED"
                state.message = "Encoder: movement entropy exceeds threshold"
                state.stage = "encoder"
                return state

        self.last_vertex = best_idx
        state.vertex_idx = best_idx
        state.nibble = format(best_idx, '04b')
        state.status = "STABLE"
        state.message = f"Encoder: vertex {best_idx}"
        state.stage = "encoder"
        return state

# ─────────────────────────────────────────────

# Stage 2: HamiltonianResolver
#
# Disambiguates when vector falls between vertices
#
# Minimizes switching entropy (momentum preservation)

# ─────────────────────────────────────────────


class HamiltonianResolver:
    def __init__(self, tolerance: float = 1.2):
        self.vertices = VERTICES
        self.tolerance = tolerance
        self.last_idx: Optional[int] = None

    def resolve(self, state: PipelineState) -> PipelineState:
        if state.status != "STABLE":
            return state

        # Find all vertices within tolerance
        candidates = [
            i for i, v in enumerate(self.vertices)
            if math.dist(state.vector_in, v) < self.tolerance
        ]

        if not candidates:
            state.status = "HALTED"
            state.message = "Resolver: no vertices within tolerance"
            state.stage = "resolver"
            return state

        if len(candidates) == 1:
            chosen = candidates[0]
        else:
            # Pick vertex closest to previous position (momentum)
            chosen = candidates[0]
            min_switch = float('inf')
            for idx in candidates:
                if self.last_idx is not None:
                    d = math.dist(self.vertices[self.last_idx], self.vertices[idx])
                    if d < min_switch:
                        min_switch = d
                        chosen = idx

        self.last_idx = chosen
        state.vertex_idx = chosen
        state.nibble = format(chosen, '04b')
        state.message = f"Resolver: locked vertex {chosen} (from {len(candidates)} candidates)"
        state.stage = "resolver"
        return state

# ─────────────────────────────────────────────

# Stage 3: HamiltonianValidator
#
# Verifies nibble represents a legal edge-walk on the lattice
#
# Bit 2 = interference gate (bright fringe -> valid path)

# ─────────────────────────────────────────────


class HamiltonianValidator:
    def __init__(self):
        self.adj = ICOSA_ADJ
        self.current_pos: int = 0

    def validate(self, state: PipelineState) -> PipelineState:
        if state.status != "STABLE":
            return state

        nibble = state.nibble
        assert nibble is not None and len(nibble) == 4

        # Bit 2: interference gate
        if nibble[2] == "0":
            state.status = "RECALIBRATE"
            state.message = "Validator: dark fringe -- signal below threshold"
            state.stage = "validator"
            return state

        # Bits 0-1 select neighbor
        neighbor_idx = int(nibble[:2], 2) % len(self.adj[self.current_pos])
        next_pos = self.adj[self.current_pos][neighbor_idx]
        self.current_pos = next_pos
        state.vertex_idx = next_pos
        state.nibble = format(next_pos, '04b')
        state.message = f"Validator: walked to vertex {next_pos}"
        state.stage = "validator"
        return state

# ─────────────────────────────────────────────

# Stage 4: NautilusGrowth
#
# phi-spaced node expansion -- constant energy density
#
# sqrt(index) radius, golden angle rotation

# ─────────────────────────────────────────────


class NautilusGrowth:
    def __init__(self):
        self.node_count: int = 0

    def expand(self, state: PipelineState) -> PipelineState:
        if state.status not in ("STABLE", "RECALIBRATE"):
            return state
        if state.status == "RECALIBRATE":
            # Don't grow on recalibrate -- hold position
            state.message += " | Growth: held (recalibrating)"
            state.stage = "growth"
            return state

        self.node_count += 1
        r = math.sqrt(self.node_count)
        theta = self.node_count * GOLDEN_ANGLE
        x = r * math.cos(theta)
        y = r * math.sin(theta)
        state.node_position = (round(x, 4), round(y, 4))
        state.message = f"Growth: node {self.node_count} at ({x:.4f}, {y:.4f})"
        state.stage = "growth"
        return state

# ─────────────────────────────────────────────

# Stage 5: UrgencyGuard
#
# Thermal envelope -- gates growth against sCO2 limits

# ─────────────────────────────────────────────


class UrgencyGuard:
    def __init__(self, p_limit: float = 20.0, t_limit: float = 550.0):
        self.p_limit = p_limit
        self.t_limit = t_limit

    def check(self, state: PipelineState,
              current_p: float, current_t: float) -> PipelineState:
        if state.status == "HALTED":
            return state

        p_ratio = current_p / self.p_limit
        t_ratio = current_t / self.t_limit

        if p_ratio > 1.0 or t_ratio > 1.0:
            state.status = "HARD_STOP"
            state.message = "UrgencyGuard: entropy event imminent"
            state.stage = "urgency"
            return state

        if p_ratio > 0.9 or t_ratio > 0.9:
            state.status = "STALL_GROWTH"
            state.message = "UrgencyGuard: approaching thermal ceiling"
            state.stage = "urgency"
            return state

        state.message = f"UrgencyGuard: clear (P={p_ratio:.2f}, T={t_ratio:.2f})"
        state.stage = "urgency"
        return state

# ─────────────────────────────────────────────

# Stage 6: SubstrateHandshake
#
# Final commit gate -- binary instruction -> physical torque

# ─────────────────────────────────────────────


class SubstrateHandshake:
    def __init__(self, hardware_id: str = "sCO2_Unit_01",
                 thermal_ceiling: float = 550.0):
        self.hardware_id = hardware_id
        self.thermal_ceiling = thermal_ceiling
        self.felt_level: float = 1.0  # handshake strength

    def commit(self, state: PipelineState,
               sensor_temp: float) -> PipelineState:
        if state.status in ("HALTED", "HARD_STOP"):
            return state

        if sensor_temp > self.thermal_ceiling:
            self.felt_level = max(0.0, self.felt_level - 0.2)
            state.status = "REJECTED"
            state.message = f"Handshake: thermal limit exceeded (felt={self.felt_level:.1f})"
            state.stage = "handshake"
            return state

        if state.nibble is None:
            state.status = "REJECTED"
            state.message = "Handshake: no nibble to commit"
            state.stage = "handshake"
            return state

        torque = int(state.nibble, 2)
        state.torque_level = torque

        if self.felt_level > 0.6:
            state.status = "COMMITTED"
            state.message = f"Handshake: torque {torque} on {self.hardware_id}"
        else:
            state.status = "STALLED"
            state.message = f"Handshake: felt too low ({self.felt_level:.1f})"

        state.stage = "handshake"
        return state

# ─────────────────────────────────────────────

# Pipeline Runner

# ─────────────────────────────────────────────


class GeometricPipeline:
    """
    Full pipeline: vector -> nibble -> validate -> grow -> thermal check -> commit.

    Usage:
        pipe = GeometricPipeline()
        results = pipe.run(vectors, pressure=15.0, temperature=400.0)
    """

    def __init__(self, **kwargs):
        self.encoder = LightBridgeEncoder(
            entropy_threshold=kwargs.get("entropy_threshold", 1.5)
        )
        self.resolver = HamiltonianResolver(
            tolerance=kwargs.get("tolerance", 1.2)
        )
        self.validator = HamiltonianValidator()
        self.growth = NautilusGrowth()
        self.guard = UrgencyGuard(
            p_limit=kwargs.get("p_limit", 20.0),
            t_limit=kwargs.get("t_limit", 550.0)
        )
        self.handshake = SubstrateHandshake(
            hardware_id=kwargs.get("hardware_id", "sCO2_Unit_01"),
            thermal_ceiling=kwargs.get("thermal_ceiling", 550.0)
        )

    def step(self, vector: tuple[float, float, float],
             pressure: float, temperature: float) -> PipelineState:
        """Process one vector through the full pipeline."""
        s = PipelineState(vector_in=vector)

        s = self.encoder.encode(s)
        if s.status != "STABLE":
            return s

        s = self.resolver.resolve(s)
        if s.status != "STABLE":
            return s

        s = self.validator.validate(s)
        # validator can RECALIBRATE -- growth handles that

        s = self.growth.expand(s)

        s = self.guard.check(s, pressure, temperature)
        if s.status in ("HARD_STOP", "STALL_GROWTH"):
            return s

        s = self.handshake.commit(s, temperature)
        return s

    def run(self, vectors: list[tuple[float, float, float]],
            pressure: float = 15.0,
            temperature: float = 400.0) -> list[PipelineState]:
        """Process a sequence of vectors."""
        return [self.step(v, pressure, temperature) for v in vectors]

# ─────────────────────────────────────────────

# Demo / Self-Test

# ─────────────────────────────────────────────

if __name__ == "__main__":
    pipe = GeometricPipeline()

    # Smooth path near vertex cluster (low entropy)
    test_vectors = [
        (0.0,  1.1,  1.6),
        (0.1,  0.9,  1.7),
        (0.2,  0.8,  1.8),
        (0.0, -1.0, -1.6),   # big jump -- should trigger entropy gate
        (0.05, 0.95, 1.65),  # back to smooth
    ]

    print("=" * 60)
    print("PIPELINE TEST -- Normal conditions (15 MPa, 400 C)")
    print("=" * 60)

    for v in test_vectors:
        result = pipe.step(v, pressure=15.0, temperature=400.0)
        print(f"  {v} -> [{result.status}] {result.message}")

    print()
    print("=" * 60)
    print("PIPELINE TEST -- Thermal stress (19 MPa, 520 C)")
    print("=" * 60)

    pipe2 = GeometricPipeline()
    for v in test_vectors[:3]:
        result = pipe2.step(v, pressure=19.0, temperature=520.0)
        print(f"  {v} -> [{result.status}] {result.message}")

    print()
    print("=" * 60)
    print("PIPELINE TEST -- Over thermal ceiling (560 C)")
    print("=" * 60)

    pipe3 = GeometricPipeline()
    result = pipe3.step(test_vectors[0], pressure=15.0, temperature=560.0)
    print(f"  {test_vectors[0]} -> [{result.status}] {result.message}")
