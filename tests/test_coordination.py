"""
Tests for Multi-Agent Coordination
"""

import json
import pytest

from traffic_agent.crew.coordination import (
    ConflictDetector,
    CoordinationCrew,
    MessageBus,
    AgentMessage,
)
from traffic_agent.llm.parser import TrafficDecision
from traffic_agent.simulation.grid import GridSimulation
from traffic_agent.simulation.engine import SimulationConfig


class TestMessageBus:
    """Test message bus."""
    
    def test_send_receive(self):
        bus = MessageBus()
        
        msg = AgentMessage(
            sender="ix_0_0",
            receiver="ix_0_1",
            msg_type="state",
            content="排队10辆",
            timestamp=100.0,
        )
        bus.send(msg)
        
        received = bus.receive("ix_0_1")
        assert len(received) == 1
        assert received[0].sender == "ix_0_0"
    
    def test_no_messages(self):
        bus = MessageBus()
        received = bus.receive("ix_0_0")
        assert len(received) == 0
    
    def test_multiple_messages(self):
        bus = MessageBus()
        
        for i in range(3):
            bus.send(AgentMessage(
                sender=f"ix_0_{i}",
                receiver="ix_1_1",
                msg_type="state",
                content=f"msg_{i}",
                timestamp=100.0,
            ))
        
        received = bus.receive("ix_1_1")
        assert len(received) == 3
    
    def test_clear(self):
        bus = MessageBus()
        bus.send(AgentMessage(
            sender="a", receiver="b", msg_type="x",
            content="", timestamp=0,
        ))
        bus.clear()
        assert len(bus.receive("b")) == 0


class TestConflictDetector:
    """Test conflict detection."""
    
    def test_no_conflict(self):
        decisions = {
            "ix_0_0": TrafficDecision(
                action="extend_green", phase="NS_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
            "ix_0_1": TrafficDecision(
                action="extend_green", phase="NS_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
        }
        graph = {"ix_0_0": ["ix_0_1"], "ix_0_1": ["ix_0_0"]}
        
        conflicts = ConflictDetector.detect(decisions, graph)
        assert len(conflicts) == 0
    
    def test_phase_mismatch(self):
        decisions = {
            "ix_0_0": TrafficDecision(
                action="extend_green", phase="NS_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
            "ix_0_1": TrafficDecision(
                action="extend_green", phase="EW_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
        }
        graph = {"ix_0_0": ["ix_0_1"], "ix_0_1": ["ix_0_0"]}
        
        conflicts = ConflictDetector.detect(decisions, graph)
        assert len(conflicts) == 1
        assert conflicts[0][2] == "phase_mismatch"
    
    def test_excessive_green(self):
        decisions = {
            "ix_0_0": TrafficDecision(
                action="extend_green", phase="NS_GREEN",
                duration=50, reasoning="test", confidence=0.8,
            ),
            "ix_0_1": TrafficDecision(
                action="extend_green", phase="NS_GREEN",
                duration=50, reasoning="test", confidence=0.8,
            ),
        }
        graph = {"ix_0_0": ["ix_0_1"], "ix_0_1": ["ix_0_0"]}
        
        conflicts = ConflictDetector.detect(decisions, graph)
        # Detected in both directions
        assert len(conflicts) == 2
        assert all(c[2] == "excessive_green" for c in conflicts)
    
    def test_non_adjacent_no_conflict(self):
        decisions = {
            "ix_0_0": TrafficDecision(
                action="extend_green", phase="NS_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
            "ix_2_2": TrafficDecision(
                action="extend_green", phase="EW_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
        }
        graph = {"ix_0_0": ["ix_0_1"], "ix_2_2": ["ix_2_1"]}
        
        conflicts = ConflictDetector.detect(decisions, graph)
        assert len(conflicts) == 0


class TestCoordinationCrew:
    """Test coordination crew (without actual LLM calls)."""
    
    def test_creation(self):
        sim = GridSimulation(SimulationConfig(seed=42))
        crew = CoordinationCrew(sim)
        
        assert len(crew.intersection_ids) == 9
        assert crew.total_llm_calls == 0
    
    def test_graph_matches_simulation(self):
        sim = GridSimulation()
        crew = CoordinationCrew(sim)
        
        assert crew.graph == sim.get_graph()
    
    def test_metrics_initial(self):
        sim = GridSimulation()
        crew = CoordinationCrew(sim)
        
        metrics = crew.get_metrics()
        assert metrics["total_llm_calls"] == 0
        assert metrics["total_conflicts"] == 0
