"""
Tests for Multi-Agent Coordination
"""

import pytest

from traffic_agent.crew.coordination import (
    ConflictDetector,
    GreenWaveAdvisor,
    PriorityResolver,
)
from traffic_agent.llm.parser import TrafficDecision
from traffic_agent.tools.traffic_tools import IntersectionState


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

    def test_empty_decisions(self):
        conflicts = ConflictDetector.detect({}, {"ix_0_0": ["ix_0_1"]})
        assert len(conflicts) == 0

    def test_single_intersection_no_conflict(self):
        decisions = {
            "ix_0_0": TrafficDecision(
                action="extend_green", phase="NS_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
        }
        graph = {"ix_0_0": []}

        conflicts = ConflictDetector.detect(decisions, graph)
        assert len(conflicts) == 0

    def test_neighbor_not_in_decisions(self):
        decisions = {
            "ix_0_0": TrafficDecision(
                action="extend_green", phase="NS_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
        }
        graph = {"ix_0_0": ["ix_0_1"], "ix_0_1": ["ix_0_0"]}

        conflicts = ConflictDetector.detect(decisions, graph)
        assert len(conflicts) == 0


class TestGreenWaveAdvisor:
    """Test green wave offset suggestions."""

    def test_suggest_offsets_ew_corridor(self):
        decisions = {
            "ix_0_0": TrafficDecision(
                action="extend_green", phase="EW_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
            "ix_0_1": TrafficDecision(
                action="extend_green", phase="EW_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
            "ix_0_2": TrafficDecision(
                action="extend_green", phase="EW_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
        }
        graph = {
            "ix_0_0": ["ix_0_1"],
            "ix_0_1": ["ix_0_0", "ix_0_2"],
            "ix_0_2": ["ix_0_1"],
        }

        suggestions = GreenWaveAdvisor.suggest_offsets(decisions, graph, "EW")
        # First intersection gets no offset, later ones get progressive offsets
        assert "ix_0_0" not in suggestions or suggestions.get("ix_0_0", 0) == 0
        # Later intersections should have negative offsets (shorter green upstream)
        if "ix_0_1" in suggestions:
            assert suggestions["ix_0_1"] < 0
        if "ix_0_2" in suggestions:
            assert suggestions["ix_0_2"] < suggestions.get("ix_0_1", 0)

    def test_suggest_offsets_ns_corridor(self):
        decisions = {
            "ix_0_0": TrafficDecision(
                action="extend_green", phase="NS_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
            "ix_1_0": TrafficDecision(
                action="extend_green", phase="NS_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
        }
        graph = {
            "ix_0_0": ["ix_1_0"],
            "ix_1_0": ["ix_0_0"],
        }

        suggestions = GreenWaveAdvisor.suggest_offsets(decisions, graph, "NS")
        assert isinstance(suggestions, dict)

    def test_suggest_offsets_empty_decisions(self):
        graph = {"ix_0_0": ["ix_0_1"], "ix_0_1": ["ix_0_0"]}
        suggestions = GreenWaveAdvisor.suggest_offsets({}, graph)
        assert len(suggestions) == 0

    def test_suggest_offsets_single_intersection(self):
        decisions = {
            "ix_0_0": TrafficDecision(
                action="extend_green", phase="EW_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
        }
        graph = {"ix_0_0": []}

        suggestions = GreenWaveAdvisor.suggest_offsets(decisions, graph)
        # Single intersection corridor should have no suggestions
        assert len(suggestions) == 0

    def test_offsets_clamped_to_range(self):
        """Offsets should be clamped to [-10, +10]."""
        decisions = {
            f"ix_0_{i}": TrafficDecision(
                action="extend_green", phase="EW_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            )
            for i in range(10)
        }
        graph = {f"ix_0_{i}": [f"ix_0_{i+1}"] for i in range(9)}
        graph["ix_0_9"] = ["ix_0_8"]

        suggestions = GreenWaveAdvisor.suggest_offsets(decisions, graph, "EW")
        for offset in suggestions.values():
            assert -10 <= offset <= 10


class TestPriorityResolver:
    """Test conflict resolution by priority."""

    def _make_state(self, ix_id, queue_n=0, queue_s=0, queue_e=0, queue_w=0,
                    emergency=False, emergency_approach=None):
        return IntersectionState(
            intersection_id=ix_id,
            timestamp=0.0,
            queue_north=queue_n,
            queue_south=queue_s,
            queue_east=queue_e,
            queue_west=queue_w,
            emergency=emergency,
            emergency_approach=emergency_approach,
        )

    def test_no_conflicts_returns_original(self):
        decisions = {
            "ix_0_0": TrafficDecision(
                action="extend_green", phase="NS_GREEN",
                duration=30, reasoning="test", confidence=0.8,
            ),
        }
        states = {"ix_0_0": self._make_state("ix_0_0")}

        resolved = PriorityResolver.resolve(decisions, states, [])
        assert resolved == decisions

    def test_emergency_wins(self):
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
            "ix_0_0": self._make_state("ix_0_0", emergency=True, emergency_approach=0),
            "ix_0_1": self._make_state("ix_0_1"),
        }
        conflicts = [("ix_0_0", "ix_0_1", "phase_mismatch")]

        resolved = PriorityResolver.resolve(decisions, states, conflicts)
        # Emergency intersection keeps its phase
        assert resolved["ix_0_0"].phase == "NS_GREEN"
        # Loser gets opposite phase of winner
        assert resolved["ix_0_1"].phase == "EW_GREEN"

    def test_higher_queue_wins(self):
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
            "ix_0_0": self._make_state("ix_0_0", queue_n=10, queue_s=10),
            "ix_0_1": self._make_state("ix_0_1", queue_e=2, queue_w=2),
        }
        conflicts = [("ix_0_0", "ix_0_1", "phase_mismatch")]

        resolved = PriorityResolver.resolve(decisions, states, conflicts)
        # Higher queue intersection keeps its phase
        assert resolved["ix_0_0"].phase == "NS_GREEN"
        # Loser gets opposite phase of winner
        assert resolved["ix_0_1"].phase == "EW_GREEN"

    def test_tie_break_by_id(self):
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
            "ix_0_0": self._make_state("ix_0_0"),
            "ix_0_1": self._make_state("ix_0_1"),
        }
        conflicts = [("ix_0_0", "ix_0_1", "phase_mismatch")]

        resolved = PriorityResolver.resolve(decisions, states, conflicts)
        # ix_0_0 < ix_0_1, so ix_0_0 wins
        assert resolved["ix_0_0"].phase == "NS_GREEN"
        # Loser gets opposite phase of winner
        assert resolved["ix_0_1"].phase == "EW_GREEN"

    def test_missing_state_skipped(self):
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
        states = {"ix_0_0": self._make_state("ix_0_0")}
        conflicts = [("ix_0_0", "ix_0_1", "phase_mismatch")]

        resolved = PriorityResolver.resolve(decisions, states, conflicts)
        # Missing state means conflict is skipped
        assert resolved["ix_0_1"].phase == "EW_GREEN"
