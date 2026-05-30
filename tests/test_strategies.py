"""
Tests for Signal Control Strategies module.
"""

import pytest

from traffic_agent.optimization.strategies import (
    EmergencyPriorityStrategy,
    FixedTimingStrategy,
    QueueBalancingStrategy,
    StrategyDecision,
    StrategyRegistry,
    default_registry,
)


class TestStrategyDecision:
    """Test StrategyDecision data class."""

    def test_to_dict(self):
        decision = StrategyDecision(
            adjustment=5.0,
            reasoning="test",
            confidence=0.8,
            strategy_name="test_strategy",
        )
        d = decision.to_dict()
        assert d["adjustment"] == 5.0
        assert d["strategy"] == "test_strategy"


class TestFixedTimingStrategy:
    """Test FixedTimingStrategy."""

    def test_name(self):
        strategy = FixedTimingStrategy()
        assert strategy.name == "fixed"

    def test_always_returns_none(self):
        strategy = FixedTimingStrategy()
        result = strategy.decide(
            detector_data={"queue_north": 10},
            signal_state={"current_phase": "NS_GREEN"},
        )
        assert result is None


class TestQueueBalancingStrategy:
    """Test QueueBalancingStrategy."""

    def test_name(self):
        strategy = QueueBalancingStrategy()
        assert strategy.name == "queue_balancing"

    def test_no_adjustment_when_balanced(self):
        strategy = QueueBalancingStrategy()
        result = strategy.decide(
            detector_data={
                "queue_north": 5,
                "queue_south": 5,
                "queue_east": 5,
                "queue_west": 5,
            },
            signal_state={"current_phase": "NS_GREEN"},
        )
        assert result is None

    def test_adjust_when_ns_dominates_in_ew_phase(self):
        strategy = QueueBalancingStrategy()
        result = strategy.decide(
            detector_data={
                "queue_north": 10,
                "queue_south": 10,
                "queue_east": 1,
                "queue_west": 1,
            },
            signal_state={"current_phase": "EW_GREEN"},
        )
        assert result is not None
        assert result.adjustment < 0  # Shorten EW phase

    def test_adjust_when_ew_dominates_in_ns_phase(self):
        strategy = QueueBalancingStrategy()
        result = strategy.decide(
            detector_data={
                "queue_north": 1,
                "queue_south": 1,
                "queue_east": 10,
                "queue_west": 10,
            },
            signal_state={"current_phase": "NS_GREEN"},
        )
        assert result is not None
        assert result.adjustment < 0  # Shorten NS phase


class TestEmergencyPriorityStrategy:
    """Test EmergencyPriorityStrategy."""

    def test_name(self):
        strategy = EmergencyPriorityStrategy()
        assert strategy.name == "emergency_priority"

    def test_no_emergency(self):
        strategy = EmergencyPriorityStrategy()
        result = strategy.decide(
            detector_data={"emergency": False},
            signal_state={"current_phase": "NS_GREEN"},
        )
        assert result is None

    def test_emergency_ns_approach_in_ew_phase(self):
        strategy = EmergencyPriorityStrategy()
        result = strategy.decide(
            detector_data={"emergency": True, "emergency_approach": 0},
            signal_state={"current_phase": "EW_GREEN"},
        )
        assert result is not None
        assert result.adjustment == -10.0
        assert result.confidence == 1.0

    def test_emergency_ew_approach_in_ns_phase(self):
        strategy = EmergencyPriorityStrategy()
        result = strategy.decide(
            detector_data={"emergency": True, "emergency_approach": 1},
            signal_state={"current_phase": "NS_GREEN"},
        )
        assert result is not None
        assert result.adjustment == -10.0

    def test_emergency_already_green(self):
        strategy = EmergencyPriorityStrategy()
        result = strategy.decide(
            detector_data={"emergency": True, "emergency_approach": 0},
            signal_state={"current_phase": "NS_GREEN"},
        )
        assert result is None  # Already green for emergency


class TestStrategyRegistry:
    """Test StrategyRegistry."""

    def test_register_and_get(self):
        registry = StrategyRegistry()
        strategy = FixedTimingStrategy()
        registry.register(strategy)

        assert registry.get("fixed") is strategy
        assert registry.get("nonexistent") is None

    def test_list_strategies(self):
        registry = StrategyRegistry()
        registry.register(FixedTimingStrategy())
        registry.register(QueueBalancingStrategy())

        names = registry.list_strategies()
        assert "fixed" in names
        assert "queue_balancing" in names

    def test_decide_all(self):
        registry = StrategyRegistry()
        registry.register(FixedTimingStrategy())
        registry.register(QueueBalancingStrategy())

        decisions = registry.decide_all(
            detector_data={"queue_north": 5, "queue_south": 5, "queue_east": 5, "queue_west": 5},
            signal_state={"current_phase": "NS_GREEN"},
        )
        assert "fixed" in decisions
        assert "queue_balancing" in decisions

    def test_default_registry(self):
        assert "fixed" in default_registry.list_strategies()
        assert "queue_balancing" in default_registry.list_strategies()
        assert "emergency_priority" in default_registry.list_strategies()
