"""
Grid Simulation — 3x3 intersection network with vehicle flow.

Vehicles move between intersections, creating realistic traffic patterns.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from traffic_agent.simulation.engine import (
    GREEN_APPROACHES,
    PHASE_DURATIONS,
    SIGNAL_PHASES,
    Intersection,
    RoadNetwork,
    SimulationConfig,
    SimulationEngine,
    Vehicle,
)
from traffic_agent.simulation.signal_controller import (
    SignalController,
    SignalState,
    crossroad_plan,
)
from traffic_agent.tools.traffic_tools import IntersectionState


@dataclass
class RoadSegment:
    """A road segment connecting two intersections."""
    from_id: str
    to_id: str
    length: float = 200.0       # meters
    speed_limit: float = 13.89  # m/s (50 km/h)
    capacity: int = 50          # max vehicles
    vehicles: List[Vehicle] = field(default_factory=list)


class GridSimulation:
    """
    3x3 grid traffic simulation.

    Layout:
        ix_0_0 --- ix_0_1 --- ix_0_2
          |          |          |
        ix_1_0 --- ix_1_1 --- ix_1_2
          |          |          |
        ix_2_0 --- ix_2_1 --- ix_2_2

    Vehicles:
    - Generated at boundary intersections
    - Flow through the grid
    - Exit at boundary intersections
    """

    def __init__(self, config: Optional[SimulationConfig] = None):
        self.config = config or SimulationConfig()
        self.rows = 3
        self.cols = 3
        self.time: float = 0.0
        self.step_count: int = 0

        # Road network
        self.intersections: Dict[str, Intersection] = {}
        self.segments: Dict[str, RoadSegment] = {}

        # Signal controllers (one per intersection)
        self.controllers: Dict[str, SignalController] = {}

        # Metrics
        self.total_vehicles_generated = 0
        self.total_vehicles_completed = 0
        self.total_wait_time = 0.0

        # Vehicle ID counter
        self._vehicle_counter = 0

        if self.config.seed is not None:
            np.random.seed(self.config.seed)

        self._build_grid()

    def _build_grid(self) -> None:
        """Build the 3x3 grid network."""
        # Create intersections
        for row in range(self.rows):
            for col in range(self.cols):
                ix_id = f"ix_{row}_{col}"
                self.intersections[ix_id] = Intersection(id=ix_id)

        # Create road segments (horizontal)
        for row in range(self.rows):
            for col in range(self.cols - 1):
                from_id = f"ix_{row}_{col}"
                to_id = f"ix_{row}_{col+1}"
                key = f"{from_id}->{to_id}"
                self.segments[key] = RoadSegment(from_id=from_id, to_id=to_id)

        # Create road segments (vertical)
        for row in range(self.rows - 1):
            for col in range(self.cols):
                from_id = f"ix_{row}_{col}"
                to_id = f"ix_{row+1}_{col}"
                key = f"{from_id}->{to_id}"
                self.segments[key] = RoadSegment(from_id=from_id, to_id=to_id)

        # Create signal controllers for each intersection
        plan = crossroad_plan()
        for ix_id in self.intersections:
            self.controllers[ix_id] = SignalController(plan)

    def get_neighbors(self, ix_id: str) -> List[str]:
        """Get neighbor intersection IDs."""
        row, col = self._parse_id(ix_id)
        neighbors = []

        if col > 0: neighbors.append(f"ix_{row}_{col-1}")
        if col < self.cols - 1: neighbors.append(f"ix_{row}_{col+1}")
        if row > 0: neighbors.append(f"ix_{row-1}_{col}")
        if row < self.rows - 1: neighbors.append(f"ix_{row+1}_{col}")

        return neighbors

    def get_graph(self) -> Dict[str, List[str]]:
        """Get adjacency list for all intersections."""
        return {
            ix_id: self.get_neighbors(ix_id)
            for ix_id in self.intersections
        }

    def get_signal_state(self, ix_id: str) -> SignalState:
        """Get full signal controller state for an intersection."""
        return self.controllers[ix_id].get_state()

    def get_state(self, ix_id: str) -> IntersectionState:
        """Get current state for an intersection."""
        ix = self.intersections[ix_id]
        controller = self.controllers[ix_id]
        signal_state = controller.get_state()

        # Count vehicles approaching from each direction
        queue_north = self._count_approaching(ix_id, 0)  # from north
        queue_south = self._count_approaching(ix_id, 2)  # from south
        queue_east = self._count_approaching(ix_id, 1)   # from east
        queue_west = self._count_approaching(ix_id, 3)   # from west

        # Count waiting vehicles (at intersection, red light)
        wait_north = self._count_waiting(ix_id, 0)
        wait_south = self._count_waiting(ix_id, 2)
        wait_east = self._count_waiting(ix_id, 1)
        wait_west = self._count_waiting(ix_id, 3)

        # Check for emergency vehicles
        emergency = False
        emergency_approach = None
        for seg_key, seg in self.segments.items():
            if seg.to_id == ix_id:
                for v in seg.vehicles:
                    if v.is_emergency:
                        emergency = True
                        emergency_approach = v.approach
                        break
                if emergency:
                    break

        return IntersectionState(
            intersection_id=ix_id,
            timestamp=self.time,
            queue_north=queue_north,
            queue_south=queue_south,
            queue_east=queue_east,
            queue_west=queue_west,
            wait_north=wait_north * 2.0,
            wait_south=wait_south * 2.0,
            wait_east=wait_east * 2.0,
            wait_west=wait_west * 2.0,
            current_phase=signal_state.current_phase,
            phase_duration=signal_state.phase_duration,
            base_duration=signal_state.base_duration,
            emergency=emergency,
            emergency_approach=emergency_approach,
        )

    def apply_decision(self, ix_id: str, decision: Dict) -> None:
        """Apply LLM decision to intersection.

        Supports two modes:
        - timing adjustment: {"adjustment": int} — applies ±10s to current green phase
        - phase switch: {"phase": str} — directly switches to a new phase
        """
        ix = self.intersections[ix_id]
        controller = self.controllers[ix_id]

        # Support timing adjustment (the ±10s model)
        adjustment = decision.get("adjustment")
        if adjustment is not None and isinstance(adjustment, (int, float)):
            controller.apply_adjustment(int(adjustment))

        # Support direct phase switch (legacy)
        new_phase = decision.get("phase")
        if new_phase and new_phase != ix.current_phase:
            ix.current_phase = new_phase
            ix.phase_timer = 0.0
            # Sync controller state
            signal_phases = ["NS_GREEN", "NS_YELLOW", "ALL_RED_1",
                             "EW_GREEN", "EW_YELLOW", "ALL_RED_2"]
            if new_phase in signal_phases:
                controller._phase_index = signal_phases.index(new_phase)
            controller._phase_elapsed = 0.0
            controller._adjustment = 0
            controller._adjustment_applied = False

    def step(self) -> None:
        """Advance simulation by one time step."""
        dt = self.config.dt

        # 1. Generate vehicles at boundaries
        self._generate_boundary_vehicles(dt)

        # 2. Update signal phases (auto-cycle with yellow/all-red)
        for ix in self.intersections.values():
            self._update_signal(ix, dt)

        # 3. Move vehicles through segments (includes intersection routing)
        self._move_vehicles(dt)

        # 4. Update signal timers
        for ix in self.intersections.values():
            ix.phase_timer += dt

        self.time += dt
        self.step_count += 1

    def get_metrics(self) -> Dict[str, float]:
        """Get simulation metrics."""
        total_queue = sum(
            self._count_approaching(ix_id, a)
            for ix_id in self.intersections
            for a in range(4)
        )

        total_waiting = sum(
            self._count_waiting(ix_id, a)
            for ix_id in self.intersections
            for a in range(4)
        )

        avg_wait = self.total_wait_time / max(1, self.total_vehicles_completed)

        return {
            "time": self.time,
            "total_queue": total_queue,
            "total_waiting": total_waiting,
            "vehicles_generated": self.total_vehicles_generated,
            "vehicles_completed": self.total_vehicles_completed,
            "avg_wait_time": avg_wait,
            "throughput": self.total_vehicles_completed / max(1, self.time),
        }

    def reset(self) -> None:
        """Reset simulation."""
        self.time = 0.0
        self.step_count = 0
        self._vehicle_counter = 0
        self.total_vehicles_generated = 0
        self.total_vehicles_completed = 0
        self.total_wait_time = 0.0

        for ix in self.intersections.values():
            ix.vehicles.clear()
            ix.current_phase = "NS_GREEN"
            ix.phase_timer = 0.0

        for controller in self.controllers.values():
            controller.reset()

        for seg in self.segments.values():
            seg.vehicles.clear()

    # ─── Private Methods ───────────────────────────────────────

    def _parse_id(self, ix_id: str) -> Tuple[int, int]:
        """Parse intersection ID to (row, col)."""
        parts = ix_id.split("_")
        return int(parts[1]), int(parts[2])

    def _update_signal(self, ix: Intersection, dt: float) -> None:
        """Auto-cycle signal phases using the signal controller."""
        controller = self.controllers[ix.id]
        phase_changed = controller.step(dt)
        if phase_changed:
            state = controller.get_state()
            ix.current_phase = state.current_phase
            ix.phase_timer = 0.0
        else:
            ix.phase_timer = controller._phase_elapsed

    def _generate_boundary_vehicles(self, dt: float) -> None:
        """Generate vehicles at boundary intersections."""
        boundaries = [
            (0, col) for col in range(self.cols)  # Top row
        ] + [
            (self.rows - 1, col) for col in range(self.cols)  # Bottom row
        ] + [
            (row, 0) for row in range(1, self.rows - 1)  # Left column
        ] + [
            (row, self.cols - 1) for row in range(1, self.rows - 1)  # Right column
        ]

        for row, col in boundaries:
            if np.random.random() < self.config.arrival_rate * dt:
                self._vehicle_counter += 1
                self.total_vehicles_generated += 1

                # Random destination
                dest_row = np.random.randint(0, self.rows)
                dest_col = np.random.randint(0, self.cols)

                v = Vehicle(
                    id=f"v_{self._vehicle_counter}",
                    approach=np.random.randint(0, 4),
                    position=self.config.road_length,
                    speed=self.config.speed_limit,
                )

                # Add to segment approaching this intersection
                self._add_vehicle_to_segment(row, col, v)

    def _add_vehicle_to_segment(self, row: int, col: int, vehicle: Vehicle) -> None:
        """Add vehicle to a segment approaching the intersection."""
        # Find an incoming segment
        candidates = []
        if row > 0:  # From north
            candidates.append(f"ix_{row-1}_{col}->ix_{row}_{col}")
        if row < self.rows - 1:  # From south
            candidates.append(f"ix_{row+1}_{col}->ix_{row}_{col}")
        if col > 0:  # From west
            candidates.append(f"ix_{row}_{col-1}->ix_{row}_{col}")
        if col < self.cols - 1:  # From east
            candidates.append(f"ix_{row}_{col+1}->ix_{row}_{col}")

        if candidates:
            seg_key = np.random.choice(candidates)
            if seg_key in self.segments:
                self.segments[seg_key].vehicles.append(vehicle)

    def _move_vehicles(self, dt: float) -> None:
        """Move vehicles through road segments, routing at intersections."""
        for seg_key, seg in self.segments.items():
            to_remove = []

            for i, v in enumerate(seg.vehicles):
                # Vehicle is at the intersection (position <= 5.0)
                if v.position <= 5.0:
                    to_ix = self.intersections.get(seg.to_id)
                    if to_ix:
                        has_green = self._has_green(to_ix, v.approach)
                        if not has_green:
                            # Red light — wait
                            v.speed = 0
                            v.waiting = True
                            self.total_wait_time += dt
                            continue
                        else:
                            # Green light — route through intersection
                            next_seg = self._route_vehicle(seg.to_id, v)
                            if next_seg is None:
                                self.total_vehicles_completed += 1
                            to_remove.append(i)
                            continue

                # Check if vehicle will cross the intersection this step
                new_pos = v.position - seg.speed_limit * dt
                if v.position > 5.0 and new_pos <= 5.0:
                    to_ix = self.intersections.get(seg.to_id)
                    if to_ix:
                        has_green = self._has_green(to_ix, v.approach)
                        if not has_green:
                            # Stop at intersection boundary
                            v.position = 5.0
                            v.speed = 0
                            v.waiting = True
                            self.total_wait_time += dt
                            continue
                        else:
                            # Route through intersection
                            next_seg = self._route_vehicle(seg.to_id, v)
                            if next_seg is None:
                                self.total_vehicles_completed += 1
                            to_remove.append(i)
                            continue

                # Move forward normally
                v.speed = seg.speed_limit
                v.waiting = False
                v.position -= v.speed * dt

                if v.position <= -5.0:
                    to_remove.append(i)

            for i in sorted(to_remove, reverse=True):
                seg.vehicles.pop(i)

    def _route_vehicle(self, from_id: str, vehicle: Vehicle) -> Optional[str]:
        """Route vehicle to next segment. Returns segment key or None if completed."""
        from_row, from_col = self._parse_id(from_id)

        # Vehicle continues in its current direction (physical logic)
        # approach 0=N(→up), 1=E(→right), 2=S(→down), 3=W(→left)
        directions = [
            (-1, 0),  # N -> go up
            (0, 1),   # E -> go right
            (1, 0),   # S -> go down
            (0, -1),  # W -> go left
        ]

        dr, dc = directions[vehicle.approach]
        to_row, to_col = from_row + dr, from_col + dc

        # Check if out of bounds
        if to_row < 0 or to_row >= self.rows or to_col < 0 or to_col >= self.cols:
            return None

        to_id = f"ix_{to_row}_{to_col}"
        seg_key = f"{from_id}->{to_id}"

        if seg_key in self.segments:
            # Move vehicle to next segment, keeping original approach
            vehicle.position = self.config.road_length
            self.segments[seg_key].vehicles.append(vehicle)
            return seg_key

        # No direct road — try turning (pick a valid adjacent road)
        turn_candidates = []
        for new_approach, (ndr, ndc) in enumerate(directions):
            nr, nc = from_row + ndr, from_col + ndc
            if 0 <= nr < self.rows and 0 <= nc < self.cols:
                new_to = f"ix_{nr}_{nc}"
                new_key = f"{from_id}->{new_to}"
                if new_key in self.segments:
                    turn_candidates.append((new_approach, new_key))

        if turn_candidates:
            new_approach, new_key = turn_candidates[np.random.randint(len(turn_candidates))]
            vehicle.position = self.config.road_length
            vehicle.approach = new_approach
            self.segments[new_key].vehicles.append(vehicle)
            return new_key

        return None

    def _has_green(self, ix: Intersection, approach: int) -> bool:
        """Check if approach has green light."""
        green_list = GREEN_APPROACHES.get(ix.current_phase, [])
        return approach in green_list

    def _count_approaching(self, ix_id: str, approach: int) -> int:
        """Count vehicles approaching from a direction."""
        count = 0
        for seg_key, seg in self.segments.items():
            if seg.to_id == ix_id:
                # Check if vehicle's approach matches
                for v in seg.vehicles:
                    if v.approach == approach:
                        count += 1
        return count

    def _count_waiting(self, ix_id: str, approach: int) -> int:
        """Count vehicles waiting at intersection."""
        count = 0
        for seg_key, seg in self.segments.items():
            if seg.to_id == ix_id:
                for v in seg.vehicles:
                    if v.approach == approach and v.waiting:
                        count += 1
        return count
