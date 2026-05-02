"""
Simulation Engine — Traffic Environment

Lightweight traffic simulation engine.
No external dependencies (SUMO, etc.) — full control over dynamics.

Design:
- Event-driven (not polling)
- Deterministic for reproducibility
- Supports real-time and accelerated modes
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from traffic_agent.agents.base_agent import Observation


@dataclass
class Vehicle:
    """Single vehicle in the simulation."""
    id: str
    approach: int          # Which approach (0=N, 1=E, 2=S, 3=W)
    position: float        # Meters from intersection
    speed: float           # m/s
    desired_speed: float   # m/s
    waiting: bool = False
    
    def __repr__(self):
        return f"Vehicle({self.id}, pos={self.position:.1f}, spd={self.speed:.1f})"


@dataclass
class SignalPhase:
    """Traffic signal phase definition."""
    index: int
    name: str
    green_approaches: List[int]  # Which approaches get green
    yellow_approaches: List[int]  # Which approaches get yellow
    min_green: float = 10.0
    max_green: float = 60.0


@dataclass 
class Intersection:
    """Single intersection in the road network."""
    id: str
    approaches: int = 4
    phases: List[SignalPhase] = field(default_factory=list)
    current_phase: int = 0
    phase_timer: float = 0.0
    
    # Vehicles per approach
    vehicles: Dict[int, List[Vehicle]] = field(default_factory=lambda: defaultdict(list))
    
    # Metrics
    total_wait_time: float = 0.0
    total_vehicles_served: int = 0
    
    def __post_init__(self):
        if not self.phases:
            # Default 4-phase signal
            self.phases = [
                SignalPhase(0, "NS_Green", [0, 2], [1, 3]),
                SignalPhase(1, "NS_Yellow", [], [0, 2]),
                SignalPhase(2, "EW_Green", [1, 3], [0, 2]),
                SignalPhase(3, "EW_Yellow", [], [1, 3]),
            ]


@dataclass
class SimulationConfig:
    """Simulation configuration."""
    # Time
    dt: float = 0.1              # Time step (seconds)
    max_steps: int = 10_000      # Max simulation steps
    real_time: bool = False      # Real-time mode
    
    # Road network
    road_length: float = 200.0   # Meters from intersection center
    speed_limit: float = 13.89   # m/s (50 km/h)
    
    # Vehicle generation
    arrival_rate: float = 0.5    # Vehicles per second per approach
    max_vehicles: int = 1000     # Max vehicles in simulation
    
    # Metrics
    metrics_interval: float = 10.0  # Seconds between metric snapshots
    
    # Random seed
    seed: Optional[int] = None


class RoadNetwork:
    """
    Graph representation of road network.
    
    Nodes = Intersections
    Edges = Road segments connecting intersections
    """
    
    def __init__(self):
        self.intersections: Dict[str, Intersection] = {}
        self.edges: Dict[str, List[str]] = defaultdict(list)  # adjacency list
    
    def add_intersection(self, intersection: Intersection) -> None:
        self.intersections[intersection.id] = intersection
    
    def connect(self, from_id: str, to_id: str) -> None:
        """Add directed edge from intersection to intersection."""
        self.edges[from_id].append(to_id)
    
    def get_neighbors(self, intersection_id: str) -> List[str]:
        return self.edges.get(intersection_id, [])


class EventBus:
    """Simple event system for simulation events."""
    
    def __init__(self):
        self._handlers: Dict[str, List] = defaultdict(list)
    
    def on(self, event_type: str, handler) -> None:
        self._handlers[event_type].append(handler)
    
    def emit(self, event_type: str, data: Any) -> None:
        for handler in self._handlers.get(event_type, []):
            handler(data)


class MetricsCollector:
    """Collect and aggregate simulation metrics."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.wait_times: List[float] = []
        self.queue_lengths: List[int] = []
        self.throughput: int = 0
        self.phase_changes: int = 0
        self._timestamps: List[float] = []
    
    def record_wait(self, wait_time: float):
        self.wait_times.append(wait_time)
    
    def record_queue(self, length: int):
        self.queue_lengths.append(length)
    
    def record_served(self):
        self.throughput += 1
    
    def record_phase_change(self):
        self.phase_changes += 1
    
    def get_summary(self) -> Dict[str, float]:
        return {
            "avg_wait_time": np.mean(self.wait_times) if self.wait_times else 0,
            "max_wait_time": np.max(self.wait_times) if self.wait_times else 0,
            "avg_queue_length": np.mean(self.queue_lengths) if self.queue_lengths else 0,
            "throughput": self.throughput,
            "phase_changes": self.phase_changes,
        }


