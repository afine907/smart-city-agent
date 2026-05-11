"""
Tests for CrewAI Integration — TrafficControlCrew, Tools, and Coordination.
"""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

# crewai is a core dependency — always available

from traffic_agent.crew.coordination import (
    ConflictDetector,
    GreenWaveAdvisor,
    PriorityResolver,
)
from traffic_agent.llm.parser import TrafficDecision, TimingAdjustment
from traffic_agent.simulation.grid import GridSimulation
from traffic_agent.simulation.engine import SimulationConfig
from traffic_agent.tools.traffic_tools import (
    IntersectionState,
    SimulationState,
    set_sim_state,
)


# ─── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def grid_sim():
    """Create a deterministic 3x3 grid simulation."""
    sim = GridSimulation(config=SimulationConfig(seed=42))
    # Run a few steps to generate some traffic
    for _ in range(10):
        sim.step()
    return sim


@pytest.fixture
def graph(grid_sim):
    return grid_sim.get_graph()


@pytest.fixture
def sim_state(grid_sim, graph):
    state = SimulationState(engine=grid_sim, graph=graph)
    set_sim_state(state)
    return state


# ─── Test CrewAI Tools ────────────────────────────────────────

class TestCrewTools:
    """Test each CrewAI tool independently."""

    def test_get_intersection_state_tool(self, sim_state):
        from traffic_agent.tools.traffic_tools import _create_tools
        tools = _create_tools()
        get_state_tool = tools[0]  # get_intersection_state

        result = get_state_tool._run(intersection_id="ix_1_1")
        assert "ix_1_1" in result
        assert "排队" in result
        assert "信号" in result

    def test_get_neighbor_states_tool(self, sim_state):
        from traffic_agent.tools.traffic_tools import _create_tools
        tools = _create_tools()
        get_neighbors_tool = tools[1]  # get_neighbor_states

        result = get_neighbors_tool._run(intersection_id="ix_1_1")
        assert "邻居" in result
        # ix_1_1 should have neighbors
        assert any(n in result for n in ["ix_0_1", "ix_1_0", "ix_1_2", "ix_2_1"])

    def test_apply_signal_decision_tool(self, sim_state):
        from traffic_agent.tools.traffic_tools import _create_tools
        tools = _create_tools()
        apply_tool = tools[2]  # apply_signal_decision

        result = apply_tool._run(
            intersection_id="ix_1_1",
            phase="EW_GREEN",
            reasoning="测试切换"
        )
        assert "已将" in result
        assert "EW_GREEN" in result

        # Verify state changed
        state = sim_state.engine.get_state("ix_1_1")
        assert state.current_phase == "EW_GREEN"

    def test_apply_signal_decision_invalid_phase(self, sim_state):
        from traffic_agent.tools.traffic_tools import _create_tools
        tools = _create_tools()
        apply_tool = tools[2]

        result = apply_tool._run(
            intersection_id="ix_1_1",
            phase="INVALID",
            reasoning="测试"
        )
        assert "错误" in result

    def test_apply_timing_adjustment_tool(self, sim_state):
        from traffic_agent.tools.traffic_tools import _create_tools
        tools = _create_tools()
        adjust_tool = tools[3]  # apply_timing_adjustment

        result = adjust_tool._run(
            intersection_id="ix_1_1",
            adjustment=5,
            reasoning="测试调整"
        )
        assert "+5" in result

    def test_check_conflicts_tool(self, sim_state):
        from traffic_agent.tools.traffic_tools import _create_tools
        tools = _create_tools()
        check_tool = tools[4]  # check_conflicts

        # Create conflicting decisions
        decisions = [
            {"intersection_id": "ix_0_0", "phase": "NS_GREEN", "duration": 30, "action": "extend_green"},
            {"intersection_id": "ix_0_1", "phase": "EW_GREEN", "duration": 30, "action": "extend_green"},
        ]
        result = check_tool._run(decisions_json=json.dumps(decisions))
        assert "冲突" in result

    def test_get_traffic_trend_tool(self, sim_state):
        from traffic_agent.tools.traffic_tools import _create_tools
        tools = _create_tools()
        trend_tool = tools[5]  # get_traffic_trend

        result = trend_tool._run(intersection_id="ix_1_1", direction="north")
        assert "ix_1_1" in result
        assert "north" in result
        assert "排队" in result

    def test_get_traffic_trend_invalid_direction(self, sim_state):
        from traffic_agent.tools.traffic_tools import _create_tools
        tools = _create_tools()
        trend_tool = tools[5]

        result = trend_tool._run(intersection_id="ix_1_1", direction="invalid")
        assert "错误" in result


