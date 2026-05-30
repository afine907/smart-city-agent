"""
Tests for Layered Decision Pipeline module.
"""

import pytest
from unittest.mock import MagicMock, patch

from traffic_agent.llm.parser import TimingAdjustment
from traffic_agent.optimization.layered import TimingDecisionPipeline


class TestTimingDecisionPipeline:
    """Test TimingDecisionPipeline."""

    def test_initialization(self):
        """Test pipeline can be initialized."""
        pipeline = TimingDecisionPipeline()
        assert pipeline is not None

    def test_decide_with_rule_hit(self):
        """Test decision when rule engine hits."""
        pipeline = TimingDecisionPipeline()

        detector_data = {
            "queue_north": 0,
            "queue_south": 0,
            "queue_east": 0,
            "queue_west": 0,
        }
        signal_state = {
            "current_phase": "NS_GREEN",
            "phase_duration": 30.0,
        }

        # Low traffic should trigger rule
        result = pipeline.decide(detector_data, signal_state)
        assert result is not None
        assert isinstance(result, TimingAdjustment)

    def test_get_stats(self):
        """Test stats retrieval."""
        pipeline = TimingDecisionPipeline()
        stats = pipeline.get_stats()
        assert "total_decisions" in stats

    def test_decide_with_cache_hit(self):
        """Test decision when cache hits."""
        pipeline = TimingDecisionPipeline()

        detector_data = {
            "queue_north": 5,
            "queue_south": 3,
            "queue_east": 8,
            "queue_west": 2,
        }
        signal_state = {
            "current_phase": "NS_GREEN",
            "phase_duration": 30.0,
        }

        # First call - may hit rule or cache miss
        result1 = pipeline.decide(detector_data, signal_state)

        # Second call - should hit cache if first didn't hit rule
        result2 = pipeline.decide(detector_data, signal_state)

        # Both should return valid results
        assert result1 is not None
        assert result2 is not None

    def test_decide_returns_timing_adjustment(self):
        """Test that decide returns TimingAdjustment."""
        pipeline = TimingDecisionPipeline()

        detector_data = {
            "queue_north": 10,
            "queue_south": 10,
            "queue_east": 15,
            "queue_west": 12,
        }
        signal_state = {
            "current_phase": "NS_GREEN",
            "phase_duration": 30.0,
        }

        result = pipeline.decide(detector_data, signal_state)
        assert isinstance(result, TimingAdjustment)
        assert -10 <= result.adjustment <= 10

    def test_stats_track_decisions(self):
        """Test that stats track decision counts."""
        pipeline = TimingDecisionPipeline()

        detector_data = {
            "queue_north": 5,
            "queue_south": 3,
            "queue_east": 8,
            "queue_west": 2,
        }
        signal_state = {
            "current_phase": "NS_GREEN",
            "phase_duration": 30.0,
        }

        pipeline.decide(detector_data, signal_state)
        stats = pipeline.get_stats()

        assert stats["total_decisions"] >= 1
