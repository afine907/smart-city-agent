"""
Rule-Only Pipeline — convenience wrapper for rule-engine-only decisions.

Used when LLM is not available or not desired. Returns rule engine decisions
with a fallback to no-adjustment when no rule matches.
"""

from __future__ import annotations


from traffic_agent.llm.parser import TimingAdjustment
from traffic_agent.optimization.rule_engine import TimingRuleEngine


class RuleOnlyPipeline:
    """Pipeline that uses only the rule engine (no LLM, no cache)."""

    def __init__(self):
        self.rule_engine = TimingRuleEngine()
        self._stats = {"total_decisions": 0, "layer1_rules": 0}

    def decide(self, detector_data, signal_state, trend=None, **kwargs):
        self._stats["total_decisions"] += 1
        result = self.rule_engine.decide(detector_data, signal_state, trend)
        if result:
            self._stats["layer1_rules"] += 1
            return result
        return TimingAdjustment.no_adjustment("规则未命中，不调整")

    def get_stats(self):
        total = max(1, self._stats["total_decisions"])
        # All decisions are free (rule engine or fallback), no LLM cost
        free_decisions = self._stats["total_decisions"]
        return {
            **self._stats,
            "rule_rate": self._stats["layer1_rules"] / total,
            "layer2_cache": 0,
            "layer3_llm": 0,
            "free_decisions": free_decisions,
            "free_rate": free_decisions / total,
        }