# ─── Test TrafficControlCrew ──────────────────────────────────

class TestTrafficControlCrew:
    """Test crew orchestration logic."""

    @patch("crewai.Agent")
    def test_crew_creation(self, mock_agent_cls, graph):
        from traffic_agent.crew.traffic_crew import TrafficControlCrew, CrewConfig

        intersection_ids = list(graph.keys())
        crew = TrafficControlCrew(
            intersection_ids=intersection_ids,
            graph=graph,
            config=CrewConfig(),
        )

        assert len(crew.intersection_agents) == 9
        assert crew.coordinator_agent is not None
        assert len(crew.intersection_tools) == 4  # 3-5 tools per agent (skill rule)
        assert len(crew.coordinator_tools) == 3
        # Agent() called 9 times for intersections + 1 for coordinator
        assert mock_agent_cls.call_count == 10

    @patch("crewai.Agent")
    def test_set_engine(self, mock_agent_cls, grid_sim, graph):
        from traffic_agent.crew.traffic_crew import TrafficControlCrew, CrewConfig

        intersection_ids = list(graph.keys())
        crew = TrafficControlCrew(
            intersection_ids=intersection_ids,
            graph=graph,
            config=CrewConfig(),
        )

        crew.set_engine(grid_sim)

        from traffic_agent.tools.traffic_tools import _sim_state
        assert _sim_state is not None
        assert _sim_state.engine is grid_sim

    @patch("crewai.Crew")
    @patch("crewai.Task")
    @patch("crewai.Agent")
    def test_step_rules_only(self, mock_agent_cls, mock_task_cls, mock_crew_cls, grid_sim, graph):
        """Test that rules handle simple cases without LLM calls."""
        from traffic_agent.crew.traffic_crew import TrafficControlCrew, CrewConfig

        crew = TrafficControlCrew(
            intersection_ids=list(graph.keys()),
            graph=graph,
            config=CrewConfig(use_rules=True, use_cache=False),
        )
        crew.set_engine(grid_sim)

        grid_sim.step()
        decisions = crew.step(grid_sim)

        assert len(decisions) > 0
        metrics = crew.get_metrics()
        assert metrics["total_decisions"] > 0

    @patch("crewai.Crew")
    @patch("crewai.Task")
    @patch("crewai.Agent")
    def test_metrics_tracking(self, mock_agent_cls, mock_task_cls, mock_crew_cls, grid_sim, graph):
        """Test that metrics are correctly tracked."""
        from traffic_agent.crew.traffic_crew import TrafficControlCrew, CrewConfig

        crew = TrafficControlCrew(
            intersection_ids=list(graph.keys()),
            graph=graph,
            config=CrewConfig(use_rules=True, use_cache=True),
        )
        crew.set_engine(grid_sim)

        for _ in range(3):
            grid_sim.step()
            crew.step(grid_sim)

        metrics = crew.get_metrics()
        assert "total_decisions" in metrics
        assert "total_llm_calls" in metrics
        assert "total_rule_hits" in metrics
        assert "total_cache_hits" in metrics
        assert "rule_hit_rate" in metrics
        assert "cache_hit_rate" in metrics
        assert metrics["total_decisions"] > 0

    @patch("crewai.Crew")
    @patch("crewai.Task")
    @patch("crewai.Agent")
    def test_decision_history(self, mock_agent_cls, mock_task_cls, mock_crew_cls, grid_sim, graph):
        """Test that decision history is recorded."""
        from traffic_agent.crew.traffic_crew import TrafficControlCrew, CrewConfig

        crew = TrafficControlCrew(
            intersection_ids=list(graph.keys()),
            graph=graph,
            config=CrewConfig(use_rules=True, use_cache=False),
        )
        crew.set_engine(grid_sim)

        grid_sim.step()
        crew.step(grid_sim)

        history = crew.get_reasoning_history("ix_1_1", limit=5)
        assert isinstance(history, list)


# ─── Test Coordination Enhancements ───────────────────────────

