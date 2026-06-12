"""
Signal Control Strategies — Pluggable strategy interface for signal timing.

Defines a common interface for different signal control strategies,
allowing easy extension with new algorithms.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class StrategyDecision:
    """Decision from a signal control strategy."""

    adjustment: float  # seconds to adjust (±10s max)
    reasoning: str
    confidence: float  # 0.0 to 1.0
    strategy_name: str

    def __post_init__(self):
        # Clamp adjustment to ±10s for safety
        self.adjustment = max(-10.0, min(10.0, self.adjustment))
        # Clamp confidence to [0, 1]
        self.confidence = max(0.0, min(1.0, self.confidence))

    def to_dict(self) -> dict[str, Any]:
        return {
            "adjustment": self.adjustment,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "strategy": self.strategy_name,
        }


class SignalStrategy(ABC):
    """Abstract base class for signal control strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name."""
        ...

    @abstractmethod
    def decide(
        self,
        detector_data: dict[str, Any],
        signal_state: dict[str, Any],
        trend: dict[str, Any] | None = None,
    ) -> StrategyDecision | None:
        """
        Make a signal timing decision.

        Args:
            detector_data: Current detector readings
            signal_state: Current signal state
            trend: Optional trend analysis data

        Returns:
            StrategyDecision or None if no adjustment needed
        """
        ...

    def get_stats(self) -> dict[str, Any]:
        """Get strategy statistics."""
        return {"strategy": self.name}


class FixedTimingStrategy(SignalStrategy):
    """Fixed timing strategy — no adjustments."""

    @property
    def name(self) -> str:
        return "fixed"

    def decide(
        self,
        detector_data: dict[str, Any],
        signal_state: dict[str, Any],
        trend: dict[str, Any] | None = None,
    ) -> StrategyDecision | None:
        return None


class QueueBalancingStrategy(SignalStrategy):
    """Adjust timing to balance queue lengths across approaches."""

    @property
    def name(self) -> str:
        return "queue_balancing"

    def decide(
        self,
        detector_data: dict[str, Any],
        signal_state: dict[str, Any],
        trend: dict[str, Any] | None = None,
    ) -> StrategyDecision | None:
        queue_n = detector_data.get("queue_north", 0)
        queue_s = detector_data.get("queue_south", 0)
        queue_e = detector_data.get("queue_east", 0)
        queue_w = detector_data.get("queue_west", 0)

        ns_queue = queue_n + queue_s
        ew_queue = queue_e + queue_w

        current_phase = signal_state.get("current_phase", "NS_GREEN")

        # If NS has much more traffic and we're in EW phase, switch sooner
        if current_phase == "EW_GREEN" and ns_queue > ew_queue * 2:
            return StrategyDecision(
                adjustment=-5.0,
                reasoning=f"NS queue ({ns_queue}) much larger than EW ({ew_queue})",
                confidence=0.7,
                strategy_name=self.name,
            )

        # If EW has much more traffic and we're in NS phase, extend
        if current_phase == "NS_GREEN" and ew_queue > ns_queue * 2:
            return StrategyDecision(
                adjustment=-5.0,
                reasoning=f"EW queue ({ew_queue}) much larger than NS ({ns_queue})",
                confidence=0.7,
                strategy_name=self.name,
            )

        return None


class EmergencyPriorityStrategy(SignalStrategy):
    """Prioritize emergency vehicle approaches."""

    @property
    def name(self) -> str:
        return "emergency_priority"

    def decide(
        self,
        detector_data: dict[str, Any],
        signal_state: dict[str, Any],
        trend: dict[str, Any] | None = None,
    ) -> StrategyDecision | None:
        emergency = detector_data.get("emergency", False)
        emergency_approach = detector_data.get("emergency_approach")

        if not emergency:
            return None

        current_phase = signal_state.get("current_phase", "NS_GREEN")

        # Determine if emergency vehicle needs green
        # Approaches: 0=north, 1=east, 2=south, 3=west
        ns_approaches = {0, 2}
        ew_approaches = {1, 3}

        if emergency_approach in ns_approaches and current_phase != "NS_GREEN":
            return StrategyDecision(
                adjustment=-10.0,  # Maximum reduction to switch quickly
                reasoning=f"Emergency vehicle at approach {emergency_approach}",
                confidence=1.0,
                strategy_name=self.name,
            )

        if emergency_approach in ew_approaches and current_phase != "EW_GREEN":
            return StrategyDecision(
                adjustment=-10.0,
                reasoning=f"Emergency vehicle at approach {emergency_approach}",
                confidence=1.0,
                strategy_name=self.name,
            )

        return None


class StrategyRegistry:
    """Registry for signal control strategies."""

    def __init__(self):
        self._strategies: dict[str, SignalStrategy] = {}

    def register(self, strategy: SignalStrategy) -> None:
        """Register a strategy."""
        self._strategies[strategy.name] = strategy

    def get(self, name: str) -> SignalStrategy | None:
        """Get a strategy by name."""
        return self._strategies.get(name)

    def list_strategies(self) -> list[str]:
        """List all registered strategy names."""
        return list(self._strategies.keys())

    def decide_all(
        self,
        detector_data: dict[str, Any],
        signal_state: dict[str, Any],
        trend: dict[str, Any] | None = None,
    ) -> dict[str, StrategyDecision | None]:
        """Run all registered strategies and return their decisions."""
        return {
            name: strategy.decide(detector_data, signal_state, trend)
            for name, strategy in self._strategies.items()
        }


# Default registry with built-in strategies
default_registry = StrategyRegistry()
default_registry.register(FixedTimingStrategy())
default_registry.register(QueueBalancingStrategy())
default_registry.register(EmergencyPriorityStrategy())
