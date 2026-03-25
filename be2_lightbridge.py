"""
be2_lightbridge.py — BE-2 Geometric Computation Pipeline with Meta-Awareness

Architecture (energy flows top->down, any gate can halt):

+---------------------------------------------------+
|              MetaAwareness (supervisor)             |
|  watches all stages, injects null nibbles on        |
|  recovery, forces survival mode on extremes         |
+---------------------------------------------------+
|                                                     |
|  3D vector                                          |
|    |                                                |
|  LightBridgeEncoder  (nearest vertex -> 4-bit)      |
|    |                                                |
|  HamiltonianResolver (disambiguate boundaries)      |
|    |                                                |
|  HamiltonianValidator (lattice edge-walk check)     |
|    |                                                |
|  NautilusGrowth (phi-spaced node expansion)         |
|    |                                                |
|  UrgencyGuard (thermal envelope)                    |
|    |                                                |
|  SubstrateHandshake (commit -> physical torque)     |
|                                                     |
+---------------------------------------------------+
|  WhiteoutSimulator (environmental stress input)     |
|  ThermalModel (internal heat accumulation)          |
+---------------------------------------------------+

Released CC0.
"""

import math
import random
from dataclasses import dataclass
from typing import Optional

# ─────────────────────────────────────────────

# Constants

# ─────────────────────────────────────────────

PHI = (1 + 5**0.5) / 2
GOLDEN_ANGLE = 2 * math.pi * (1 - 1 / PHI)

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
    verts = []
    for s1 in (-1, 1):
        for s2 in (-PHI, PHI):
            verts.append((0.0, float(s1), float(s2)))
            verts.append((float(s2), 0.0, float(s1)))
            verts.append((float(s1), float(s2), 0.0))
    return verts


VERTICES = icosahedron_vertices()
NULL_VECTOR = (0.0, 0.0, 0.0)

# ─────────────────────────────────────────────

# Pipeline State — single type through all stages

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
    # Meta-awareness fields
    meta_action: str = "CONTINUE"
    internal_t: float = 0.0
    ambient_t: float = 0.0
    is_recovery_nibble: bool = False

# ─────────────────────────────────────────────

# Stage 1: LightBridgeEncoder

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

# ─────────────────────────────────────────────


class HamiltonianResolver:
    def __init__(self, tolerance: float = 1.2):
        self.vertices = VERTICES
        self.tolerance = tolerance
        self.last_idx: Optional[int] = None

    def resolve(self, state: PipelineState) -> PipelineState:
        if state.status != "STABLE":
            return state

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
        state.message = f"Resolver: locked vertex {chosen} ({len(candidates)} candidates)"
        state.stage = "resolver"
        return state

# ─────────────────────────────────────────────

# Stage 3: HamiltonianValidator

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

        if nibble[2] == "0":
            state.status = "RECALIBRATE"
            state.message = "Validator: dark fringe -- signal below threshold"
            state.stage = "validator"
            return state

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

# ─────────────────────────────────────────────


class NautilusGrowth:
    def __init__(self):
        self.node_count: int = 0

    def expand(self, state: PipelineState) -> PipelineState:
        if state.status not in ("STABLE", "RECALIBRATE"):
            return state
        if state.status == "RECALIBRATE":
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

# ─────────────────────────────────────────────


class SubstrateHandshake:
    def __init__(self, hardware_id: str = "sCO2_Unit_01",
                 thermal_ceiling: float = 550.0):
        self.hardware_id = hardware_id
        self.thermal_ceiling = thermal_ceiling
        self.felt_level: float = 1.0

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

# Environment: WhiteoutSimulator
#
# External thermal stress — ambient temperature swings
# Models arctic conditions / polar vortex events

# ─────────────────────────────────────────────


class WhiteoutSimulator:
    def __init__(self, start_ambient: float = -10.0,
                 swing_range: tuple[float, float] = (5.0, 15.0),
                 seed: Optional[int] = None):
        self.ambient_t = start_ambient
        self.swing_range = swing_range
        if seed is not None:
            random.seed(seed)

    def step(self) -> float:
        """One timestep of ambient temperature drop."""
        self.ambient_t -= random.uniform(*self.swing_range)
        return self.ambient_t

    def reset(self, start: float = -10.0):
        self.ambient_t = start

# ─────────────────────────────────────────────

# Environment: ThermalModel
#
# Internal heat accumulation with cooling pulse

# ─────────────────────────────────────────────


class ThermalModel:
    def __init__(self, start_t: float = 480.0,
                 heat_per_step: float = 8.0,
                 cooling_pulse: float = 40.0,
                 thermal_floor: float = 20.0):
        self.internal_t = start_t
        self.heat_per_step = heat_per_step
        self.cooling_pulse = cooling_pulse
        self.thermal_floor = thermal_floor

    def step(self, is_recovery: bool = False) -> float:
        """Accumulate heat, or apply cooling pulse during recovery."""
        if is_recovery:
            self.internal_t = max(self.thermal_floor,
                                  self.internal_t - self.cooling_pulse)
        else:
            self.internal_t += self.heat_per_step
        return self.internal_t

