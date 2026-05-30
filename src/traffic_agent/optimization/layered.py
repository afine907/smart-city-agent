"""
Timing Decision Pipeline — 3-layer decision pipeline for ±10s adjustment.

Routes decisions through different layers based on complexity:
- Layer 1 (Rules):  Zero cost, instant. For simple/obvious cases.
- Layer 2 (Cache):  Zero cost, instant. For similar traffic patterns.
- Layer 3 (LLM):    Paid, slow. For complex scenarios requiring reasoning.

Usage:
    pipeline = TimingDecisionPipeline(llm_config)
    adjustment = pipeline.decide(detector_data, signal_state, trend)
"""

from __future__ import annotations


from typing import Any, Dict, List, Optional

from traffic_agent.llm.client import LLMClient, LLMConfig
from traffic_agent.llm.parser import TimingAdjustment, TimingAdjustmentParser
from traffic_agent.llm.prompts import (
    TIMING_ADJUSTMENT_SYSTEM,
    format_timing_message,
)
from traffic_agent.optimization.cache import DecisionCache
from traffic_agent.optimization.cost_tracker import CostTracker
from traffic_agent.optimization.rule_engine import TimingRuleEngine


class TimingDecisionPipeline:
    """
    Three-layer decision pipeline for timing adjustments.

    Layer flow:
        data → RuleEngine → (hit? return) → Cache → (hit? return) → LLM

    The pipeline decides whether to adjust the current green phase
    duration by ±10 seconds based on traffic conditions.
    """

    def __init__(
        self,
        llm_config: Optional[LLMConfig] = None,
        cost_tracker: Optional[CostTracker] = None,
    ):
        self.llm_config = llm_config or LLMConfig()
        self.llm_client = LLMClient(self.llm_config)
        self.rule_engine = TimingRuleEngine()
        self.cache = DecisionCache(max_size=2000, ttl_seconds=30.0)
        self.cost_tracker = cost_tracker

        # Stats
        self._layer1_hits = 0
        self._layer2_hits = 0
        self._layer3_calls = 0
        self._total_decisions = 0
        self._adjustment_history: List[Dict] = []

    def decide(
        self,
        detector_data: Dict,
        signal_state: Dict,
        trend: Optional[Dict[str, List[int]]] = None,
        intersection_id: str = "unknown",
        intersection_type: str = "crossroad",
    ) -> TimingAdjustment:
        """
        Make a timing adjustment through the layered pipeline.

        Args:
            detector_data: dict with readings per direction
            signal_state: dict with current_phase, phase_remaining, etc.
            trend: optional trend data
            intersection_id: ID of the intersection
            intersection_type: "crossroad" or "tjunction"

        Returns:
            TimingAdjustment with adjustment value and reasoning
        """
        self._total_decisions += 1

        # Layer 1: Rules
        rule_result = self.rule_engine.decide(detector_data, signal_state, trend)
        if rule_result is not None:
            self._layer1_hits += 1
            self._record_adjustment(rule_result, intersection_id)
            return rule_result

        # Layer 2: Cache
        cache_key = self._make_cache_key(detector_data, signal_state)
        cached = self.cache.get(cache_key)
        if cached is not None and isinstance(cached, TimingAdjustment):
            self._layer2_hits += 1
            # Return a copy to avoid mutating the cached object
            result = TimingAdjustment(
                adjustment=cached.adjustment,
                reasoning=cached.reasoning,
                confidence=cached.confidence,
                source="cache",
            )
            self._record_adjustment(result, intersection_id)
            return result

        # Layer 3: LLM
        llm_result = self._call_llm(
            detector_data, signal_state, trend,
            intersection_id, intersection_type,
        )
        self._layer3_calls += 1

        # Cache the result
        self.cache.set(cache_key, llm_result)
        self._record_adjustment(llm_result, intersection_id)

        return llm_result

    def _call_llm(
        self,
        detector_data: Dict,
        signal_state: Dict,
        trend: Optional[Dict[str, List[int]]],
        intersection_id: str,
        intersection_type: str,
    ) -> TimingAdjustment:
        """Call LLM for timing adjustment."""
        # Format the user message
        user_message = format_timing_message(
            intersection_id=intersection_id,
            intersection_type=intersection_type,
            current_phase=signal_state.get("current_phase", "NS_GREEN"),
            base_duration=signal_state.get("base_duration", 60.0),
            phase_elapsed=signal_state.get("phase_elapsed", 0.0),
            phase_remaining=signal_state.get("phase_remaining", 30.0),
            detector_data=detector_data,
            ns_trend=trend.get("ns_total", []) if trend else [],
            ew_trend=trend.get("ew_total", []) if trend else [],
            recent_adjustments=self._adjustment_history[-3:],
        )

        # Use fast model for LLM calls (cost-efficient)
        model = self.llm_config.fast_model

        response = self.llm_client.chat(
            system_prompt=TIMING_ADJUSTMENT_SYSTEM,
            user_message=user_message,
            model=model,
            temperature=0.3,
        )

        # Track cost
        if self.cost_tracker:
            self.cost_tracker.record(
                intersection_id=intersection_id,
                model=model,
                prompt_tokens=response.tokens_input,
                completion_tokens=response.tokens_output,
            )

        # Parse response
        result = TimingAdjustmentParser.parse(response.content)
        if result is None:
            result = TimingAdjustmentParser.fallback("LLM响应解析失败")

        return result

    def _make_cache_key(self, detector_data: Dict, signal_state: Dict) -> str:
        """Create a coarse-grained cache key from detector data."""
        readings = detector_data.get("readings", {})

        def bin_value(v: int) -> int:
            return v // 3  # bin to groups of 3

        north = bin_value(readings.get("north", {}).get("vehicles", 0))
        south = bin_value(readings.get("south", {}).get("vehicles", 0))
        east = bin_value(readings.get("east", {}).get("vehicles", 0))
        west = bin_value(readings.get("west", {}).get("vehicles", 0))
        phase = signal_state.get("current_phase", "NS_GREEN")

        return f"{north}_{south}_{east}_{west}_{phase}"

    def _record_adjustment(self, adjustment: TimingAdjustment, intersection_id: str) -> None:
        """Record adjustment for history."""
        self._adjustment_history.append({
            "intersection_id": intersection_id,
            "adjustment": adjustment.adjustment,
            "reason": adjustment.reasoning,
            "source": adjustment.source,
        })
        # Keep only last 10
        if len(self._adjustment_history) > 10:
            self._adjustment_history = self._adjustment_history[-10:]

    def get_stats(self) -> Dict[str, Any]:
        """Return pipeline statistics."""
        total = max(1, self._total_decisions)
        return {
            "total_decisions": self._total_decisions,
            "layer1_rules": self._layer1_hits,
            "layer2_cache": self._layer2_hits,
            "layer3_llm": self._layer3_calls,
            "rule_rate": self._layer1_hits / total,
            "cache_rate": self._layer2_hits / total,
            "llm_rate": self._layer3_calls / total,
            "free_rate": (self._layer1_hits + self._layer2_hits) / total,
            "rule_engine": self.rule_engine.get_stats(),
            "cache_size": self.cache.size,
        }

    def reset(self) -> None:
        """Reset pipeline state."""
        self._layer1_hits = 0
        self._layer2_hits = 0
        self._layer3_calls = 0
        self._total_decisions = 0
        self._adjustment_history = []
        self.rule_engine.reset_stats()
        self.cache.clear()


# Backward compatibility alias
LayeredDecisionMaker = TimingDecisionPipeline
