"""
Tests for Grid Simulation
"""

import pytest

from traffic_agent.simulation.grid import GridSimulation, RoadSegment
from traffic_agent.simulation.engine import SimulationConfig


class TestGridSimulation:
    """Test 3x3 grid simulation."""
    
    def test_grid_creation(self):
        sim = GridSimulation(SimulationConfig(seed=42))
        
        assert len(sim.intersections) == 9
        assert len(sim.segments) == 12  # 6 horizontal + 6 vertical
    
    def test_neighbors(self):
        sim = GridSimulation()
        
        # Center intersection
        neighbors = sim.get_neighbors("ix_1_1")
        assert len(neighbors) == 4
        assert "ix_0_1" in neighbors  # North
        assert "ix_2_1" in neighbors  # South
        assert "ix_1_0" in neighbors  # West
        assert "ix_1_2" in neighbors  # East
        
        # Corner intersection
        neighbors = sim.get_neighbors("ix_0_0")
        assert len(neighbors) == 2
        assert "ix_0_1" in neighbors
        assert "ix_1_0" in neighbors
    
    def test_graph(self):
        sim = GridSimulation()
        graph = sim.get_graph()
        
        assert len(graph) == 9
        assert "ix_1_1" in graph
        assert len(graph["ix_1_1"]) == 4
    
    def test_get_state(self):
        sim = GridSimulation(SimulationConfig(seed=42))
        state = sim.get_state("ix_0_0")
        
        assert state.intersection_id == "ix_0_0"
        assert state.current_phase == "NS_GREEN"
    
    def test_step_advances_time(self):
        sim = GridSimulation(SimulationConfig(dt=1.0, seed=42))
        sim.step()
        assert sim.time == 1.0
    
    def test_vehicle_generation(self):
        sim = GridSimulation(SimulationConfig(
            seed=42, arrival_rate=2.0, road_length=50.0
        ))
        
        # Run several steps
        for _ in range(30):
            sim.step()
        
        assert sim.total_vehicles_generated > 0
    
    def test_vehicle_flow(self):
        sim = GridSimulation(SimulationConfig(
            seed=42, arrival_rate=2.0, road_length=50.0
        ))
        
        for _ in range(100):
            sim.step()
        
        metrics = sim.get_metrics()
        assert metrics["vehicles_generated"] > 0
    
    def test_apply_decision(self):
        sim = GridSimulation(SimulationConfig(seed=42))
        
        sim.apply_decision("ix_1_1", {"phase": "EW_GREEN"})
        assert sim.intersections["ix_1_1"].current_phase == "EW_GREEN"
    
    def test_metrics(self):
        sim = GridSimulation(SimulationConfig(seed=42))
        
        for _ in range(50):
            sim.step()
        
        metrics = sim.get_metrics()
        assert "time" in metrics
        assert "total_queue" in metrics
        assert "throughput" in metrics
    
    def test_reset(self):
        sim = GridSimulation(SimulationConfig(seed=42))
        
        for _ in range(50):
            sim.step()
        
        sim.reset()
        assert sim.time == 0.0
        assert sim.total_vehicles_generated == 0
    
    def test_9_intersections(self):
        sim = GridSimulation()
        
        expected = [f"ix_{r}_{c}" for r in range(3) for c in range(3)]
        assert list(sim.intersections.keys()) == expected