class SimulationEngine:
    """
    Core simulation engine.
    
    Responsibilities:
    1. Maintain road network state
    2. Spawn vehicles according to demand
    3. Process agent actions (signal changes)
    4. Update vehicle positions
    5. Calculate metrics
    6. Emit events for monitoring
    """
    
    def __init__(self, config: Optional[SimulationConfig] = None):
        self.config = config or SimulationConfig()
        self.road_network = RoadNetwork()
        self.event_bus = EventBus()
        self.metrics = MetricsCollector()
        
        self.time: float = 0.0
        self.step_count: int = 0
        self._running: bool = False
        self._vehicle_counter: int = 0
        
        if self.config.seed is not None:
            np.random.seed(self.config.seed)
    
    def add_intersection(self, intersection: Intersection) -> None:
        """Add an intersection to the simulation."""
        self.road_network.add_intersection(intersection)
    
    def connect(self, from_id: str, to_id: str) -> None:
        """Connect two intersections."""
        self.road_network.connect(from_id, to_id)
    
    def get_observation(self, intersection_id: str) -> Observation:
        """
        Get observation for an intersection agent.
        
        This is what the RL agent sees.
        """
        ix = self.road_network.intersections[intersection_id]
        
        queue_lengths = np.zeros(ix.approaches)
        vehicle_counts = np.zeros(ix.approaches)
        arrival_rates = np.zeros(ix.approaches)
        pedestrian_waiting = np.zeros(ix.approaches)
        
        for approach, vehicles in ix.vehicles.items():
            queue_lengths[approach] = sum(1 for v in vehicles if v.waiting)
            vehicle_counts[approach] = len(vehicles)
            # Estimate arrival rate from recent history
            arrival_rates[approach] = len(vehicles) / max(1, self.time)
        
        return Observation(
            intersection_id=intersection_id,
            timestamp=self.time,
            queue_lengths=queue_lengths,
            vehicle_counts=vehicle_counts,
            arrival_rates=arrival_rates,
            current_phase=ix.current_phase,
            phase_duration=ix.phase_timer,
            time_since_change=ix.phase_timer,
            pedestrian_waiting=pedestrian_waiting,
            emergency_pending=False,
        )
    
    def apply_action(self, intersection_id: str, phase: int, duration: float) -> None:
        """
        Apply agent's action to the intersection.
        
        Changes the signal phase.
        """
        ix = self.road_network.intersections[intersection_id]
        if phase != ix.current_phase:
            ix.current_phase = phase
            ix.phase_timer = 0.0
            self.metrics.record_phase_change()
            self.event_bus.emit("phase_change", {
                "intersection_id": intersection_id,
                "phase": phase,
                "time": self.time,
            })
    
    def step(self) -> Dict[str, Observation]:
        """
        Advance simulation by one time step.
        
        Returns observations for all intersections.
        """
        dt = self.config.dt
        
        # 1. Generate new vehicles
        self._generate_vehicles(dt)
        
        # 2. Update vehicle positions
        self._update_vehicles(dt)
        
        # 3. Update signal timers
        self._update_signals(dt)
        
        # 4. Collect observations
        observations = {}
        for ix_id in self.road_network.intersections:
            observations[ix_id] = self.get_observation(ix_id)
        
        # 5. Update time
        self.time += dt
        self.step_count += 1
        
        return observations
    
    def run(self, num_steps: Optional[int] = None) -> Dict[str, float]:
        """
        Run simulation for specified steps.
        
        Returns final metrics summary.
        """
        steps = num_steps or self.config.max_steps
        self._running = True
        
        for _ in range(steps):
            if not self._running:
                break
            
            self.step()
            
            # Real-time mode
            if self.config.real_time:
                time.sleep(self.config.dt)
        
        return self.metrics.get_summary()
    
    def stop(self) -> None:
        """Stop simulation."""
        self._running = False
    
    def reset(self) -> None:
        """Reset simulation to initial state."""
        self.time = 0.0
        self.step_count = 0
        self._vehicle_counter = 0
        self.metrics.reset()
        
        for ix in self.road_network.intersections.values():
            ix.vehicles.clear()
            ix.current_phase = 0
            ix.phase_timer = 0.0
            ix.total_wait_time = 0.0
            ix.total_vehicles_served = 0
    
    # ─── Private Methods ───────────────────────────────────────
    
    def _generate_vehicles(self, dt: float) -> None:
        """Generate new vehicles on each approach."""
        for ix in self.road_network.intersections.values():
            for approach in range(ix.approaches):
                # Poisson arrival process
                if np.random.random() < self.config.arrival_rate * dt:
                    self._vehicle_counter += 1
                    vehicle = Vehicle(
                        id=f"v_{self._vehicle_counter}",
                        approach=approach,
                        position=self.config.road_length,
                        speed=self.config.speed_limit,
                        desired_speed=self.config.speed_limit,
                    )
                    ix.vehicles[approach].append(vehicle)
    
    def _update_vehicles(self, dt: float) -> None:
        """Update vehicle positions and handle queuing."""
        for ix in self.road_network.intersections.values():
            for approach in range(ix.approaches):
                vehicles = ix.vehicles[approach]
                to_remove = []
                
                for i, vehicle in enumerate(vehicles):
                    # Check if vehicle should stop (red light + at intersection)
                    at_intersection = vehicle.position <= 5.0
                    has_green = approach in ix.phases[ix.current_phase].green_approaches
                    
                    if at_intersection and not has_green:
                        # Stop at intersection
                        vehicle.speed = 0
                        vehicle.waiting = True
                        ix.total_wait_time += dt
                    else:
                        # Move forward
                        vehicle.speed = vehicle.desired_speed
                        vehicle.waiting = False
                        vehicle.position -= vehicle.speed * dt
                    
                    # Vehicle has passed through intersection
                    if vehicle.position <= -5.0:
                        to_remove.append(i)
                        ix.total_vehicles_served += 1
                        self.metrics.record_served()
                
                # Remove vehicles that passed through
                for i in sorted(to_remove, reverse=True):
                    vehicles.pop(i)
                
                # Record queue length
                queue = sum(1 for v in vehicles if v.waiting)
                self.metrics.record_queue(queue)
    
    def _update_signals(self, dt: float) -> None:
        """Update signal timers and auto-change if needed."""
        for ix in self.road_network.intersections.values():
            ix.phase_timer += dt
            
            # Auto-advance phase if max green exceeded
            phase = ix.phases[ix.current_phase]
            if ix.phase_timer >= phase.max_green:
                next_phase = (ix.current_phase + 1) % len(ix.phases)
                self.apply_action(ix.id, next_phase, 0)
