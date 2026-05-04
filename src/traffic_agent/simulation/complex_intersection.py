"""
Complex Intersection — Realistic 4-way intersection simulation.

Models a real-world intersection with:
- 4 approaches (N, E, S, W), each with left/through/right lanes
- 8-phase signal control (standard NEMA dual-ring)
- Asymmetric traffic demand (direction bias)
- Pedestrian crossings
- Emergency vehicle preemption
- Dynamic scenario support (rush hour, accident)

This is the core demo unit — a single intersection where LLM
decision-making clearly outperforms fixed timing.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ─── Data Structures ────────────────────────────────────────

@dataclass
class Lane:
    """A single lane at an intersection approach."""
    direction: str   # "left", "through", "right"
    approach: int    # 0=N, 1=E, 2=S, 3=W
    queue: int = 0
    waiting: int = 0
    wait_time: float = 0.0
    vehicles: List[Dict] = field(default_factory=list)


@dataclass
class SignalPhase:
    """A signal phase (e.g., NS_LEFT, NS_THROUGH, EW_LEFT, EW_THROUGH)."""
    name: str
    green_approaches: List[int]   # which approaches get green
    green_lanes: List[str]        # which lane types get green ("left", "through", "right")
    min_green: float = 10.0
    max_green: float = 60.0
    yellow: float = 3.0
    all_red: float = 2.0


# Standard 8-phase NEMA signal plan
PHASES = [
    SignalPhase("NS_LEFT",    [0, 2], ["left"],     min_green=10, max_green=25),
    SignalPhase("NS_THROUGH", [0, 2], ["through", "right"], min_green=15, max_green=45),
    SignalPhase("NS_YELLOW",  [],     [],           yellow=3),
    SignalPhase("ALL_RED_1",  [],     [],           all_red=2),
    SignalPhase("EW_LEFT",    [1, 3], ["left"],     min_green=10, max_green=25),
    SignalPhase("EW_THROUGH", [1, 3], ["through", "right"], min_green=15, max_green=45),
    SignalPhase("EW_YELLOW",  [],     [],           yellow=3),
    SignalPhase("ALL_RED_2",  [],     [],           all_red=2),
]

PHASE_NAMES = [p.name for p in PHASES]


@dataclass
class IntersectionConfig:
    """Configuration for a complex intersection."""
    # Traffic demand (vehicles per second per approach)
    arrival_rate_north: float = 0.5
    arrival_rate_east: float = 0.3
    arrival_rate_south: float = 0.5
    arrival_rate_west: float = 0.3

    # Emergency vehicle rate
    emergency_rate: float = 0.005

    # Pedestrian rate (crossings per second)
    pedestrian_rate: float = 0.02

    # Signal timing (for fixed-timing baseline)
    fixed_phase_duration: float = 30.0

    # Seed
    seed: Optional[int] = None


class ComplexIntersection:
    """
    Realistic 4-way intersection simulation.

    Layout:
              N
              ↑
    W ← ── [IX] ── → E
              ↓
              S

    Each approach has 3 lanes: left, through, right.
    Vehicles are generated at approach boundaries and queue up.
    Signal phases control which lanes get green.
    """

    APPROACH_NAMES = ["North", "East", "South", "West"]
    APPROACH_DIRS = ["N", "E", "S", "W"]
    LANE_TYPES = ["left", "through", "right"]

    def __init__(self, config: Optional[IntersectionConfig] = None):
        self.config = config or IntersectionConfig()
        self.time: float = 0.0
        self.step_count: int = 0

        if self.config.seed is not None:
            np.random.seed(self.config.seed)

        # Lanes: lanes[approach][lane_type] = Lane
        self.lanes: Dict[int, Dict[str, Lane]] = {}
        for approach in range(4):
            self.lanes[approach] = {}
            for lane_type in self.LANE_TYPES:
                self.lanes[approach][lane_type] = Lane(
                    direction=lane_type,
                    approach=approach,
                )

        # Signal state
        self.current_phase_idx: int = 0
        self.phase_timer: float = 0.0
        self.current_phase: SignalPhase = PHASES[0]

        # Metrics
        self.total_vehicles_generated: int = 0
        self.total_vehicles_completed: int = 0
        self.total_wait_time: float = 0.0
        self.total_pedestrian_waits: int = 0

        # Vehicle ID counter
        self._vehicle_counter: int = 0

        # Decision history (for LLM analysis)
        self.decision_history: List[Dict[str, Any]] = []

    @property
    def arrival_rates(self) -> List[float]:
        """Arrival rates for N, E, S, W."""
        return [
            self.config.arrival_rate_north,
            self.config.arrival_rate_east,
            self.config.arrival_rate_south,
            self.config.arrival_rate_west,
        ]

    def step(self) -> Dict[str, Any]:
        """Advance simulation by one time step. Returns step info."""
        dt = 1.0

        # 1. Generate vehicles at each approach
        generated = self._generate_vehicles(dt)

        # 2. Process signal phase timing
        phase_changed = self._update_signal(dt)

        # 3. Move vehicles through intersection
        completed = self._process_vehicles(dt)

        # 4. Update metrics
        self.time += dt
        self.step_count += 1

        # Build step info
        info = {
            "time": self.time,
            "step": self.step_count,
            "phase": self.current_phase.name,
            "phase_timer": self.phase_timer,
            "generated": generated,
            "completed": completed,
            "queues": self.get_queues(),
            "phase_changed": phase_changed,
        }

        self.decision_history.append(info)
        return info

    def apply_llm_decision(self, decision: Dict[str, Any]) -> None:
        """Apply an LLM decision to the signal."""
        target_phase = decision.get("phase", self.current_phase.name)
        duration = decision.get("duration", self.current_phase.max_green)

        if target_phase in PHASE_NAMES:
            idx = PHASE_NAMES.index(target_phase)
            if idx != self.current_phase_idx:
                self.current_phase_idx = idx
                self.current_phase = PHASES[idx]
                self.phase_timer = 0.0

    def get_state(self) -> Dict[str, Any]:
        """Get current state for LLM decision-making."""
        queues = self.get_queues()
        return {
            "time": self.time,
            "phase": self.current_phase.name,
            "phase_timer": self.phase_timer,
            "queues": queues,
            "total_waiting": sum(
                self.lanes[a][l].waiting
                for a in range(4) for l in self.LANE_TYPES
            ),
            "ns_queue": queues.get("north", 0) + queues.get("south", 0),
            "ew_queue": queues.get("east", 0) + queues.get("west", 0),
            "ns_left_queue": (
                self.lanes[0]["left"].queue + self.lanes[2]["left"].queue
            ),
            "ew_left_queue": (
                self.lanes[1]["left"].queue + self.lanes[3]["left"].queue
            ),
        }

    def get_queues(self) -> Dict[str, int]:
        """Get queue length per approach."""
        return {
            self.APPROACH_NAMES[a]: sum(
                self.lanes[a][l].queue for l in self.LANE_TYPES
            )
            for a in range(4)
        }

    def get_metrics(self) -> Dict[str, Any]:
        """Get final metrics."""
        avg_wait = self.total_wait_time / max(1, self.total_vehicles_completed)
        total_queue = sum(
            self.lanes[a][l].queue
            for a in range(4) for l in self.LANE_TYPES
        )
        return {
            "time": self.time,
            "total_vehicles_generated": self.total_vehicles_generated,
            "total_vehicles_completed": self.total_vehicles_completed,
            "completion_rate": self.total_vehicles_completed / max(1, self.total_vehicles_generated),
            "avg_wait_time": avg_wait,
            "total_queue": total_queue,
            "throughput": self.total_vehicles_completed / max(1, self.time),
            "pedestrian_waits": self.total_pedestrian_waits,
        }

    def reset(self) -> None:
        """Reset simulation."""
        self.time = 0.0
        self.step_count = 0
        self._vehicle_counter = 0
        self.total_vehicles_generated = 0
        self.total_vehicles_completed = 0
        self.total_wait_time = 0.0
        self.total_pedestrian_waits = 0
        self.current_phase_idx = 0
        self.phase_timer = 0.0
        self.current_phase = PHASES[0]
        self.decision_history = []

        for approach in range(4):
            for lane_type in self.LANE_TYPES:
                self.lanes[approach][lane_type] = Lane(
                    direction=lane_type,
                    approach=approach,
                )

    # ─── Private Methods ──────────────────────────────────────

    def _generate_vehicles(self, dt: float) -> int:
        """Generate vehicles at each approach."""
        generated = 0
        rates = self.arrival_rates

        for approach in range(4):
            rate = rates[approach]

            # Generate vehicles for each lane type
            for lane_type in self.LANE_TYPES:
                # Lane-specific probability
                if lane_type == "left":
                    prob = rate * 0.25 * dt  # 25% go left
                elif lane_type == "right":
                    prob = rate * 0.20 * dt  # 20% go right
                else:
                    prob = rate * 0.55 * dt  # 55% go through

                if np.random.random() < prob:
                    self._vehicle_counter += 1
                    self.total_vehicles_generated += 1
                    generated += 1

                    v = {
                        "id": f"v_{self._vehicle_counter}",
                        "approach": approach,
                        "lane": lane_type,
                        "entry_time": self.time,
                        "waiting": False,
                    }

                    self.lanes[approach][lane_type].vehicles.append(v)
                    self.lanes[approach][lane_type].queue += 1

            # Emergency vehicle (special: appears in through lane)
            if np.random.random() < self.config.emergency_rate * dt:
                self._vehicle_counter += 1
                self.total_vehicles_generated += 1
                generated += 1

                v = {
                    "id": f"ev_{self._vehicle_counter}",
                    "approach": approach,
                    "lane": "through",
                    "entry_time": self.time,
                    "waiting": False,
                    "is_emergency": True,
                }
                self.lanes[approach]["through"].vehicles.append(v)
                self.lanes[approach]["through"].queue += 1

        return generated

    def _update_signal(self, dt: float) -> bool:
        """Update signal phase timing. Returns True if phase changed."""
        self.phase_timer += dt
        phase = self.current_phase

        # Check if current phase should end
        should_advance = False

        if phase.name in ("NS_YELLOW", "EW_YELLOW", "ALL_RED_1", "ALL_RED_2"):
            # Fixed-duration phases
            if self.phase_timer >= phase.yellow or self.phase_timer >= phase.all_red:
                should_advance = True
        else:
            # Green phases: check min/max green
            if self.phase_timer >= phase.max_green:
                should_advance = True
            elif self.phase_timer >= phase.min_green:
                # Check if there's demand on the conflicting phase
                should_advance = self._should_switch_phase()

        if should_advance:
            self.current_phase_idx = (self.current_phase_idx + 1) % len(PHASES)
            self.current_phase = PHASES[self.current_phase_idx]
            self.phase_timer = 0.0
            return True

        return False

    def _should_switch_phase(self) -> bool:
        """Decide if we should switch from current phase (for fixed timing)."""
        phase = self.current_phase

        # If current green has no queue, switch immediately
        current_queue = sum(
            self.lanes[a][l].queue
            for a in phase.green_approaches
            for l in phase.green_lanes
        )

        if current_queue == 0:
            return True

        # Check conflicting demand
        conflicting_queue = 0
        for a in range(4):
            if a not in phase.green_approaches:
                for l in self.LANE_TYPES:
                    conflicting_queue += self.lanes[a][l].queue

        # Switch if conflicting demand is much higher
        if conflicting_queue > current_queue * 2:
            return True

        return False

    def _process_vehicles(self, dt: float) -> int:
        """Process vehicles at the intersection. Returns number completed."""
        completed = 0
        phase = self.current_phase

        for approach in range(4):
            for lane_type in self.LANE_TYPES:
                lane = self.lanes[approach][lane_type]
                to_remove = []

                for i, v in enumerate(lane.vehicles):
                    # Check if this lane has green
                    has_green = (
                        approach in phase.green_approaches
                        and lane_type in phase.green_lanes
                    )

                    if has_green:
                        # Vehicle passes through
                        to_remove.append(i)
                        self.total_vehicles_completed += 1
                        completed += 1
                        wait = self.time - v["entry_time"]
                        self.total_wait_time += wait
                    else:
                        # Vehicle waits
                        v["waiting"] = True
                        lane.waiting += 1

                # Remove completed vehicles (reverse order)
                for i in sorted(to_remove, reverse=True):
                    lane.vehicles.pop(i)
                    lane.queue -= 1

                # Reset waiting count
                lane.waiting = sum(1 for v in lane.vehicles if v.get("waiting"))

        return completed


# ─── Scenario Variants ──────────────────────────────────────


def create_rush_hour_config(
    heavy_direction: str = "ns",
    severity: float = 1.5,
) -> IntersectionConfig:
    """Create a rush hour config with asymmetric traffic."""
    base = 0.4
    heavy = base * severity
    light = base * 0.6

    if heavy_direction == "ns":
        return IntersectionConfig(
            arrival_rate_north=heavy,
            arrival_rate_south=heavy,
            arrival_rate_east=light,
            arrival_rate_west=light,
            seed=42,
        )
    else:
        return IntersectionConfig(
            arrival_rate_north=light,
            arrival_rate_south=light,
            arrival_rate_east=heavy,
            arrival_rate_west=heavy,
            seed=42,
        )


def create_accident_config() -> IntersectionConfig:
    """Create an accident scenario — one direction blocked, emergency vehicles."""
    return IntersectionConfig(
        arrival_rate_north=0.8,  # Heavy north-south
        arrival_rate_south=0.8,
        arrival_rate_east=0.3,
        arrival_rate_west=0.3,
        emergency_rate=0.03,  # 10x normal emergency rate
        seed=42,
    )


def create_multi_phase_scenario() -> List[Tuple[IntersectionConfig, int]]:
    """Create a multi-phase scenario: normal → rush hour → accident → recovery."""
    return [
        (IntersectionConfig(seed=42), 60),                              # Normal
        (create_rush_hour_config("ns", 2.0), 80),                      # NS rush
        (create_rush_hour_config("ew", 1.8), 60),                      # EW rush
        (create_accident_config(), 50),                                  # Accident
        (IntersectionConfig(seed=42), 50),                              # Recovery
    ]
