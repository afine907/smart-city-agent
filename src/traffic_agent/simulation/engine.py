"""
Simulation Engine — Lightweight traffic simulation.

Zero external dependencies. Provides realistic traffic data
for LLM agents to make decisions on.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from traffic_agent.tools.traffic_tools import IntersectionState


@dataclass
class SimulationConfig:
    """Simulation configuration."""
    dt: float = 1.0              # Time step (seconds)
    max_steps: int = 5000
    arrival_rate: float = 0.5    # Vehicles per second per approach
    speed_limit: float = 13.89   # m/s (50 km/h)
    road_length: float = 200.0   # meters
    seed: Optional[int] = None
    emergency_rate: float = 0.005  # Probability of emergency vehicle per step


@dataclass
class Vehicle:
    """Simple vehicle model."""
    id: str
    approach: int
    position: float
    speed: float
    waiting: bool = False
    is_emergency: bool = False


# Standard 4-phase signal cycle with yellow and all-red transitions
SIGNAL_PHASES = ["NS_GREEN", "NS_YELLOW", "ALL_RED_1", "EW_GREEN", "EW_YELLOW", "ALL_RED_2"]

# Phase durations (seconds) for automatic cycling
PHASE_DURATIONS = {
    "NS_GREEN": 30.0,
    "NS_YELLOW": 3.0,
    "ALL_RED_1": 2.0,
    "EW_GREEN": 30.0,
    "EW_YELLOW": 3.0,
    "ALL_RED_2": 2.0,
}

# Approaches that get green in each phase
GREEN_APPROACHES = {
    "NS_GREEN": [0, 2],      # N, S
    "NS_YELLOW": [],          # All red (yellow = clearing)
    "ALL_RED_1": [],          # All red
    "EW_GREEN": [1, 3],      # E, W
    "EW_YELLOW": [],          # All red (yellow = clearing)
    "ALL_RED_2": [],          # All red
}


@dataclass
class Intersection:
    """Intersection in the road network."""
    id: str
    approaches: int = 4
    current_phase: str = "NS_GREEN"
    phase_timer: float = 0.0
    vehicles: Dict[int, List[Vehicle]] = field(
        default_factory=lambda: defaultdict(list)
    )
    total_wait_time: float = 0.0
    total_served: int = 0

    def get_queue(self, approach: int) -> int:
        return sum(1 for v in self.vehicles[approach] if v.waiting)

    def get_total_queue(self) -> int:
        return sum(self.get_queue(a) for a in range(self.approaches))

    def get_wait_time(self, approach: int) -> float:
        waiting = [v for v in self.vehicles[approach] if v.waiting]
        return len(waiting) * 2.0  # Approximate: 2s per waiting vehicle


class RoadNetwork:
    """Graph of intersections."""
    
    def __init__(self):
        self.intersections: Dict[str, Intersection] = {}
        self.edges: Dict[str, List[str]] = defaultdict(list)
    
    def add(self, intersection: Intersection):
        self.intersections[intersection.id] = intersection
    
    def connect(self, from_id: str, to_id: str):
        self.edges[from_id].append(to_id)
    
    def neighbors(self, ix_id: str) -> List[str]:
        return self.edges.get(ix_id, [])


class SimulationEngine:
    """
    Lightweight traffic simulation engine.
    
    Provides realistic traffic data for LLM decision making.
    """
    
    def __init__(self, config: Optional[SimulationConfig] = None):
        self.config = config or SimulationConfig()
        self.network = RoadNetwork()
        self.time: float = 0.0
        self.step_count: int = 0
        self._vehicle_counter: int = 0
        
        if self.config.seed is not None:
            np.random.seed(self.config.seed)
    
    def add_intersection(self, ix_id: str, approaches: int = 4) -> None:
        ix = Intersection(id=ix_id, approaches=approaches)
        self.network.add(ix)
    
    def connect(self, from_id: str, to_id: str) -> None:
        self.network.connect(from_id, to_id)
    
    def get_state(self, intersection_id: str) -> IntersectionState:
        """Get current state for an intersection (what LLM agents see)."""
        ix = self.network.intersections.get(intersection_id)
        if ix is None:
            return IntersectionState(intersection_id=intersection_id, timestamp=self.time)

        # Check for emergency vehicles
        emergency = False
        emergency_approach = None
        for approach in range(ix.approaches):
            for v in ix.vehicles[approach]:
                if v.is_emergency:
                    emergency = True
                    emergency_approach = approach
                    break
            if emergency:
                break

        return IntersectionState(
            intersection_id=intersection_id,
            timestamp=self.time,
            queue_north=ix.get_queue(0),
            queue_south=ix.get_queue(2),
            queue_east=ix.get_queue(1),
            queue_west=ix.get_queue(3),
            wait_north=ix.get_wait_time(0),
            wait_south=ix.get_wait_time(2),
            wait_east=ix.get_wait_time(1),
            wait_west=ix.get_wait_time(3),
            current_phase=ix.current_phase,
            phase_duration=ix.phase_timer,
            emergency=emergency,
            emergency_approach=emergency_approach,
        )
    
    def apply_decision(self, intersection_id: str, decision: Dict) -> None:
        """Apply LLM decision to simulation."""
        ix = self.network.intersections.get(intersection_id)
        if ix is None:
            return
        
        new_phase = decision.get("phase", ix.current_phase)
        if new_phase != ix.current_phase:
            ix.current_phase = new_phase
            ix.phase_timer = 0.0
    
    def step(self) -> None:
        """Advance simulation by one time step."""
        dt = self.config.dt

        for ix in self.network.intersections.values():
            # Generate vehicles
            self._generate_vehicles(ix, dt)

            # Update signal phase (auto-cycle through yellow/all-red)
            self._update_signal(ix, dt)

            # Update vehicles
            self._update_vehicles(ix, dt)

            # Update signal timer
            ix.phase_timer += dt

        self.time += dt
        self.step_count += 1
    
    def run(self, num_steps: Optional[int] = None) -> Dict[str, Any]:
        """Run simulation and return metrics."""
        steps = num_steps or self.config.max_steps
        
        for _ in range(steps):
            self.step()
        
        return self._get_metrics()
    
    def reset(self) -> None:
        """Reset simulation."""
        self.time = 0.0
        self.step_count = 0
        self._vehicle_counter = 0

        for ix in self.network.intersections.values():
            ix.vehicles.clear()
            ix.current_phase = "NS_GREEN"
            ix.phase_timer = 0.0
            ix.total_wait_time = 0.0
            ix.total_served = 0

    def _generate_vehicles(self, ix: Intersection, dt: float) -> None:
        for approach in range(ix.approaches):
            if np.random.random() < self.config.arrival_rate * dt:
                self._vehicle_counter += 1
                is_emergency = np.random.random() < self.config.emergency_rate
                v = Vehicle(
                    id=f"v_{self._vehicle_counter}",
                    approach=approach,
                    position=self.config.road_length,
                    speed=self.config.speed_limit * (1.5 if is_emergency else 1.0),
                    is_emergency=is_emergency,
                )
                ix.vehicles[approach].append(v)

                # Emergency vehicles trigger immediate green for their approach
                if is_emergency:
                    self._handle_emergency(ix, approach)
    
    def _update_vehicles(self, ix: Intersection, dt: float) -> None:
        for approach in range(ix.approaches):
            to_remove = []
            
            for i, v in enumerate(ix.vehicles[approach]):
                at_intersection = v.position <= 5.0
                has_green = self._has_green(ix, approach)
                
                if at_intersection and not has_green:
                    v.speed = 0
                    v.waiting = True
                    ix.total_wait_time += dt
                else:
                    v.speed = self.config.speed_limit
                    v.waiting = False
                    v.position -= v.speed * dt
                
                if v.position <= -5.0:
                    to_remove.append(i)
                    ix.total_served += 1
            
            for i in sorted(to_remove, reverse=True):
                ix.vehicles[approach].pop(i)
    
    def _has_green(self, ix: Intersection, approach: int) -> bool:
        """Check if approach has green light."""
        green_list = GREEN_APPROACHES.get(ix.current_phase, [])
        return approach in green_list

    def _update_signal(self, ix: Intersection, dt: float) -> None:
        """Auto-cycle signal phases with yellow and all-red transitions."""
        phase = ix.current_phase
        max_duration = PHASE_DURATIONS.get(phase, 30.0)

        if ix.phase_timer >= max_duration:
            # Advance to next phase in cycle
            idx = SIGNAL_PHASES.index(phase)
            next_idx = (idx + 1) % len(SIGNAL_PHASES)
            ix.current_phase = SIGNAL_PHASES[next_idx]
            ix.phase_timer = 0.0

    def _handle_emergency(self, ix: Intersection, approach: int) -> None:
        """Handle emergency vehicle — force green for its approach."""
        # approaches: 0=N, 1=E, 2=S, 3=W
        # NS approaches: 0, 2 → NS_GREEN
        # EW approaches: 1, 3 → EW_GREEN
        if approach in [0, 2]:
            target_phase = "NS_GREEN"
        else:
            target_phase = "EW_GREEN"

        if ix.current_phase != target_phase:
            ix.current_phase = target_phase
            ix.phase_timer = 0.0
    
    def _get_metrics(self) -> Dict[str, Any]:
        metrics = {
            "time": self.time,
            "total_vehicles": sum(
                ix.get_total_queue() for ix in self.network.intersections.values()
            ),
            "total_served": sum(
                ix.total_served for ix in self.network.intersections.values()
            ),
        }
        
        wait_times = []
        for ix in self.network.intersections.values():
            for approach in range(ix.approaches):
                wait_times.append(ix.get_wait_time(approach))
        
        if wait_times:
            metrics["avg_wait_time"] = np.mean(wait_times)
            metrics["max_wait_time"] = np.max(wait_times)
        
        return metrics
