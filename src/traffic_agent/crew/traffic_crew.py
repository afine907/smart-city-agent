"""
Traffic Control Crew — CrewAI orchestration for traffic management.

This is the main entry point for the multi-agent system.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from traffic_agent.llm.client import LLMClient, LLMConfig
from traffic_agent.llm.parser import ResponseParser, TrafficDecision
from traffic_agent.optimization.cache import DecisionCache
from traffic_agent.tools.traffic_tools import (
    IntersectionState,
    CoordinationMessageTool,
    EmergencyAlertTool,
    TRAFFIC_EXPERT_PROMPT,
    COORDINATOR_PROMPT,
)
from traffic_agent.crew.coordination import ConflictDetector


@dataclass
class CrewConfig:
    """Configuration for the traffic control crew."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    decision_interval: float = 5.0     # Seconds between decisions
    max_coordination_rounds: int = 3
    enable_coordination: bool = True
    use_cache: bool = True
    verbose: bool = False


class TrafficControlCrew:
    """
    Main orchestrator for LLM multi-agent traffic control.

    Workflow per decision cycle:
    1. Collect traffic states from simulation
    2. Each intersection agent observes and decides (LLM call)
    3. Coordinator agent resolves conflicts (LLM call)
    4. Execute decisions in simulation
    5. Record reasoning and metrics

    Usage:
        crew = TrafficControlCrew(intersections, graph, config)

        # Decision cycle
        decisions = crew.step(simulation_engine)
    """

    def __init__(
        self,
        intersection_ids: List[str],
        graph: Dict[str, List[str]],
        config: Optional[CrewConfig] = None,
    ):
        self.intersection_ids = intersection_ids
        self.graph = graph
        self.config = config or CrewConfig()

        # LLM client
        self.llm_client = LLMClient(self.config.llm)

        # Tools
        self.coordination_tool = CoordinationMessageTool()
        self.emergency_tool = EmergencyAlertTool()

        # Cache — from optimization module
        self.cache: Optional[DecisionCache] = (
            DecisionCache(max_size=1000, ttl_seconds=60.0)
            if self.config.use_cache
            else None
        )

        # Metrics
        self._total_llm_calls = 0
        self._total_cache_hits = 0
        self._total_decisions = 0
        self._decision_history: List[Dict] = []

        # Try to create CrewAI agents (optional)
        self._use_crewai = self._try_init_crewai()

    def step(self, engine) -> List[Dict[str, Any]]:
        """
        Execute one decision cycle.

        Args:
            engine: SimulationEngine or GridSimulation instance

        Returns:
            List of decisions made
        """
        decisions = []

        # 1. Collect all states
        states: Dict[str, IntersectionState] = {}
        for ix_id in self.intersection_ids:
            states[ix_id] = engine.get_state(ix_id)

        # 2. Each agent makes independent decision
        agent_decisions: Dict[str, TrafficDecision] = {}
        for ix_id in self.intersection_ids:
            decision = self._agent_decide(ix_id, states[ix_id], states)
            agent_decisions[ix_id] = decision

        # 3. Coordinate if enabled
        if self.config.enable_coordination:
            agent_decisions = self._coordinate(agent_decisions, states)

        # 4. Execute decisions
        for ix_id, decision in agent_decisions.items():
            engine.apply_decision(ix_id, decision.to_dict())
            decisions.append({
                "intersection_id": ix_id,
                **decision.to_dict(),
            })

        # 5. Record
        self._total_decisions += len(decisions)
        self._decision_history.append({
            "timestamp": time.time(),
            "decisions": decisions,
        })

        # Keep history manageable
        if len(self._decision_history) > 1000:
            self._decision_history = self._decision_history[-500:]

        return decisions

    def _agent_decide(
        self,
        intersection_id: str,
        state: IntersectionState,
        all_states: Dict[str, IntersectionState],
    ) -> TrafficDecision:
        """Get decision from an intersection agent."""

        # Check cache first
        if self.cache:
            cached = self.cache.get(state)
            if cached:
                self._total_cache_hits += 1
                return cached

        # Build prompt
        neighbor_ids = self.graph.get(intersection_id, [])
        neighbor_text = "\n".join(
            f"  {nid}: 排队{all_states[nid].get_total_queue()}辆, "
            f"信号{all_states[nid].current_phase}"
            for nid in neighbor_ids if nid in all_states
        )

        user_message = f"""当前路况：
{state.to_text()}

邻居路口：
{neighbor_text}

请做出信号灯决策（JSON格式）。"""

        # Call LLM
        response = self.llm_client.chat(
            system_prompt=TRAFFIC_EXPERT_PROMPT.format(
                intersection_id=intersection_id
            ),
            user_message=user_message,
            model=self.config.llm.fast_model,
            temperature=0.3,
        )

        self._total_llm_calls += 1

        # Parse response
        decision = ResponseParser.parse(response.content)
        if decision is None:
            decision = ResponseParser.fallback("LLM响应解析失败")

        # Cache
        if self.cache:
            self.cache.set(state, decision)

        return decision

    def _coordinate(
        self,
        decisions: Dict[str, TrafficDecision],
        states: Dict[str, IntersectionState],
    ) -> Dict[str, TrafficDecision]:
        """Coordinate between agents to resolve conflicts."""

        # Check for conflicts
        conflicts = ConflictDetector.detect(decisions, self.graph)

        if not conflicts:
            return decisions

        # Build coordination prompt
        decisions_text = "\n".join(
            f"{ix_id}: {d.to_dict()}"
            for ix_id, d in decisions.items()
        )

        states_text = "\n".join(
            f"{ix_id}: {s.to_text()}"
            for ix_id, s in states.items()
        )

        user_message = f"""各路口决策：
{decisions_text}

各路口状态：
{states_text}

发现 {len(conflicts)} 个冲突：
{self._format_conflicts(conflicts)}

请协调解决冲突，输出最终决策（JSON格式）。"""

        # Call coordinator LLM
        response = self.llm_client.chat(
            system_prompt=COORDINATOR_PROMPT,
            user_message=user_message,
            model=self.config.llm.smart_model,
            temperature=0.2,
        )

        self._total_llm_calls += 1

        # Parse coordinator response
        try:
            data = json.loads(response.content)
            coordinated = {}
            for d in data.get("decisions", []):
                ix_id = d.get("intersection_id")
                if ix_id in decisions:
                    decision = ResponseParser.parse(json.dumps(d))
                    if decision:
                        coordinated[ix_id] = decision
                    else:
                        coordinated[ix_id] = decisions[ix_id]
                else:
                    coordinated[ix_id] = decisions[ix_id]
            return coordinated
        except (json.JSONDecodeError, KeyError):
            return decisions  # Fall back to original decisions

    def _format_conflicts(self, conflicts: list) -> str:
        return "\n".join(
            f"  - {c[0]} 和 {c[1]}: {c[2]}"
            for c in conflicts
        )

    def _try_init_crewai(self) -> bool:
        """Try to initialize CrewAI agents."""
        try:
            from traffic_agent.agents.intersection import (
                IntersectionAgentFactory,
                CoordinatorAgentFactory,
            )

            self.crewai_agents = {}
            for ix_id in self.intersection_ids:
                neighbors = self.graph.get(ix_id, [])
                self.crewai_agents[ix_id] = IntersectionAgentFactory.create(
                    ix_id, neighbors, self.config.llm
                )

            self.coordinator_agent = CoordinatorAgentFactory.create(
                self.intersection_ids, self.config.llm
            )

            return True
        except (ImportError, Exception):
            return False

    def get_metrics(self) -> Dict[str, Any]:
        """Return crew metrics."""
        cache_hit_rate = (
            self._total_cache_hits / max(1, self._total_decisions)
        )

        cache_stats = self.cache.stats if self.cache else None

        return {
            "total_decisions": self._total_decisions,
            "total_llm_calls": self._total_llm_calls,
            "total_cache_hits": self._total_cache_hits,
            "cache_hit_rate": cache_hit_rate,
            "cache_size": self.cache.size if self.cache else 0,
            "llm_stats": self.llm_client.get_stats(),
            "history_size": len(self._decision_history),
        }

    def get_reasoning_history(self, intersection_id: str, limit: int = 10) -> List[Dict]:
        """Get recent reasoning history for an intersection."""
        history = []
        for record in reversed(self._decision_history):
            for d in record["decisions"]:
                if d.get("intersection_id") == intersection_id:
                    history.append(d)
                    if len(history) >= limit:
                        return history
        return history