# ─────────────────────────────────────────────

# Meta-Awareness Layer
#
# Supervisor across all pipeline agents
#
# Decision hierarchy:
#   1. SURVIVAL — ambient or internal at lethal thresholds
#   2. IDLE_RECOVERY — thermal stall, inject null nibbles
#   3. CONTINUE — normal flow
#
# In survival mode: all innovation halted,
# 100% energy to substrate preservation

# ─────────────────────────────────────────────


class MetaAwareness:
    def __init__(self, ambient_floor: float = -48.0,
                 internal_ceiling: float = 560.0):
        self.ambient_floor = ambient_floor
        self.internal_ceiling = internal_ceiling
        self.recovery_mode: bool = False
        self.survival_mode: bool = False
        self.manual_override: bool = False

    def evaluate(self, pipeline_status: str,
                 ambient_t: float, internal_t: float,
                 manual_trigger: bool = False) -> str:
        """
        Returns one of:
          SURVIVAL         -- lethal conditions, shut everything down
          IDLE_RECOVERY    -- thermal stall, inject cooling
          CONTINUE         -- normal operation
        """
        # Priority 1: manual override
        if manual_trigger:
            self.manual_override = True
            self.survival_mode = True
            self.recovery_mode = False
            return "SURVIVAL"

        # Priority 2: environmental lethality
        if ambient_t < self.ambient_floor:
            self.survival_mode = True
            self.recovery_mode = False
            return "SURVIVAL"

        # Priority 3: internal thermal runaway
        if internal_t > self.internal_ceiling:
            self.survival_mode = True
            self.recovery_mode = False
            return "SURVIVAL"

        # Priority 2.5: exit survival if conditions recovered
        if self.survival_mode:
            # Both ambient and internal must be in safe range
            if ambient_t >= self.ambient_floor and internal_t <= self.internal_ceiling:
                self.survival_mode = False
                self.recovery_mode = True  # transition through recovery
                return "IDLE_RECOVERY"
            else:
                return "SURVIVAL"

        # Priority 4: pipeline-reported stall
        if pipeline_status in ("STALL_GROWTH", "RECALIBRATE"):
            self.survival_mode = False
            self.recovery_mode = True
            return "IDLE_RECOVERY"

        # Priority 5: hard stop from pipeline
        if pipeline_status in ("HARD_STOP", "HALTED", "REJECTED"):
            self.survival_mode = False
            self.recovery_mode = False
            return "HALT"

        # All clear
        self.survival_mode = False
        self.recovery_mode = False
        return "CONTINUE"

    def survival_state(self) -> dict:
        """What the system looks like in survival mode."""
        return {
            "LightBridge": "OFFLINE",
            "sCO2_Mode": "THERMAL_MAX",
            "Innovation_Yield": 0.0,
            "Substrate_Safety": 1.0,
        }

# ─────────────────────────────────────────────

# Pipeline Runner (static thermal — original interface)

# ─────────────────────────────────────────────


