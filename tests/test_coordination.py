"""
Tests for Multi-Agent Coordination
"""

import pytest

from traffic_agent.crew.coordination import ConflictDetector
from traffic_agent.llm.parser import TrafficDecision


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
