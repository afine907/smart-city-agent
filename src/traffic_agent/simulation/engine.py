"""
Simulation Engine - Lightweight traffic simulation.

Zero external dependencies. Provides realistic traffic data
for LLM agents to make decisions on.

Supports mixed traffic: cars, electric bikes, bicycles, pedestrians,
and emergency vehicles - reflecting real-world road conditions.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np

from traffic_agent.tools.traffic_tools import IntersectionState


# ─── Vehicle Types ──────────────────────────────────────────────

class VehicleType(str, Enum):
    """Types of road users in mixed traffic."""
    CAR = "car"                # 汽车
    E_BIKE = "e_bike"          # 电动自行车
    BICYCLE = "bicycle"        # 自行车
    PEDESTRIAN = "pedestrian"  # 行人
    EMERGENCY = "emergency"    # 紧急车辆(救护车/消防车)
    BUS = "bus"                # 公交车


@dataclass(frozen=True)
class VehicleTypeInfo:
    """Physical and behavioral properties of a vehicle type."""
    name: str
    name_zh: str
    speed_min: float       # m/s - minimum travel speed
    speed_max: float       # m/s - maximum travel speed
    speed_normal: float    # m/s - normal/cruise speed
    length: float          # meters - vehicle length
    width: float           # meters - vehicle width
    acceleration: float    # m/s2 - typical acceleration
    deceleration: float    # m/s2 - typical deceleration (braking)
    space_occupancy: float # meters - space occupied in queue (length + gap)
    can_use_bike_lane: bool
    respects_signal: bool  # False = may ignore (e.g., jaywalking pedestrians)
    has_priority: bool     # Emergency vehicles get priority


# Vehicle type registry - based on real-world data
VEHICLE_TYPES: Dict[VehicleType, VehicleTypeInfo] = {
    VehicleType.CAR: VehicleTypeInfo(
        name="car", name_zh="汽车",
        speed_min=0, speed_max=16.67, speed_normal=13.89,  # 0-60 km/h, normal 50 km/h
        length=4.5, width=1.8,
        acceleration=2.5, deceleration=4.5,
        space_occupancy=7.5,  # 4.5m car + 3m gap
        can_use_bike_lane=False, respects_signal=True, has_priority=False,
    ),
    VehicleType.BUS: VehicleTypeInfo(
        name="bus", name_zh="公交车",
        speed_min=0, speed_max=13.89, speed_normal=11.11,  # 0-50 km/h, normal 40 km/h
        length=12.0, width=2.5,
        acceleration=1.5, deceleration=3.5,
        space_occupancy=15.0,  # 12m bus + 3m gap
        can_use_bike_lane=False, respects_signal=True, has_priority=False,
    ),
    VehicleType.E_BIKE: VehicleTypeInfo(
        name="e_bike", name_zh="电动自行车",
        speed_min=0, speed_max=8.33, speed_normal=6.25,  # 0-30 km/h, normal 22.5 km/h
        length=1.8, width=0.6,
        acceleration=2.0, deceleration=5.0,
        space_occupancy=2.5,  # 1.8m bike + 0.7m gap
        can_use_bike_lane=True, respects_signal=False,  # May enter car lanes, run red
        has_priority=False,
    ),
    VehicleType.BICYCLE: VehicleTypeInfo(
        name="bicycle", name_zh="自行车",
        speed_min=0, speed_max=5.56, speed_normal=4.17,  # 0-20 km/h, normal 15 km/h
        length=1.7, width=0.5,
        acceleration=1.0, deceleration=4.0,
        space_occupancy=2.2,  # 1.7m bike + 0.5m gap
        can_use_bike_lane=True, respects_signal=False,  # May run red lights
        has_priority=False,
    ),
    VehicleType.PEDESTRIAN: VehicleTypeInfo(
        name="pedestrian", name_zh="行人",
        speed_min=0, speed_max=2.22, speed_normal=1.39,  # 0-8 km/h, normal 5 km/h
        length=0.5, width=0.5,
        acceleration=0.5, deceleration=3.0,
        space_occupancy=0.8,  # 0.5m person + 0.3m gap
        can_use_bike_lane=False, respects_signal=False,  # May jaywalk
        has_priority=False,
    ),
    VehicleType.EMERGENCY: VehicleTypeInfo(
        name="emergency", name_zh="紧急车辆",
        speed_min=5.0, speed_max=22.22, speed_normal=16.67,  # 18-80 km/h, normal 60 km/h
        length=5.5, width=2.2,
        acceleration=3.0, deceleration=5.0,
        space_occupancy=9.0,  # 5.5m + 3.5m gap (others yield)
        can_use_bike_lane=False, respects_signal=False,  # Can run red
        has_priority=True,
    ),
}


@dataclass
class SimulationConfig:
    """Simulation configuration."""
    dt: float = 1.0              # Time step (seconds)
    max_steps: int = 5000
    arrival_rate: float = 0.5    # Vehicles per second per approach
    speed_limit: float = 13.89   # m/s (50 km/h) - used as default for cars
    road_length: float = 200.0   # meters
    seed: Optional[int] = None
    emergency_rate: float = 0.005  # Probability of emergency vehicle per step

    # ─── Mixed traffic ratios (must sum to 1.0) ───
    # These define the proportion of each vehicle type in traffic flow.
    car_ratio: float = 0.55
    bus_ratio: float = 0.05
    e_bike_ratio: float = 0.25
    bicycle_ratio: float = 0.10
    pedestrian_ratio: float = 0.05
    # Emergency vehicles are generated separately via emergency_rate

    # ─── Behavior modifiers ───
    e_bike_lane_violation_rate: float = 0.15  # E-bikes entering car lanes
    pedestrian_jaywalking_rate: float = 0.10   # Pedestrians crossing on red
    bike_red_light_rate: float = 0.05          # Bikes running red lights

    def __post_init__(self):
        total = (self.car_ratio + self.bus_ratio + self.e_bike_ratio +
                 self.bicycle_ratio + self.pedestrian_ratio)
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"Vehicle ratios must sum to 1.0, got {total:.3f}. "
                f"car={self.car_ratio} bus={self.bus_ratio} "
                f"e_bike={self.e_bike_ratio} bicycle={self.bicycle_ratio} "
                f"pedestrian={self.pedestrian_ratio}"
            )

    def get_mix_ratios(self) -> Dict[VehicleType, float]:
        """Return vehicle type -> probability mapping."""
        return {
            VehicleType.CAR: self.car_ratio,
            VehicleType.BUS: self.bus_ratio,
            VehicleType.E_BIKE: self.e_bike_ratio,
            VehicleType.BICYCLE: self.bicycle_ratio,
            VehicleType.PEDESTRIAN: self.pedestrian_ratio,
        }


@dataclass
class Vehicle:
    """Vehicle model with type-specific properties."""
    id: str
    approach: int
    position: float
    speed: float
    vehicle_type: VehicleType = VehicleType.CAR
    waiting: bool = False
    is_emergency: bool = False

    # Computed from vehicle_type - set during creation
    _type_info: Optional[VehicleTypeInfo] = field(default=None, repr=False)

    @property
    def type_info(self) -> VehicleTypeInfo:
        if self._type_info is None:
            self._type_info = VEHICLE_TYPES[self.vehicle_type]
        return self._type_info

    @property
    def length(self) -> float:
        return self.type_info.length

    @property
    def space_occupancy(self) -> float:
        return self.type_info.space_occupancy

    @property
    def can_respect_signal(self) -> bool:
        return self.type_info.respects_signal

    @property
    def has_priority(self) -> bool:
        return self.type_info.has_priority

    def get_effective_speed(self, road_speed_limit: float) -> float:
        """
        Get the actual speed this vehicle will travel at,
        considering its own capabilities and the road speed limit.
        """
        info = self.type_info
        # Vehicle speed is min(its max, road limit)
        effective = min(info.speed_normal, road_speed_limit)
        # Add some randomness (±15%)
        effective *= np.random.uniform(0.85, 1.15)
        return max(info.speed_min, min(info.speed_max, effective))

    def should_obey_signal(self, violation_rate: float = 0.0) -> bool:
        """
        Determine if this vehicle respects the traffic signal.
        Some vehicle types may violate signals at certain rates.
        """
        if self.type_info.has_priority:
            return False  # Emergency always goes
        if not self.type_info.respects_signal:
            return np.random.random() > violation_rate
        return True


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
    Lightweight traffic simulation engine with mixed traffic support.

    Provides realistic traffic data for LLM decision making.
    Supports cars, buses, electric bikes, bicycles, pedestrians,
    and emergency vehicles — each with distinct physical properties.
    """
    
    def __init__(self, config: Optional[SimulationConfig] = None):
        self.config = config or SimulationConfig()
        self.network = RoadNetwork()
        self.time: float = 0.0
        self.step_count: int = 0
        self._vehicle_counter: int = 0

        # Mixed traffic stats
        self._type_counts: Dict[VehicleType, int] = defaultdict(int)

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

        # Count vehicles by type per approach
        type_breakdown = {}
        for approach in range(ix.approaches):
            for v in ix.vehicles[approach]:
                type_name = v.vehicle_type.value
                if type_name not in type_breakdown:
                    type_breakdown[type_name] = {"total": 0, "waiting": 0}
                type_breakdown[type_name]["total"] += 1
                if v.waiting:
                    type_breakdown[type_name]["waiting"] += 1

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
            vehicle_type_breakdown=type_breakdown,
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
        self._type_counts.clear()

        for ix in self.network.intersections.values():
            ix.vehicles.clear()
            ix.current_phase = "NS_GREEN"
            ix.phase_timer = 0.0
            ix.total_wait_time = 0.0
            ix.total_served = 0

    def _pick_vehicle_type(self) -> VehicleType:
        """Pick a vehicle type based on configured mix ratios."""
        ratios = self.config.get_mix_ratios()
        types = list(ratios.keys())
        probs = [ratios[t] for t in types]
        idx = np.random.choice(len(types), p=probs)
        return types[idx]

    def _generate_vehicles(self, ix: Intersection, dt: float) -> None:
        for approach in range(ix.approaches):
            if np.random.random() < self.config.arrival_rate * dt:
                # Check if this is an emergency vehicle
                is_emergency = np.random.random() < self.config.emergency_rate

                if is_emergency:
                    vtype = VehicleType.EMERGENCY
                else:
                    vtype = self._pick_vehicle_type()

                self._vehicle_counter += 1
                type_info = VEHICLE_TYPES[vtype]
                speed = type_info.speed_normal * np.random.uniform(0.85, 1.15)
                speed = max(type_info.speed_min, min(type_info.speed_max, speed))

                v = Vehicle(
                    id=f"v_{self._vehicle_counter}",
                    approach=approach,
                    position=self.config.road_length,
                    speed=speed,
                    vehicle_type=vtype,
                    is_emergency=is_emergency,
                    _type_info=type_info,
                )
                ix.vehicles[approach].append(v)
                self._type_counts[vtype] += 1

                # Emergency vehicles trigger immediate green for their approach
                if is_emergency:
                    self._handle_emergency(ix, approach)
    
    def _update_vehicles(self, ix: Intersection, dt: float) -> None:
        for approach in range(ix.approaches):
            to_remove = []
            
            for i, v in enumerate(ix.vehicles[approach]):
                at_intersection = v.position <= 5.0
                has_green = self._has_green(ix, approach)

                # Determine if this vehicle should obey the signal
                if v.vehicle_type == VehicleType.PEDESTRIAN:
                    obey = v.should_obey_signal(self.config.pedestrian_jaywalking_rate)
                elif v.vehicle_type == VehicleType.BICYCLE:
                    obey = v.should_obey_signal(self.config.bike_red_light_rate)
                elif v.vehicle_type == VehicleType.E_BIKE:
                    obey = v.should_obey_signal(self.config.e_bike_lane_violation_rate)
                else:
                    obey = v.should_obey_signal()

                if at_intersection and not has_green and obey:
                    # Red light — stop (unless signal-violating type)
                    v.speed = 0
                    v.waiting = True
                    ix.total_wait_time += dt
                else:
                    # Green light or vehicle ignores signal
                    effective_speed = v.get_effective_speed(self.config.speed_limit)
                    v.speed = effective_speed
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
        metrics: Dict[str, Any] = {
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

        # Mixed traffic breakdown
        metrics["vehicle_type_counts"] = {
            vtype.value: count for vtype, count in self._type_counts.items()
        }
        
        return metrics
