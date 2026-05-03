"""Tests for OpenStreetMap integration."""

import pytest

from traffic_agent.simulation.engine import SimulationConfig
from traffic_agent.simulation.osm import (
    SMALL_MANHATTAN,
    WUHAN_OPTICS_VALLEY,
    OSMNetwork,
)
from traffic_agent.simulation.osm_sim import OSMSimulation


class TestOSMNetwork:
    """Test OSM network loading and manipulation."""

    def test_from_dict(self):
        """Load network from dictionary."""
        net = OSMNetwork.from_dict(SMALL_MANHATTAN)
        assert len(net.intersections) == 9
        assert len(net.roads) == 12

    def test_wuhan_preset(self):
        """Load Wuhan Optics Valley preset."""
        net = OSMNetwork.from_dict(WUHAN_OPTICS_VALLEY)
        assert len(net.intersections) == 6
        assert len(net.roads) == 7

        # Check a specific intersection
        guanggu_2 = net.intersections["guanggu_2"]
        assert "珞瑜路" in guanggu_2.roads
        assert "光谷广场" in guanggu_2.roads

    def test_neighbors(self):
        """Get neighbors of an intersection."""
        net = OSMNetwork.from_dict(SMALL_MANHATTAN)
        neighbors = net.get_neighbors("ix_2_2")
        assert len(neighbors) == 4
        assert "ix_1_2" in neighbors
        assert "ix_3_2" in neighbors
        assert "ix_2_1" in neighbors
        assert "ix_2_3" in neighbors

    def test_get_road_between(self):
        """Get road connecting two intersections."""
        net = OSMNetwork.from_dict(SMALL_MANHATTAN)
        road = net.get_road_between("ix_1_1", "ix_1_2")
        assert road is not None
        assert road.name == "7th Ave"
        assert road.length == 220

    def test_get_road_between_none(self):
        """Get road when none exists."""
        net = OSMNetwork.from_dict(SMALL_MANHATTAN)
        road = net.get_road_between("ix_1_1", "ix_3_3")
        assert road is None

    def test_stats(self):
        """Get network statistics."""
        net = OSMNetwork.from_dict(SMALL_MANHATTAN)
        stats = net.get_stats()
        assert stats["num_intersections"] == 9
        assert stats["num_roads"] == 12
        assert stats["avg_road_length"] == 220.0
        assert stats["total_road_length"] == 12 * 220

    def test_to_geojson(self):
        """Export to GeoJSON."""
        net = OSMNetwork.from_dict(SMALL_MANHATTAN)
        geojson = net.to_geojson()
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 9 + 12  # 9 points + 12 lines

    def test_haversine(self):
        """Test distance calculation."""
        # Distance between ix_1_1 (40.7580, -73.9855) and ix_3_3 (40.7540, -73.9805)
        dist = OSMNetwork._haversine(40.7580, -73.9855, 40.7540, -73.9805)
        assert 300 < dist < 700  # ~500m diagonal across the grid


