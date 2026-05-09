"""
Traffic Control Crew — CrewAI multi-agent orchestration for traffic management.

Uses CrewAI framework to create agents for each intersection and a coordinator.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from crewai import Agent, Task, Crew, Process

from traffic_agent.llm.client import LLMClient, LLMConfig
from traffic_agent.llm.parser import ResponseParser, TrafficDecision
from traffic_agent.optimization.cache import DecisionCache
from traffic_agent.tools.traffic_tools import (
    IntersectionState,
    TRAFFIC_EXPERT_PROMPT,
    COORDINATOR_PROMPT,
)
from traffic_agent.crew.coordination import ConflictDetector


@dataclass
class CrewConfig:
    """Configuration for the traffic control crew."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    decision_interval: float = 5.0
    enable_coordination: bool = True
    use_cache: bool = True


class TrafficControlCrew:
    """
    CrewAI-based multi-agent orchestrator for traffic signal control.

    Uses CrewAI Agent, Task, and Crew classes for proper multi-agent coordination.
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

        # LLM client for direct calls (fallback)
        self.llm_client = LLMClient(self.config.llm)

        # Cache
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
        self._last_cache_hit = False

        # Create CrewAI agents
        self._create_agents()

    def _create_agents(self):
        """Create CrewAI agents for each intersection and coordinator."""
        from crewai.llms import LLM

        self.intersection_agents: Dict[str, Agent] = {}
        self.intersection_tasks: Dict[str, Task] = {}

        # Create LLM instances using our config
        fast_llm = LLM(
            model=f"openai/{self.config.llm.fast_model}",
            api_key=self.config.llm.api_key,
            base_url=self.config.llm.api_base,
        )
        smart_llm = LLM(
            model=f"openai/{self.config.llm.smart_model}",
            api_key=self.config.llm.api_key,
            base_url=self.config.llm.api_base,
        )

        for ix_id in self.intersection_ids:
            neighbors = self.graph.get(ix_id, [])

            agent = Agent(
                role=f"Traffic Signal Controller for {ix_id}",
                goal=f"Minimize vehicle wait time at {ix_id} intersection while coordinating with neighbors: {neighbors}",
                backstory=TRAFFIC_EXPERT_PROMPT.format(intersection_id=ix_id),
                verbose=False,
                allow_delegation=False,
                llm=fast_llm,
            )
            self.intersection_agents[ix_id] = agent

        # Coordinator agent
        self.coordinator_agent = Agent(
            role="Traffic Coordination Supervisor",
            goal="Resolve conflicts between intersection agents and optimize city-wide traffic flow",
            backstory=COORDINATOR_PROMPT,
            verbose=False,
            allow_delegation=False,
            llm=smart_llm,
        )

    def step(self, engine) -> List[Dict[str, Any]]:
        """
        Execute one decision cycle using CrewAI.

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
            t0 = time.time()
            decision = self._agent_decide(ix_id, states[ix_id], states)
            duration_ms = (time.time() - t0) * 1000
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

        if len(self._decision_history) > 1000:
            self._decision_history = self._decision_history[-500:]

        return decisions

    def _agent_decide(
        self,
        intersection_id: str,
        state: IntersectionState,
        all_states: Dict[str, IntersectionState],
    ) -> TrafficDecision:
        """Get decision from an intersection agent using CrewAI."""

        self._last_cache_hit = False

        # Check cache first
        if self.cache:
            cached = self.cache.get(state)
            if cached:
                self._total_cache_hits += 1
                self._last_cache_hit = True
                return cached

        # Build neighbor info
        neighbor_ids = self.graph.get(intersection_id, [])
        neighbor_text = "\n".join(
            f"  {nid}: 排队{all_states[nid].get_total_queue()}辆, "
            f"信号{all_states[nid].current_phase}"
            for nid in neighbor_ids if nid in all_states
        )

        # Create task for this intersection
        task_description = f"""当前路况：
{state.to_text()}

邻居路口：
{neighbor_text}

请做出信号灯决策（JSON格式）：{{"action": "extend_green/switch_phase", "phase": "NS_GREEN/EW_GREEN", "duration": 秒数, "reasoning": "理由"}}"""

        task = Task(
            description=task_description,
            agent=self.intersection_agents[intersection_id],
            expected_output="JSON decision with action/phase/duration/reasoning",
        )

        # Run single-agent crew
        crew = Crew(
            agents=[self.intersection_agents[intersection_id]],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        self._total_llm_calls += 1

        # Parse response
        decision = ResponseParser.parse(str(result))
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

        # Build coordination task
        decisions_text = "\n".join(
            f"{ix_id}: {d.to_dict()}"
            for ix_id, d in decisions.items()
        )

        states_text = "\n".join(
            f"{ix_id}: {s.to_text()}"
            for ix_id, s in states.items()
        )

        task_description = f"""各路口决策：
{decisions_text}

各路口状态：
{states_text}

发现 {len(conflicts)} 个冲突：
{self._format_conflicts(conflicts)}

请协调解决冲突，输出最终决策（JSON格式）。"""

        task = Task(
            description=task_description,
            agent=self.coordinator_agent,
            expected_output="Coordinated JSON decisions",
        )

        # Run coordinator crew
        crew = Crew(
            agents=[self.coordinator_agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        self._total_llm_calls += 1

        # Parse coordinator response
        try:
            content = str(result)
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(content[start:end])
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
        except (json.JSONDecodeError, ValueError):
            pass

        return decisions

    def _format_conflicts(self, conflicts: list) -> str:
        return "\n".join(
            f"  - {c[0]} 和 {c[1]}: {c[2]}"
            for c in conflicts
        )

    def get_metrics(self) -> Dict[str, Any]:
        """Return crew metrics."""
        cache_hit_rate = (
            self._total_cache_hits / max(1, self._total_decisions)
        )

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
