"""
OSM Simulation — Traffic simulation using real OpenStreetMap road networks.

Extends the grid simulation concept to work with arbitrary road network
topologies loaded from OSM data.
"""

from dataclasses import dataclass, field

import numpy as np

from traffic_agent.simulation.engine import Intersection, SimulationConfig, Vehicle
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

        if self.config.seed is not None:
            np.random.seed(self.config.seed)

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

        # Identify boundary intersections:
        # - Source: has outgoing but no/few incoming roads (vehicles enter here)
        # - Sink: has incoming but no/few outgoing roads (vehicles exit here)
        incoming_count = {}
        outgoing_count = {}
        for seg in self.segments.values():
            outgoing_count[seg.from_id] = outgoing_count.get(seg.from_id, 0) + 1
            incoming_count[seg.to_id] = incoming_count.get(seg.to_id, 0) + 1

        all_ids = set(self.intersections.keys())
        for ix_id in all_ids:
            inc = incoming_count.get(ix_id, 0)
            out = outgoing_count.get(ix_id, 0)
            # Boundary: fewer than 2 incoming (source) OR fewer than 2 outgoing (sink)
            if inc < 2 or out < 2:
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
        """Get current state for an intersection."""
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

        # Check for emergency vehicles
        emergency = False
        emergency_approach = None
        for seg in self.segments.values():
            if seg.to_id == ix_id:
                for v in seg.vehicles:
                    if v.is_emergency:
                        emergency = True
                        # Determine approach from road direction
                        emergency_approach = self._road_to_approach(seg.from_id, ix_id)
                        break
                if emergency:
                    break

        # Emergency triggers immediate phase change
        if emergency and emergency_approach is not None:
            target_phase = "NS_GREEN" if emergency_approach in [0, 2] else "EW_GREEN"
            if ix.current_phase != target_phase:
                ix.current_phase = target_phase
                ix.phase_timer = 0.0

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

        # 2. Move vehicles through segments
        self._move_vehicles(dt)

        # 3. Process vehicles arriving at intersections
        self._process_intersections(dt)

        # 4. Update signal timers
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
        """
        from_ix = self.osm.intersections.get(from_id)
        to_ix = self.osm.intersections.get(to_id)

        if not from_ix or not to_ix:
            return 0

        # Calculate bearing from 'from' to 'to'
        dlat = to_ix.lat - from_ix.lat
        dlon = to_ix.lon - from_ix.lon

        # Simple cardinal direction based on dominant component
        if abs(dlat) > abs(dlon):
            return 0 if dlat > 0 else 2  # N or S
        else:
            return 1 if dlon > 0 else 3  # E or W

    def _generate_boundary_vehicles(self, dt: float) -> None:
        """Generate vehicles at boundary intersections."""
        all_ids = list(self.intersections.keys())
        if len(all_ids) < 2:
            return

        for ix_id in self.boundary_intersections:
            if np.random.random() < self.config.arrival_rate * dt:
                self._vehicle_counter += 1
                self.total_vehicles_generated += 1

                # Assign random destination (different from source)
                dest = ix_id
                while dest == ix_id and len(all_ids) > 1:
                    dest = all_ids[np.random.randint(len(all_ids))]
                self.vehicle_destinations[f"v_{self._vehicle_counter}"] = dest

                # Create vehicle approaching this intersection
                approach = np.random.randint(0, 4)
                v = Vehicle(
                    id=f"v_{self._vehicle_counter}",
                    approach=approach,
                    position=self.config.road_length,
                    speed=self.config.speed_limit,
                )

                # Find incoming segment or create virtual approach
                self._add_vehicle_to_boundary(ix_id, v)

    def _add_vehicle_to_boundary(self, ix_id: str, vehicle: Vehicle) -> None:
        """Add a vehicle approaching a boundary intersection."""
        # Find segments that lead to this intersection
        incoming = [seg for seg in self.segments.values() if seg.to_id == ix_id]

        if incoming:
            # Add to the shortest incoming segment
            shortest = min(incoming, key=lambda s: s.length)
            vehicle.position = shortest.length
            vehicle.speed = shortest.speed_limit
            shortest.vehicles.append(vehicle)
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
        """Move vehicles through road segments."""
        for seg in self.segments.values():
            to_remove = []

            for i, v in enumerate(seg.vehicles):
                at_intersection = v.position <= 5.0

                if at_intersection:
                    # Check if destination intersection has green
                    to_ix = self.intersections.get(seg.to_id)
                    if to_ix:
                        has_green = self._has_green(to_ix, v.approach)
                        if not has_green:
                            v.speed = 0
                            v.waiting = True
                            self.total_wait_time += dt
                            continue

                # Move forward
                v.speed = seg.speed_limit
                v.waiting = False
                v.position -= v.speed * dt

                # Vehicle reached end of segment
                if v.position <= -5.0:
                    to_remove.append(i)

            # Remove vehicles that reached the end
            for i in sorted(to_remove, reverse=True):
                seg.vehicles.pop(i)

    def _process_intersections(self, dt: float) -> None:
        """Process vehicles arriving at intersections."""
        for ix_id, _ix in self.intersections.items():
            for seg in self.segments.values():
                if seg.to_id == ix_id:
                    arriving = [v for v in seg.vehicles if v.position <= 5.0]
                    for v in arriving:
                        next_seg = self._route_vehicle(ix_id, v)
                        if next_seg is None:
                            self.total_vehicles_completed += 1

    def _route_vehicle(self, from_id: str, vehicle: Vehicle) -> str | None:
        """
        Route vehicle to next segment using shortest-path routing.
        Returns segment ID or None if completed.
        """
        dest = self.vehicle_destinations.get(vehicle.id)

        # If no destination or already at destination, pick random exit
        if dest is None or dest == from_id:
            self.vehicle_destinations.pop(vehicle.id, None)
            outgoing = [seg for seg in self.segments.values() if seg.from_id == from_id]
            if not outgoing:
                return None
            next_seg = outgoing[np.random.randint(len(outgoing))]
            vehicle.position = next_seg.length
            vehicle.approach = self._road_to_approach(from_id, next_seg.to_id)
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
            next_seg = outgoing[np.random.randint(len(outgoing))]
            vehicle.position = next_seg.length
            vehicle.approach = self._road_to_approach(from_id, next_seg.to_id)
            next_seg.vehicles.append(vehicle)
            return next_seg.road_id

        # Find the road segment to next hop
        edge_id = self.router.get_edge_id(from_id, next_node)
        if edge_id is None or edge_id not in self.segments:
            self.vehicle_destinations.pop(vehicle.id, None)
            return None

        next_seg = self.segments[edge_id]
        vehicle.position = next_seg.length
        vehicle.approach = self._road_to_approach(from_id, next_node)
        next_seg.vehicles.append(vehicle)

        # Clean up destination if arrived
        if next_node == dest:
            self.vehicle_destinations.pop(vehicle.id, None)

        return edge_id

    def _has_green(self, ix: Intersection, approach: int) -> bool:
        """Check if approach has green light."""
        if ix.current_phase == "NS_GREEN":
            return approach in [0, 2]
        elif ix.current_phase == "EW_GREEN":
            return approach in [1, 3]
        return False

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
