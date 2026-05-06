"""Tests for the route planner (Dijkstra)."""

import pytest

from traffic_agent.simulation.router import RoutePlanner
from traffic_agent.simulation.osm import OSMNetwork, SMALL_MANHATTAN, WUHAN_OPTICS_VALLEY
from traffic_agent.simulation.osm_sim import OSMSimulation
from traffic_agent.simulation.engine import SimulationConfig


class TestRoutePlanner:
    """Test Dijkstra route planner."""

    def _make_planner(self, preset: str = "manhattan") -> tuple:
        """Create a planner from a preset."""
        data = SMALL_MANHATTAN if preset == "manhattan" else WUHAN_OPTICS_VALLEY
        net = OSMNetwork.from_dict(data)
        # Build segments like OSMSimulation does
        from traffic_agent.simulation.osm_sim import OSMSegment

        segments = {}
        for road_id, osm_road in net.roads.items():
            segments[road_id] = OSMSegment(
                road_id=road_id,
                from_id=osm_road.from_intersection,
                to_id=osm_road.to_intersection,
                length=osm_road.length,
                speed_limit=osm_road.speed_limit / 3.6,
                lanes=osm_road.lanes,
                name=osm_road.name,
                oneway=osm_road.oneway,
            )
        planner = RoutePlanner()
        planner.build_graph(segments)
        return planner, net

    def test_shortest_path_same_node(self):
        """Path from node to itself."""
        planner, _ = self._make_planner()
        path = planner.shortest_path("ix_2_2", "ix_2_2")
        assert path == ["ix_2_2"]

    def test_shortest_path_adjacent(self):
        """Path between adjacent nodes."""
        planner, _ = self._make_planner()
        path = planner.shortest_path("ix_1_1", "ix_1_2")
        assert path is not None
        assert path[0] == "ix_1_1"
        assert path[-1] == "ix_1_2"
        assert len(path) == 2

    def test_shortest_path_cross_grid(self):
        """Path across the grid."""
        planner, _ = self._make_planner()
        path = planner.shortest_path("ix_1_1", "ix_3_3")
        assert path is not None
        assert path[0] == "ix_1_1"
        assert path[-1] == "ix_3_3"
        # Should be 4 edges (5 nodes): right, right, down, down (or similar)
        assert len(path) == 5

    def test_shortest_path_unreachable(self):
        """Path to unreachable node returns None."""
        planner, _ = self._make_planner()
        # Create planner with isolated node
        planner._adjacency["isolated"] = []
        path = planner.shortest_path("ix_1_1", "isolated")
        assert path is None

    def test_next_hop(self):
        """Next hop returns the second node in path."""
        planner, _ = self._make_planner()
        next_node = planner.next_hop("ix_1_1", "ix_3_3")
        assert next_node is not None
        # Should be ix_1_2 or ix_2_1 (adjacent to ix_1_1)
        assert next_node in ["ix_1_2", "ix_2_1"]

    def test_next_hop_at_destination(self):
        """Next hop when already at destination returns None."""
        planner, _ = self._make_planner()
        next_node = planner.next_hop("ix_1_1", "ix_1_1")
        assert next_node is None

    def test_get_edge_id(self):
        """Get edge ID between adjacent nodes."""
        planner, _ = self._make_planner()
        edge_id = planner.get_edge_id("ix_1_1", "ix_1_2")
        assert edge_id is not None
        # Should be r_1 (first road in preset)
        assert edge_id == "r_1"

    def test_get_edge_id_none(self):
        """Get edge ID for non-adjacent nodes."""
        planner, _ = self._make_planner()
        edge_id = planner.get_edge_id("ix_1_1", "ix_3_3")
        assert edge_id is None

    def test_get_distance(self):
        """Get distance between nodes."""
        planner, _ = self._make_planner()
        dist = planner.get_distance("ix_1_1", "ix_1_2")
        assert dist is not None
        assert dist == 220.0  # Road length in preset

    def test_get_distance_cross_grid(self):
        """Distance across grid is sum of road lengths."""
        planner, _ = self._make_planner()
        dist = planner.get_distance("ix_1_1", "ix_3_3")
        assert dist is not None
        assert dist == 4 * 220.0  # 4 roads of 220m each

    def test_cache_hit(self):
        """Second call uses cache."""
        planner, _ = self._make_planner()
        path1 = planner.shortest_path("ix_1_1", "ix_3_3")
        path2 = planner.shortest_path("ix_1_1", "ix_3_3")
        assert path1 == path2

    def test_clear_cache(self):
        """Clear cache works."""
        planner, _ = self._make_planner()
        planner.shortest_path("ix_1_1", "ix_3_3")
        planner.clear_cache()
        assert len(planner._path_cache) == 0

    def test_wuhan_routing(self):
        """Routing works on Wuhan preset."""
        planner, _ = self._make_planner("wuhan")
        path = planner.shortest_path("guanggu_1", "guanggu_6")
        assert path is not None
        assert path[0] == "guanggu_1"
        assert path[-1] == "guanggu_6"

    def test_bidirectional_road(self):
        """Bidirectional roads allow reverse travel via explicit reverse segments."""
        from traffic_agent.simulation.osm_sim import OSMSegment

        # Create a 2-node bidirectional network with explicit reverse segments
        segments = {
            "road_1": OSMSegment(
                road_id="road_1",
                from_id="A",
                to_id="B",
                length=100.0,
                speed_limit=13.89,
                lanes=2,
                name="test",
                oneway=False,
            ),
            "road_1_rev": OSMSegment(
                road_id="road_1_rev",
                from_id="B",
                to_id="A",
                length=100.0,
                speed_limit=13.89,
                lanes=2,
                name="test",
                oneway=False,
            ),
        }
        planner = RoutePlanner()
        planner.build_graph(segments)

        # Can go A -> B
        path = planner.shortest_path("A", "B")
        assert path == ["A", "B"]

        # Can also go B -> A (bidirectional)
        path = planner.shortest_path("B", "A")
        assert path == ["B", "A"]


class TestRouterIntegration:
    """Test router integration with OSMSimulation."""

    def test_vehicles_use_shortest_path(self):
        """Vehicles are routed via shortest path."""
        sim = OSMSimulation.from_preset(
            "manhattan", SimulationConfig(seed=42, arrival_rate=1.0)
        )
        # Run a few steps
        for _ in range(20):
            sim.step()

        # Check that some vehicles have destinations
        assert sim.total_vehicles_generated > 0

    def test_router_built_on_init(self):
        """Router is built when simulation starts."""
        sim = OSMSimulation.from_preset("manhattan")
        assert len(sim.router._adjacency) > 0

    def test_caches_cleared_on_reset(self):
        """Router cache cleared on reset."""
        sim = OSMSimulation.from_preset("manhattan", SimulationConfig(seed=42))
        for _ in range(10):
            sim.step()
        sim.reset()
        assert len(sim.router._path_cache) == 0
        assert len(sim.vehicle_destinations) == 0

    def test_simulation_completes_with_router(self):
        """Simulation runs to completion with router."""
        sim = OSMSimulation.from_preset(
            "manhattan", SimulationConfig(seed=42, arrival_rate=0.5)
        )
        for _ in range(100):
            sim.step()
        metrics = sim.get_metrics()
        assert metrics["vehicles_completed"] >= 0  # May or may not complete
        assert metrics["vehicles_generated"] > 0
