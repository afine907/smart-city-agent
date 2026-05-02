"""
Rule Engine — Fast rule-based decisions for simple scenarios.

Avoids LLM calls when traffic patterns are predictable.
Falls back to LLM when rules don't cover the situation.
"""

from typing import Optional

from traffic_agent.llm.parser import TrafficDecision
from traffic_agent.tools.traffic_tools import IntersectionState


# Decision constants
NS_GREEN = "NS_GREEN"
EW_GREEN = "EW_GREEN"
ALL_RED = "ALL_RED"


class RuleEngine:
    """
    Rule-based traffic signal decision engine.
    
    Handles common scenarios without LLM:
    - Low traffic: keep current phase
    - Moderate imbalance: switch to high-demand phase
    - Severe congestion: extend green for congested direction
    - Balanced traffic: default timing
    
    Returns None when the situation requires LLM reasoning.
    
    Usage:
        engine = RuleEngine()
        decision = engine.decide(state, neighbors)
        if decision is None:
            decision = call_llm(state)
    """
    
    def __init__(
        self,
        low_threshold: int = 3,
        high_threshold: int = 10,
        severe_threshold: int = 20,
    ):
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold
        self.severe_threshold = severe_threshold
        self._decisions_made = 0
        self._decisions_skipped = 0
    
    def decide(
        self,
        state: IntersectionState,
        neighbor_states: Optional[dict] = None,
    ) -> Optional[TrafficDecision]:
        """
        Make a rule-based decision.
        
        Returns TrafficDecision if rules apply, None if LLM is needed.
        """
        ns_queue = state.queue_north + state.queue_south
        ew_queue = state.queue_east + state.queue_west
        max_queue = max(ns_queue, ew_queue)
        total_queue = ns_queue + ew_queue
        current = state.current_phase
        
        # Rule 1: Very low traffic — keep current phase
        if total_queue < self.low_threshold:
            self._decisions_made += 1
            return TrafficDecision(
                action="extend_green",
                phase=current,
                duration=15,
                reasoning=f"规则引擎: 交通量低({total_queue}辆), 保持当前相位",
                confidence=0.9,
            )
        
        # Rule 2: Severe congestion on one direction — extend green for it
        if max_queue >= self.severe_threshold:
            if ns_queue > ew_queue:
                self._decisions_made += 1
                return TrafficDecision(
                    action="extend_green",
                    phase=NS_GREEN,
                    duration=45,
                    reasoning=f"规则引擎: 南北方向严重拥堵({ns_queue}辆), 延长绿灯",
                    confidence=0.85,
                )
            else:
                self._decisions_made += 1
                return TrafficDecision(
                    action="extend_green",
                    phase=EW_GREEN,
                    duration=45,
                    reasoning=f"规则引擎: 东西方向严重拥堵({ew_queue}辆), 延长绿灯",
                    confidence=0.85,
                )
        
        # Rule 3: Moderate imbalance — switch to high-demand direction
        if max_queue >= self.high_threshold:
            imbalance = abs(ns_queue - ew_queue)
            if imbalance >= 5:
                if ns_queue > ew_queue and current != NS_GREEN:
                    self._decisions_made += 1
                    return TrafficDecision(
                        action="switch_phase",
                        phase=NS_GREEN,
                        duration=30,
                        reasoning=f"规则引擎: 南北需求更高({ns_queue}vs{ew_queue}), 切换相位",
                        confidence=0.8,
                    )
                elif ew_queue > ns_queue and current != EW_GREEN:
                    self._decisions_made += 1
                    return TrafficDecision(
                        action="switch_phase",
                        phase=EW_GREEN,
                        duration=30,
                        reasoning=f"规则引擎: 东西需求更高({ew_queue}vs{ns_queue}), 切换相位",
                        confidence=0.8,
                    )
        
        # Rule 4: Balanced traffic — default equal timing
        if total_queue >= self.low_threshold:
            imbalance = abs(ns_queue - ew_queue)
            if imbalance <= 3:
                # Balanced — keep current or use default
                self._decisions_made += 1
                return TrafficDecision(
                    action="extend_green",
                    phase=current,
                    duration=20,
                    reasoning=f"规则引擎: 交通均衡({ns_queue}vs{ew_queue}), 保持当前相位",
                    confidence=0.7,
                )
        
        # Rules don't cover this — need LLM
        self._decisions_skipped += 1
        return None
    
    def get_stats(self) -> dict:
        """Return rule engine statistics."""
        total = self._decisions_made + self._decisions_skipped
        return {
            "decisions_made": self._decisions_made,
            "decisions_skipped": self._decisions_skipped,
            "total": total,
            "rule_coverage": self._decisions_made / max(1, total),
        }
    
    def reset_stats(self) -> None:
        """Reset statistics."""
        self._decisions_made = 0
        self._decisions_skipped = 0