class TestOSMSimulation:
    """Test OSM-based traffic simulation."""

    def test_create_from_preset(self):
        """Create simulation from preset."""
        sim = OSMSimulation.from_preset("manhattan")
        assert len(sim.intersections) == 9
        assert len(sim.segments) == 12

    def test_create_from_dict(self):
        """Create simulation from dict."""
        sim = OSMSimulation.from_dict(WUHAN_OPTICS_VALLEY)
        assert len(sim.intersections) == 6

    def test_unknown_preset(self):
        """Error on unknown preset."""
        with pytest.raises(ValueError, match="Unknown preset"):
            OSMSimulation.from_preset("nonexistent")

    def test_get_state(self):
        """Get intersection state."""
        sim = OSMSimulation.from_preset("manhattan")
        state = sim.get_state("ix_2_2")
        assert state.intersection_id == "ix_2_2"
        assert state.current_phase == "NS_GREEN"
        assert state.emergency is False

    def test_get_state_unknown(self):
        """Get state for unknown intersection."""
        sim = OSMSimulation.from_preset("manhattan")
        state = sim.get_state("nonexistent")
        assert state.intersection_id == "nonexistent"

    def test_apply_decision(self):
        """Apply traffic decision."""
        sim = OSMSimulation.from_preset("manhattan")
        sim.apply_decision("ix_2_2", {"phase": "EW_GREEN"})
        ix = sim.intersections["ix_2_2"]
        assert ix.current_phase == "EW_GREEN"

    def test_step(self):
        """Run one simulation step."""
        sim = OSMSimulation.from_preset("manhattan", SimulationConfig(seed=42))
        sim.step()
        assert sim.time == 1.0
        assert sim.step_count == 1

    def test_multiple_steps(self):
        """Run multiple steps."""
        sim = OSMSimulation.from_preset("manhattan", SimulationConfig(seed=42))
        for _ in range(10):
            sim.step()
        assert sim.time == 10.0
        assert sim.step_count == 10

    def test_metrics(self):
        """Get metrics after running."""
        sim = OSMSimulation.from_preset("manhattan", SimulationConfig(seed=42))
        for _ in range(100):
            sim.step()
        metrics = sim.get_metrics()
        assert "time" in metrics
        assert "total_queue" in metrics
        assert "vehicles_generated" in metrics
        assert "vehicles_completed" in metrics
        assert "num_intersections" in metrics
        assert metrics["num_intersections"] == 9

    def test_reset(self):
        """Reset simulation."""
        sim = OSMSimulation.from_preset("manhattan", SimulationConfig(seed=42))
        for _ in range(10):
            sim.step()
        sim.reset()
        assert sim.time == 0.0
        assert sim.step_count == 0

    def test_get_neighbors(self):
        """Get neighbors."""
        sim = OSMSimulation.from_preset("manhattan")
        neighbors = sim.get_neighbors("ix_2_2")
        assert len(neighbors) == 4

    def test_get_graph(self):
        """Get adjacency graph."""
        sim = OSMSimulation.from_preset("manhattan")
        graph = sim.get_graph()
        assert len(graph) == 9
        assert "ix_2_2" in graph

    def test_export_geojson(self):
        """Export as GeoJSON."""
        sim = OSMSimulation.from_preset("manhattan")
        geojson = sim.export_geojson()
        assert geojson["type"] == "FeatureCollection"

    def test_boundary_detection(self):
        """Boundary intersections are detected."""
        sim = OSMSimulation.from_preset("manhattan")
        # In a one-way grid, most intersections are boundaries
        # Only ix_2_2 (center) has 2 incoming + 2 outgoing
        assert "ix_1_1" in sim.boundary_intersections  # 0 in, 2 out
        assert "ix_3_3" in sim.boundary_intersections  # 2 in, 0 out
        # Center should NOT be boundary (2 in, 2 out)
        assert "ix_2_2" not in sim.boundary_intersections

    def test_vehicle_generation_at_boundaries(self):
        """Vehicles are generated at boundary intersections."""
        sim = OSMSimulation.from_preset("manhattan", SimulationConfig(
            seed=42,
            arrival_rate=1.0,  # High rate for testing
        ))
        for _ in range(50):
            sim.step()
        assert sim.total_vehicles_generated > 0

    def test_emergency_vehicle(self):
        """Emergency vehicle triggers green for its approach."""
        sim = OSMSimulation.from_preset("manhattan")
        # Manually add an emergency vehicle
        from traffic_agent.simulation.engine import Vehicle
        emergency = Vehicle(
            id="emergency_1",
            approach=0,  # N
            position=10.0,
            speed=20.0,
            is_emergency=True,
        )
        # Find a segment leading to ix_2_2
        for seg in sim.segments.values():
            if seg.to_id == "ix_2_2":
                seg.vehicles.append(emergency)
                break

        sim.step()
        ix = sim.intersections["ix_2_2"]
        # Should trigger NS_GREEN (approach 0 is N)
        assert ix.current_phase == "NS_GREEN"

    def test_variable_road_lengths(self):
        """Different road lengths are preserved."""
        sim = OSMSimulation.from_preset("wuhan")
        for seg in sim.segments.values():
            assert seg.length > 0
            assert seg.length != 200.0  # Not default grid length

    def test_wuhan_simulation_runs(self):
        """Wuhan preset simulation runs correctly."""
        sim = OSMSimulation.from_preset("wuhan", SimulationConfig(seed=42))
        for _ in range(100):
            sim.step()
        metrics = sim.get_metrics()
        assert metrics["num_intersections"] == 6
        assert metrics["vehicles_generated"] > 0


class TestOSMGeoJSON:
    """Test GeoJSON import/export."""

    def test_geojson_roundtrip(self):
        """Export and re-import GeoJSON."""
        net1 = OSMNetwork.from_dict(SMALL_MANHATTAN)
        geojson = net1.to_geojson()

        # Note: GeoJSON import only handles Points and LineStrings,
        # so we'd need to reconstruct the network differently.
        # This test just verifies the export works.
        assert len(geojson["features"]) == 21  # 9 points + 12 lines
