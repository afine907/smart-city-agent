"""
Layered Decision Maker — simple → fast → complex decision pipeline.

Routes decisions through different layers based on complexity:
- Layer 1 (Rules):  Zero cost, instant. For simple/obvious cases.
- Layer 2 (Fast):   Low cost, fast. For moderate complexity.
- Layer 3 (Smart):  Higher cost, thorough. For complex coordination.

Usage:
    maker = LayeredDecisionMaker(llm_config)
    decision = maker.decide(state, neighbors)
"""

from typing import Any, Dict, List, Optional

from traffic_agent.llm.client import LLMClient, LLMConfig
from traffic_agent.llm.parser import ResponseParser, TrafficDecision
from traffic_agent.optimization.cache import DecisionCache
from traffic_agent.optimization.cost_tracker import CostTracker
from traffic_agent.optimization.rule_engine import RuleEngine
from traffic_agent.tools.traffic_tools import (
    COORDINATOR_PROMPT,
    TRAFFIC_EXPERT_PROMPT,
    IntersectionState,
)


class LayeredDecisionMaker:
    """
    Three-layer decision pipeline.

    Layer flow:
        state → RuleEngine → (hit? return) → Cache → (hit? return) → LLM

    LLM selection:
        - Simple (queue < threshold): Fast model
        - Complex (conflicts, emergencies): Smart model
    """

    def __init__(
        self,
        llm_config: Optional[LLMConfig] = None,
        cost_tracker: Optional[CostTracker] = None,
        simple_threshold: int = 8,
        complex_threshold: int = 15,
    ):
        self.llm_config = llm_config or LLMConfig()
        self.llm_client = LLMClient(self.llm_config)
        self.rule_engine = RuleEngine()
        self.cache = DecisionCache(max_size=2000, ttl_seconds=30.0)
        self.cost_tracker = cost_tracker
        self.simple_threshold = simple_threshold
        self.complex_threshold = complex_threshold

        # Stats
        self._layer1_hits = 0
        self._layer2_hits = 0
        self._layer3_calls = 0
        self._total_decisions = 0

    def decide(
        self,
        state: IntersectionState,
        neighbors: Optional[Dict[str, IntersectionState]] = None,
    ) -> TrafficDecision:
        """
        Make a decision through the layered pipeline.

        1. Try rule engine (free, instant)
        2. Try cache (free, instant)
        3. Call LLM (costs money, slow)
        """
        self._total_decisions += 1

        # Layer 1: Rules
        rule_decision = self.rule_engine.decide(state, neighbors)
        if rule_decision is not None:
            self._layer1_hits += 1
            return rule_decision

        # Layer 2: Cache
        cached = self.cache.get(state)
        if cached is not None:
            self._layer2_hits += 1
            return cached

        # Layer 3: LLM (select model based on complexity)
        complexity = self._assess_complexity(state, neighbors)
        if complexity == "simple":
            model = self.llm_config.fast_model
        else:
            model = self.llm_config.smart_model

        decision = self._call_llm(state, neighbors, model)
        self._layer3_calls += 1

        # Cache the result
        self.cache.set(state, decision)

        return decision

    def _assess_complexity(
        self,
        state: IntersectionState,
        neighbors: Optional[Dict[str, IntersectionState]] = None,
    ) -> str:
        """Assess decision complexity: simple, moderate, complex."""
        total_queue = state.get_total_queue()
        max_queue = state.get_max_queue()

        # Emergency → complex
        if state.emergency:
            return "complex"

        # Very high queue → complex
        if max_queue >= self.complex_threshold:
            return "complex"

        # Neighbor conflicts → complex
        if neighbors:
            for nid, ns in neighbors.items():
                # Both have high demand but different preferred phases
                if (state.queue_north + state.queue_south > 10 and
                    ns.queue_east + ns.queue_west > 10):
                    return "complex"

        # Moderate queue → moderate
        if max_queue >= self.simple_threshold:
            return "moderate"

        return "simple"

    def _call_llm(
        self,
        state: IntersectionState,
        neighbors: Optional[Dict[str, IntersectionState]],
        model: str,
    ) -> TrafficDecision:
        """Call LLM for decision."""
        # Build neighbor text
        neighbor_text = ""
        if neighbors:
            neighbor_text = "\n".join(
                f"  {nid}: 排队{ns.get_total_queue()}辆, {ns.current_phase}"
                for nid, ns in neighbors.items()
            )

        user_message = f"""当前路况：
{state.to_text()}

邻居路口：
{neighbor_text}

请做出信号灯决策（JSON格式）。"""

        response = self.llm_client.chat(
            system_prompt=TRAFFIC_EXPERT_PROMPT.format(
                intersection_id=state.intersection_id
            ),
            user_message=user_message,
            model=model,
            temperature=0.3,
        )

        # Track cost
        if self.cost_tracker:
            self.cost_tracker.record(
                intersection_id=state.intersection_id,
                model=model,
                prompt_tokens=response.tokens_input,
                completion_tokens=response.tokens_output,
            )

        decision = ResponseParser.parse(response.content)
        if decision is None:
            decision = ResponseParser.fallback("LLM响应解析失败")

        return decision

    def get_stats(self) -> Dict[str, Any]:
        """Return layered decision statistics."""
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
