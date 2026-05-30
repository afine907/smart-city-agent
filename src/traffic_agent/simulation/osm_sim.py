"""
OSM Simulation — Traffic simulation using real OpenStreetMap road networks.

Extends the grid simulation concept to work with arbitrary road network
topologies loaded from OSM data.
"""

from __future__ import annotations


import math
from dataclasses import dataclass, field

import numpy as np
from numpy.random import Generator, PCG64

from traffic_agent.simulation.engine import (
    GREEN_APPROACHES,
    PHASE_DURATIONS,
    SIGNAL_PHASES,
    Intersection,
    SimulationConfig,
    Vehicle,
)
from traffic_agent.simulation.osm import OSMNetwork
from traffic_agent.simulation.router import RoutePlanner
from traffic_agent.tools.traffic_tools import IntersectionState


@dataclass
class OSMSegment:
    """A road segment in the OSM simulation."""
    road_id: str
    from_id: str
    to_id: str
    length: float
    speed_limit: float  # m/s
    lanes: int
    name: str
    oneway: bool
    vehicles: list[Vehicle] = field(default_factory=list)


class OSMSimulation:
    """
    Traffic simulation on real OpenStreetMap road networks.

    Unlike the 3x3 grid, this supports arbitrary topologies:
    - T-junctions
    - Roundabouts (modeled as complex intersections)
    - Uneven road lengths
    - Variable speed limits
    - Multiple lanes

    Usage:
        # Load from place name (requires network)
        sim = OSMSimulation.from_place("Manhattan, New York")

        # Load from preset
        sim = OSMSimulation.from_preset("manhattan")

        # Load from dict
        sim = OSMSimulation.from_dict(data)
    """

    def __init__(self, osm_network: OSMNetwork, config: SimulationConfig | None = None):
        self.config = config or SimulationConfig()
        self.osm = osm_network
        self.time: float = 0.0
        self.step_count: int = 0

        # Build simulation segments from OSM data
        self.intersections: dict[str, Intersection] = {}
        self.segments: dict[str, OSMSegment] = {}

        # Metrics
        self.total_vehicles_generated = 0
        self.total_vehicles_completed = 0
        self.total_wait_time = 0.0
        self._vehicle_counter = 0

        # Track which intersections are boundary (sources/sinks)
        self.boundary_intersections: set = set()

        # Route planner for shortest-path routing
        self.router = RoutePlanner()

        # Vehicle destinations: vehicle_id -> destination intersection_id
        self.vehicle_destinations: dict[str, str] = {}

        # Use local random generator to avoid global state pollution
        self._rng = Generator(PCG64(self.config.seed))

        self._build_network()

    @classmethod
    def from_place(cls, place_name: str, config: SimulationConfig | None = None) -> "OSMSimulation":
        """Create simulation from OSM place name."""
        osm = OSMNetwork.from_place(place_name)
        return cls(osm, config)

    @classmethod
    def from_bbox(cls, north: float, south: float, east: float, west: float,
                  config: SimulationConfig | None = None) -> "OSMSimulation":
        """Create simulation from bounding box."""
        osm = OSMNetwork.from_bbox(north, south, east, west)
        return cls(osm, config)

    @classmethod
    def from_preset(cls, preset_name: str, config: SimulationConfig | None = None) -> "OSMSimulation":
        """Create simulation from a preset network."""
        from traffic_agent.simulation.osm import (
            SMALL_MANHATTAN,
            WUHAN_OPTICS_VALLEY,
            SHENZHEN_LIUXIANDONG,
        )

        presets = {
            "manhattan": SMALL_MANHATTAN,
            "wuhan": WUHAN_OPTICS_VALLEY,
            "shenzhen": SHENZHEN_LIUXIANDONG,
        }

        data = presets.get(preset_name)
        if data is None:
            raise ValueError(f"Unknown preset: {preset_name}. Available: {list(presets.keys())}")

        osm = OSMNetwork.from_dict(data)
        return cls(osm, config)

    @classmethod
    def from_dict(cls, data: dict, config: SimulationConfig | None = None) -> "OSMSimulation":
        """Create simulation from dictionary."""
        osm = OSMNetwork.from_dict(data)
        return cls(osm, config)

    def _build_network(self) -> None:
        """Build simulation network from OSM data."""
        # Create intersections
        for ix_id, osm_ix in self.osm.intersections.items():
            self.intersections[ix_id] = Intersection(id=osm_ix.id)

        # Create road segments
        for road_id, osm_road in self.osm.roads.items():
            speed_ms = osm_road.speed_limit / 3.6  # km/h to m/s

            self.segments[road_id] = OSMSegment(
                road_id=road_id,
                from_id=osm_road.from_intersection,
                to_id=osm_road.to_intersection,
                length=osm_road.length,
                speed_limit=speed_ms,
                lanes=osm_road.lanes,
                name=osm_road.name,
                oneway=osm_road.oneway,
            )

            # For bidirectional roads, create a reverse segment
            if not osm_road.oneway:
                reverse_id = f"{road_id}_rev"
                self.segments[reverse_id] = OSMSegment(
                    road_id=reverse_id,
                    from_id=osm_road.to_intersection,
                    to_id=osm_road.from_intersection,
                    length=osm_road.length,
                    speed_limit=speed_ms,
                    lanes=osm_road.lanes,
                    name=osm_road.name,
                    oneway=False,
                )

        # Identify boundary intersections:
        # For bidirectional roads, all intersections may have >=2 in/out.
        # Instead, identify boundaries as intersections with fewer total connections
        # (edge/corner of the network) or those at the network perimeter.
        incoming_count: dict[str, int] = {}
        outgoing_count: dict[str, int] = {}
        for seg in self.segments.values():
            if seg.road_id.startswith("virtual"):
                continue
            outgoing_count[seg.from_id] = outgoing_count.get(seg.from_id, 0) + 1
            incoming_count[seg.to_id] = incoming_count.get(seg.to_id, 0) + 1

        all_ids = set(self.intersections.keys())
        max_connections = max(
            incoming_count.get(ix_id, 0) + outgoing_count.get(ix_id, 0)
            for ix_id in all_ids
        ) if all_ids else 0

        for ix_id in all_ids:
            inc = incoming_count.get(ix_id, 0)
            out = outgoing_count.get(ix_id, 0)
            total = inc + out
            # Boundary: fewer connections than max (edge of network)
            # or fewer than 2 incoming/outgoing (asymmetric)
            if total < max_connections or inc < 2 or out < 2:
                self.boundary_intersections.add(ix_id)

        # Build route planner graph
        self.router.build_graph(self.segments)

        # Pre-create virtual segments for boundaries with no incoming roads
        self._virtual_segments: dict[str, str] = {}  # ix_id -> virtual road_id
        for ix_id in self.boundary_intersections:
            has_incoming = any(seg.to_id == ix_id for seg in self.segments.values())
            if not has_incoming:
                road_id = f"virtual_{ix_id}"
                self.segments[road_id] = OSMSegment(
                    road_id=road_id,
                    from_id=f"boundary_{ix_id}",
                    to_id=ix_id,
                    length=self.config.road_length,
                    speed_limit=self.config.speed_limit,
                    lanes=2,
                    name="virtual",
                    oneway=True,
                )
                self._virtual_segments[ix_id] = road_id

    def get_neighbors(self, ix_id: str) -> list[str]:
        """Get neighbor intersection IDs."""
        return self.osm.get_neighbors(ix_id)

    def get_graph(self) -> dict[str, list[str]]:
        """Get adjacency list for all intersections."""
        return {
            ix_id: self.get_neighbors(ix_id)
            for ix_id in self.intersections
        }

    def get_state(self, ix_id: str) -> IntersectionState:
        """Get current state for an intersection. Pure getter, no side effects."""
        ix = self.intersections.get(ix_id)
        if ix is None:
            return IntersectionState(intersection_id=ix_id, timestamp=self.time)

        # Count vehicles approaching from each direction
        queue_north = self._count_approaching(ix_id, 0)
        queue_south = self._count_approaching(ix_id, 2)
        queue_east = self._count_approaching(ix_id, 1)
        queue_west = self._count_approaching(ix_id, 3)

        wait_north = self._count_waiting(ix_id, 0) * 2.0
        wait_south = self._count_waiting(ix_id, 2) * 2.0
        wait_east = self._count_waiting(ix_id, 1) * 2.0
        wait_west = self._count_waiting(ix_id, 3) * 2.0

        # Check for emergency vehicles (read-only)
        emergency = False
        emergency_approach = None
        for seg in self.segments.values():
            if seg.to_id == ix_id:
                for v in seg.vehicles:
                    if v.is_emergency:
                        emergency = True
                        emergency_approach = self._road_to_approach(seg.from_id, ix_id)
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
            wait_north=wait_north,
            wait_south=wait_south,
            wait_east=wait_east,
            wait_west=wait_west,
            current_phase=ix.current_phase,
            phase_duration=ix.phase_timer,
            emergency=emergency,
            emergency_approach=emergency_approach,
        )

    def apply_decision(self, ix_id: str, decision: dict) -> None:
        """Apply LLM decision to intersection."""
        ix = self.intersections.get(ix_id)
        if ix is None:
            return

        new_phase = decision.get("phase", ix.current_phase)
        if new_phase != ix.current_phase:
            ix.current_phase = new_phase
            ix.phase_timer = 0.0

    def step(self) -> None:
        """Advance simulation by one time step."""
        dt = self.config.dt

        # 1. Generate vehicles at boundary intersections
        self._generate_boundary_vehicles(dt)

        # 2. Update signal phases (auto-cycle with yellow/all-red)
        for ix in self.intersections.values():
            self._update_signal(ix, dt)

        # 3. Move vehicles through segments
        self._move_vehicles(dt)

        # 4. Process vehicles arriving at intersections
        self._process_intersections(dt)

        # 5. Update signal timers
        for ix in self.intersections.values():
            ix.phase_timer += dt

        self.time += dt
        self.step_count += 1

    def get_metrics(self) -> dict[str, float]:
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
            "num_intersections": len(self.intersections),
            "num_segments": len(self.segments),
        }

    def reset(self) -> None:
        """Reset simulation."""
        self.time = 0.0
        self.step_count = 0
        self._vehicle_counter = 0
        self.total_vehicles_generated = 0
        self.total_vehicles_completed = 0
        self.total_wait_time = 0.0
        self.vehicle_destinations.clear()
        self.router.clear_cache()

        for ix in self.intersections.values():
            ix.current_phase = "NS_GREEN"
            ix.phase_timer = 0.0

        for seg in self.segments.values():
            seg.vehicles.clear()

    def export_geojson(self) -> dict:
        """Export current state as GeoJSON for visualization."""
        return self.osm.to_geojson()

    # ─── Private Methods ───────────────────────────────────────

    def _road_to_approach(self, from_id: str, to_id: str) -> int:
        """
        Determine the approach direction (0=N, 1=E, 2=S, 3=W)
        based on the relative positions of two intersections.
        Uses atan2 for accurate bearing calculation on diagonal roads.
        """
        from_ix = self.osm.intersections.get(from_id)
        to_ix = self.osm.intersections.get(to_id)

        if not from_ix or not to_ix:
            return 0

        # Calculate bearing from 'from' to 'to'
        dlat = to_ix.lat - from_ix.lat
        dlon = to_ix.lon - from_ix.lon

        # atan2(dlon, dlat) gives bearing: 0=N, π/2=E, ±π=S, -π/2=W
        bearing = math.atan2(dlon, dlat)

        # Map bearing to closest cardinal direction (0=N, 1=E, 2=S, 3=W)
        # Check wrap-around (South near ±π) first
        if bearing >= 3 * math.pi / 4 or bearing < -3 * math.pi / 4:
            return 2  # S (bearing near ±π: 135° to 225°)
        elif bearing >= math.pi / 4:
            return 1  # E (bearing π/4 to 3π/4: 45° to 135°)
        elif bearing >= -math.pi / 4:
            return 0  # N (bearing -π/4 to π/4: -45° to 45°)
        else:
            return 3  # W (bearing -3π/4 to -π/4: -135° to -45°)

    def _generate_boundary_vehicles(self, dt: float) -> None:
        """Generate vehicles at boundary intersections."""
        all_ids = list(self.intersections.keys())
        if len(all_ids) < 2:
            return

        for ix_id in self.boundary_intersections:
            if self._rng.random() < self.config.arrival_rate * dt:
                self._vehicle_counter += 1
                self.total_vehicles_generated += 1

                # Assign random destination (different from source)
                dest = ix_id
                while dest == ix_id and len(all_ids) > 1:
                    dest = all_ids[self._rng.integers(len(all_ids))]
                self.vehicle_destinations[f"v_{self._vehicle_counter}"] = dest

                # Create vehicle approaching this intersection
                approach = int(self._rng.integers(0, 4))
                v = Vehicle(
                    id=f"v_{self._vehicle_counter}",
                    approach=approach,
                    position=self.config.road_length,
                    speed=self.config.speed_limit,
                )

                # Find incoming segment or create virtual approach
                self._add_vehicle_to_boundary(ix_id, v)

    def _add_vehicle_to_boundary(self, ix_id: str, vehicle: Vehicle) -> None:
        """Add a vehicle approaching a boundary intersection.

        The vehicle's approach is set based on the actual direction of the
        road segment it's on, so signal light checks work correctly.
        """
        # Find segments that lead to this intersection
        incoming = [seg for seg in self.segments.values() if seg.to_id == ix_id]

        if incoming:
            # Add to a random incoming segment
            seg = incoming[self._rng.integers(len(incoming))]
            vehicle.position = seg.length
            vehicle.speed = seg.speed_limit
            # Set approach: direction FROM the intersection BACK to where the vehicle came from
            # This tells the signal controller which side the vehicle is approaching from
            vehicle.approach = self._road_to_approach(ix_id, seg.from_id)
            seg.vehicles.append(vehicle)
        elif ix_id in self._virtual_segments:
            # Use pre-created virtual segment
            seg = self.segments[self._virtual_segments[ix_id]]
            vehicle.position = seg.length
            vehicle.speed = seg.speed_limit
            seg.vehicles.append(vehicle)
        else:
            # No path available — vehicle can't enter
            self.total_vehicles_completed += 1

    def _move_vehicles(self, dt: float) -> None:
        """Move vehicles through road segments.

        Vehicles at position <= 5.0 are at the intersection and will be
        handled by _process_intersections. This method only moves vehicles
        that are still approaching (position > 5.0).
        """
        for seg in self.segments.values():
            to_remove = []

            for i, v in enumerate(seg.vehicles):
                # Skip vehicles at the intersection (handled by _process_intersections)
                if v.position <= 5.0:
                    continue

                # Move forward
                v.speed = seg.speed_limit
                v.waiting = False
                v.position -= v.speed * dt

                # Vehicle passed through intersection without being processed
                # (shouldn't happen normally, but safety catch)
                if v.position <= -5.0:
                    to_remove.append(i)

            # Remove vehicles that reached the end
            for i in sorted(to_remove, reverse=True):
                seg.vehicles.pop(i)

    def _process_intersections(self, dt: float) -> None:
        """Process vehicles arriving at intersections.

        Vehicles at position <= 5.0 are at/through the intersection.
        - If past intersection (position <= 0): must route or complete
        - If at intersection with green: route to next segment
        - If at intersection with red: wait
        """
        for seg in list(self.segments.values()):
            to_remove = []
            for i, v in enumerate(seg.vehicles):
                if v.position <= 5.0:
                    # Vehicle is at or past the intersection
                    if v.position <= 0:
                        # Already past the intersection — force route
                        next_seg_id = self._route_vehicle(seg.to_id, v)
                        if next_seg_id is None:
                            self.total_vehicles_completed += 1
                        to_remove.append(i)
                    else:
                        # At intersection boundary — check signal
                        to_ix = self.intersections.get(seg.to_id)
                        if to_ix:
                            has_green = self._has_green(to_ix, v.approach)
                            if has_green:
                                next_seg_id = self._route_vehicle(seg.to_id, v)
                                if next_seg_id is None:
                                    self.total_vehicles_completed += 1
                                to_remove.append(i)
                            else:
                                # Red light — wait
                                v.speed = 0
                                v.waiting = True
                                self.total_wait_time += dt

            # Remove routed/completed vehicles from this segment
            for i in sorted(to_remove, reverse=True):
                seg.vehicles.pop(i)

    def _route_vehicle(self, from_id: str, vehicle: Vehicle) -> str | None:
        """
        Route vehicle to next segment using shortest-path routing.
        Returns segment ID or None if completed.
        """
        dest = self.vehicle_destinations.get(vehicle.id)

        # If already at destination, vehicle completes its journey
        if dest is not None and dest == from_id:
            self.vehicle_destinations.pop(vehicle.id, None)
            return None

        # If no destination set, pick random exit
        if dest is None:
            self.vehicle_destinations.pop(vehicle.id, None)
            outgoing = [seg for seg in self.segments.values() if seg.from_id == from_id]
            if not outgoing:
                return None
            next_seg = outgoing[self._rng.integers(len(outgoing))]
            vehicle.position = next_seg.length
            # approach: direction from intersection back to vehicle origin
            vehicle.approach = self._road_to_approach(next_seg.to_id, from_id)
            next_seg.vehicles.append(vehicle)
            return next_seg.road_id

        # Use router to find next hop
        next_node = self.router.next_hop(from_id, dest)
        if next_node is None:
            # No path found — pick random exit
            outgoing = [seg for seg in self.segments.values() if seg.from_id == from_id]
            if not outgoing:
                self.vehicle_destinations.pop(vehicle.id, None)
                return None
            next_seg = outgoing[self._rng.integers(len(outgoing))]
            vehicle.position = next_seg.length
            vehicle.approach = self._road_to_approach(next_seg.to_id, from_id)
            next_seg.vehicles.append(vehicle)
            return next_seg.road_id

        # Find the road segment to next hop
        edge_id = self.router.get_edge_id(from_id, next_node)
        if edge_id is None or edge_id not in self.segments:
            self.vehicle_destinations.pop(vehicle.id, None)
            return None

        next_seg = self.segments[edge_id]
        vehicle.position = next_seg.length
        vehicle.approach = self._road_to_approach(next_node, from_id)
        next_seg.vehicles.append(vehicle)

        return edge_id

    def _update_signal(self, ix: Intersection, dt: float) -> None:
        """Auto-cycle signal phases with yellow and all-red transitions."""
        phase = ix.current_phase
        max_duration = PHASE_DURATIONS.get(phase, 30.0)

        if ix.phase_timer >= max_duration:
            idx = SIGNAL_PHASES.index(phase)
            next_idx = (idx + 1) % len(SIGNAL_PHASES)
            ix.current_phase = SIGNAL_PHASES[next_idx]
            ix.phase_timer = 0.0

    def _has_green(self, ix: Intersection, approach: int) -> bool:
        """Check if approach has green light."""
        green_list = GREEN_APPROACHES.get(ix.current_phase, [])
        return approach in green_list

    def _count_approaching(self, ix_id: str, approach: int) -> int:
        """Count vehicles approaching from a direction."""
        count = 0
        for seg in self.segments.values():
            if seg.to_id == ix_id:
                # Determine approach direction
                seg_approach = self._road_to_approach(seg.from_id, ix_id)
                if seg_approach == approach:
                    count += len(seg.vehicles)
        return count

    def _count_waiting(self, ix_id: str, approach: int) -> int:
        """Count vehicles waiting at intersection."""
        count = 0
        for seg in self.segments.values():
            if seg.to_id == ix_id:
                seg_approach = self._road_to_approach(seg.from_id, ix_id)
                if seg_approach == approach:
                    count += sum(1 for v in seg.vehicles if v.waiting)
        return count