class TestGreenWaveAdvisor:
    """Test green wave advisory system."""

    def test_suggest_offsets(self, graph):
        decisions = {
            "ix_1_0": TrafficDecision(
                action="extend_green", phase="EW_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
            "ix_1_1": TrafficDecision(
                action="extend_green", phase="EW_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
            "ix_1_2": TrafficDecision(
                action="extend_green", phase="EW_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
        }

        suggestions = GreenWaveAdvisor.suggest_offsets(
            decisions, graph, corridor_direction="EW"
        )

        # Should have suggestions for at least some intersections
        assert isinstance(suggestions, dict)
        # Values should be clamped to [-10, 10]
        for v in suggestions.values():
            assert -10 <= v <= 10


class TestPriorityResolver:
    """Test priority-based conflict resolution."""

    def test_emergency_wins(self, graph):
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
        states = {
            "ix_0_0": IntersectionState(
                intersection_id="ix_0_0", timestamp=0,
                queue_north=5, queue_south=5, queue_east=3, queue_west=3,
                current_phase="NS_GREEN", emergency=True,
            ),
            "ix_0_1": IntersectionState(
                intersection_id="ix_0_1", timestamp=0,
                queue_north=10, queue_south=10, queue_east=8, queue_west=8,
                current_phase="EW_GREEN", emergency=False,
            ),
        }
        conflicts = [("ix_0_0", "ix_0_1", "phase_mismatch")]

        resolved = PriorityResolver.resolve(decisions, states, conflicts)

        # Emergency intersection should keep its phase
        assert resolved["ix_0_0"].phase == "NS_GREEN"
        # Non-emergency should get the opposite phase (conflict resolved)
        assert resolved["ix_0_1"].phase == "EW_GREEN"

    def test_higher_queue_wins(self, graph):
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
        states = {
            "ix_0_0": IntersectionState(
                intersection_id="ix_0_0", timestamp=0,
                queue_north=20, queue_south=20, queue_east=3, queue_west=3,
                current_phase="NS_GREEN",
            ),
            "ix_0_1": IntersectionState(
                intersection_id="ix_0_1", timestamp=0,
                queue_north=5, queue_south=5, queue_east=3, queue_west=3,
                current_phase="EW_GREEN",
            ),
        }
        conflicts = [("ix_0_0", "ix_0_1", "phase_mismatch")]

        resolved = PriorityResolver.resolve(decisions, states, conflicts)

        # Higher queue intersection should keep its phase
        assert resolved["ix_0_0"].phase == "NS_GREEN"

    def test_no_conflicts_returns_unchanged(self, graph):
        decisions = {
            "ix_0_0": TrafficDecision(
                action="extend_green", phase="NS_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
        }
        resolved = PriorityResolver.resolve(decisions, {}, [])
        assert resolved["ix_0_0"].phase == "NS_GREEN"


class TestConflictDetectorBackwardCompat:
    """Ensure existing ConflictDetector behavior is preserved."""

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
        assert len(conflicts) == 2
        assert all(c[2] == "excessive_green" for c in conflicts)


# ─── Test GridSimulation with SignalController ────────────────

class TestGridWithSignalController:
    """Test that GridSimulation works with integrated SignalController."""

    def test_signal_controller_exists(self, grid_sim):
        assert len(grid_sim.controllers) == 9
        for ix_id in grid_sim.intersections:
            assert ix_id in grid_sim.controllers

    def test_get_signal_state(self, grid_sim):
        signal_state = grid_sim.get_signal_state("ix_1_1")
        assert signal_state.current_phase in [
            "NS_GREEN", "NS_YELLOW", "ALL_RED_1",
            "EW_GREEN", "EW_YELLOW", "ALL_RED_2"
        ]
        assert signal_state.phase_duration >= 0

    def test_get_state_includes_base_duration(self, grid_sim):
        state = grid_sim.get_state("ix_1_1")
        assert state.base_duration > 0
        assert state.phase_duration > 0

    def test_apply_decision_with_adjustment(self, grid_sim):
        controller = grid_sim.controllers["ix_1_1"]
        initial_state = controller.get_state()

        grid_sim.apply_decision("ix_1_1", {"adjustment": 5})

        new_state = controller.get_state()
        # Adjustment should be applied
        assert new_state.adjustment == 5

    def test_apply_decision_with_phase_switch(self, grid_sim):
        grid_sim.apply_decision("ix_1_1", {"phase": "EW_GREEN"})
        state = grid_sim.get_state("ix_1_1")
        assert state.current_phase == "EW_GREEN"

    def test_reset_resets_controllers(self, grid_sim):
        grid_sim.apply_decision("ix_1_1", {"phase": "EW_GREEN"})
        grid_sim.reset()

        state = grid_sim.get_state("ix_1_1")
        assert state.current_phase == "NS_GREEN"