class GeometricPipeline:
    """
    Stateless thermal: vector + fixed P/T -> result.
    Use for unit testing individual stages.
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
        s = PipelineState(vector_in=vector)

        s = self.encoder.encode(s)
        if s.status != "STABLE":
            return s

        s = self.resolver.resolve(s)
        if s.status != "STABLE":
            return s

        s = self.validator.validate(s)
        s = self.growth.expand(s)

        s = self.guard.check(s, pressure, temperature)
        if s.status in ("HARD_STOP", "STALL_GROWTH"):
            return s

        s = self.handshake.commit(s, temperature)
        return s

    def run(self, vectors: list[tuple[float, float, float]],
            pressure: float = 15.0,
            temperature: float = 400.0) -> list[PipelineState]:
        return [self.step(v, pressure, temperature) for v in vectors]

# ─────────────────────────────────────────────

# BE-2 Governed Pipeline
#
# Dynamic thermal + meta-awareness + environment
#
# The meta layer wraps the pipeline:
#   - Before each step: evaluate environment
#   - If SURVIVAL: skip pipeline, emit survival state
#   - If IDLE_RECOVERY: inject null nibble + cooling pulse
#   - If CONTINUE: run normal pipeline with current thermal

# ─────────────────────────────────────────────


class BE2Pipeline:
    """
    Full governed pipeline with dynamic thermal model.

    Usage:
        be2 = BE2Pipeline(seed=42)  # deterministic environment
        log = be2.run(vectors, pressure=15.0, steps=20)
    """

    def __init__(self, **kwargs):
        self.pipe = GeometricPipeline(**kwargs)
        self.meta = MetaAwareness(
            ambient_floor=kwargs.get("ambient_floor", -48.0),
            internal_ceiling=kwargs.get("internal_ceiling", 560.0),
        )
        self.thermal = ThermalModel(
            start_t=kwargs.get("start_t", 480.0),
            heat_per_step=kwargs.get("heat_per_step", 8.0),
            cooling_pulse=kwargs.get("cooling_pulse", 40.0),
        )
        self.environment = WhiteoutSimulator(
            start_ambient=kwargs.get("start_ambient", -10.0),
            swing_range=kwargs.get("swing_range", (5.0, 15.0)),
            seed=kwargs.get("seed", None),
        )
        self.pressure = kwargs.get("pressure", 15.0)

    def step(self, vector: tuple[float, float, float]) -> PipelineState:
        """One governed timestep."""
        # Environment evolves
        ambient = self.environment.step()

        # Determine thermal behavior:
        #   survival -> no heat added (innovation offline)
        #   recovery -> cooling pulse
        #   normal   -> heat accumulates
        is_recovery = self.meta.recovery_mode
        if self.meta.survival_mode:
            # Innovation offline = no heat generated, passive cooling
            internal = self.thermal.step(is_recovery=True)
        else:
            internal = self.thermal.step(is_recovery=is_recovery)

        # Run pipeline (may get STALL_GROWTH etc.)
        if self.meta.survival_mode:
            # Pipeline offline -- emit survival state
            s = PipelineState(vector_in=vector)
            s.status = "SURVIVAL"
            s.message = f"Meta: survival mode -- {self.meta.survival_state()}"
            s.meta_action = "SURVIVAL"
            s.internal_t = internal
            s.ambient_t = ambient
            s.stage = "meta"
            return s

        if is_recovery:
            # Inject null nibble -- keep lattice spinning, no thermal load
            s = PipelineState(vector_in=NULL_VECTOR)
            s.nibble = "0000"
            s.is_recovery_nibble = True
            s.status = "IDLE_RECOVERY"
            s.message = f"Meta: null nibble injected, cooling to {internal:.1f} C"
            s.internal_t = internal
            s.ambient_t = ambient
            s.stage = "meta"
            # Re-evaluate after cooling
            s.meta_action = self.meta.evaluate(
                "IDLE_RECOVERY", ambient, internal
            )
            return s

        # Normal pipeline
        result = self.pipe.step(vector, self.pressure, internal)
        result.internal_t = internal
        result.ambient_t = ambient

        # Meta evaluates the pipeline result
        result.meta_action = self.meta.evaluate(
            result.status, ambient, internal
        )

        return result

    def run(self, vectors: list[tuple[float, float, float]],
            max_steps: Optional[int] = None) -> list[PipelineState]:
        """
        Process vectors with governed thermal evolution.
        If max_steps > len(vectors), vectors cycle.
        """
        n = max_steps or len(vectors)
        results = []
        for i in range(n):
            v = vectors[i % len(vectors)]
            result = self.step(v)
            results.append(result)
            if result.meta_action == "SURVIVAL":
                # Log it but keep going -- survival mode doesn't break,
                # it redirects all energy to substrate preservation
                pass
        return results

# ─────────────────────────────────────────────

# Self-Test

# ─────────────────────────────────────────────

if __name__ == "__main__":
    test_vectors = [
        (0.0,  1.1,  1.6),
        (0.1,  0.9,  1.7),
        (0.2,  0.8,  1.8),
        (0.05, 0.95, 1.65),
    ]

    # -- Test 1: Static pipeline (original behavior) --
    print("=" * 65)
    print("TEST 1 -- Static Pipeline (15 MPa, 400 C)")
    print("=" * 65)
    pipe = GeometricPipeline()
    for v in test_vectors:
        r = pipe.step(v, 15.0, 400.0)
        print(f"  {v} -> [{r.status}] {r.message}")

    # -- Test 2: BE-2 governed pipeline, normal conditions --
    print()
    print("=" * 65)
    print("TEST 2 -- BE-2 Governed Pipeline (mild environment)")
    print("=" * 65)
    be2 = BE2Pipeline(
        start_t=400.0,        # comfortable start
        heat_per_step=5.0,    # slow heat build
        start_ambient=0.0,    # mild
        swing_range=(1.0, 3.0),
        seed=42,
    )
    for v in test_vectors:
        r = be2.step(v)
        print(f"  [{r.status:15s}] T_int={r.internal_t:.0f} C  "
              f"T_amb={r.ambient_t:.1f} C  meta={r.meta_action}")

    # -- Test 3: BE-2 under whiteout stress --
    print()
    print("=" * 65)
    print("TEST 3 -- BE-2 Minnesota Whiteout (20 steps)")
    print("=" * 65)
    be2_stress = BE2Pipeline(
        start_t=480.0,
        heat_per_step=8.0,
        start_ambient=-10.0,
        swing_range=(5.0, 15.0),
        seed=7,
    )
    results = be2_stress.run(test_vectors, max_steps=20)
    for i, r in enumerate(results):
        flag = "***" if r.meta_action in ("SURVIVAL", "HALT") else "   "
        print(f"  {flag} step {i:02d}  [{r.status:15s}] "
              f"T_int={r.internal_t:.0f} C  T_amb={r.ambient_t:.1f} C  "
              f"meta={r.meta_action}")
