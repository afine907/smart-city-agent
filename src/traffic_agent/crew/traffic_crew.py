"""
Traffic Control Crew — CrewAI multi-agent orchestration for traffic management.

Uses CrewAI framework with 3-tier decision pipeline:
  Layer 1: Rule engine (free, instant)
  Layer 2: Decision cache (free, instant)
  Layer 3: LLM via CrewAI agents (paid, reasoning)

Agents interact with the simulation through CrewAI tools.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from traffic_agent.llm.client import LLMConfig
from traffic_agent.llm.parser import ResponseParser, TrafficDecision
from traffic_agent.optimization.cache import DecisionCache
from traffic_agent.optimization.rule_engine import TimingRuleEngine
from traffic_agent.tools.traffic_tools import (
    IntersectionState,
    SimulationState,
    _create_tools,
    set_sim_state,
)
from traffic_agent.crew.coordination import ConflictDetector


# Guardrail: validate that LLM output contains required signal decision fields
def _validate_signal_decision(output) -> tuple[bool, Any]:
    """Function-based guardrail: check LLM output has valid JSON decision."""
    # CrewAI 1.14+ passes TaskOutput object; extract raw string
    if hasattr(output, 'raw'):
        output = output.raw
    if not isinstance(output, str):
        output = str(output)
    try:
        # CrewAI 1.14.x passes TaskOutput object; extract raw string
        text = output.raw if hasattr(output, 'raw') else str(output)
        # Find JSON in the output
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            return False, "No JSON object found in output"
        data = json.loads(text[start:end])

        required = ["action", "phase", "duration"]
        missing = [f for f in required if f not in data]
        if missing:
            return False, f"Missing fields: {missing}"

        valid_phases = {"NS_GREEN", "EW_GREEN"}
        if data["phase"] not in valid_phases:
            return False, f"Invalid phase: {data['phase']}. Must be NS_GREEN or EW_GREEN"

        if not isinstance(data["duration"], (int, float)):
            return False, f"Duration must be numeric, got {type(data['duration'])}"

        return True, data
    except json.JSONDecodeError:
        return False, "Invalid JSON in output"


@dataclass
class CrewConfig:
    """Configuration for the traffic control crew."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    decision_interval: float = 5.0
    enable_coordination: bool = True
    use_cache: bool = True
    use_rules: bool = True
    enable_timing_adjustment: bool = True
    grid_base_ns: float = 30.0
    grid_base_ew: float = 30.0


class TrafficControlCrew:
    """
    CrewAI-based multi-agent orchestrator for traffic signal control.

    Architecture:
    - One Agent per intersection (fast_llm, with tools)
    - One Coordinator agent (smart_llm, with tools)
    - 3-tier pipeline: rules → cache → LLM (CrewAI)
    - Agents use tools to read state and apply decisions
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

        # 3-tier pipeline
        self.rule_engine = TimingRuleEngine()
        self.cache: Optional[DecisionCache] = (
            DecisionCache(max_size=1000, ttl_seconds=60.0)
            if self.config.use_cache else None
        )

        # Metrics
        self._total_llm_calls = 0
        self._total_rule_hits = 0
        self._total_cache_hits = 0
        self._total_decisions = 0
        self._decision_history: List[Dict] = []

        # Create CrewAI agents and tools
        self._create_agents()

    def _create_agents(self):
        """Create CrewAI agents for each intersection and coordinator."""
        from crewai import Agent

        # Create tools — intersection agents get 4, coordinator gets 3
        all_tools = _create_tools()
        self.intersection_tools = all_tools[:4]  # state, neighbors, adjust, signal
        self.coordinator_tools = all_tools[:3]  # state, neighbors, conflicts

        # Create LLM instances
        # Use fast_model for all agents to avoid rate limiting on smart_model
        model = self.config.llm.fast_model
        fast_llm = f"openai/{model}"
        smart_llm = f"openai/{model}"
        function_llm = fast_llm  # same model for tool-calling mechanics

        # If custom api_key/base_url, use CrewAI LLM object
        if self.config.llm.api_key:
            from crewai import LLM
            fast_llm = LLM(
                model=f"openai/{model}",
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.api_base,
            )
            smart_llm = LLM(
                model=f"openai/{model}",
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.api_base,
            )
            function_llm = LLM(
                model=f"openai/{self.config.llm.fast_model}",
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.api_base,
            )

        self.intersection_agents: Dict[str, Agent] = {}

        for ix_id in self.intersection_ids:
            neighbors = self.graph.get(ix_id, [])
            agent = Agent(
                role=f"Traffic Signal Controller for {ix_id}",
                goal=(
                    f"Minimize total vehicle wait time at intersection {ix_id} "
                    f"by choosing optimal signal phase and timing adjustments, "
                    f"while maintaining green wave coordination with neighbors {neighbors}."
                ),
                backstory=(
                    f"You are a senior traffic engineer with 20 years of experience "
                    f"in adaptive signal control. You specialize in real-time optimization "
                    f"using detector data and intersection coordination."
                ),
                tools=self.intersection_tools,
                llm=fast_llm,
                function_calling_llm=function_llm,
                verbose=False,
                allow_delegation=False,
                max_iter=12,
                max_execution_time=120,
            )
            self.intersection_agents[ix_id] = agent

        # Coordinator agent — different LLM, different tools, different persona
        self.coordinator_agent = Agent(
            role="Traffic Network Coordinator",
            goal=(
                "Resolve conflicts between intersection decisions and optimize "
                "city-wide traffic flow by ensuring green wave coordination "
                "along corridors and applying priority rules."
            ),
            backstory=(
                "You are a traffic management center coordinator with 15 years "
                "of experience in network-level optimization. You analyze intersection "
                "decisions holistically and resolve conflicts using priority rules."
            ),
            tools=self.coordinator_tools,
            llm=smart_llm,
            function_calling_llm=function_llm,
            verbose=False,
            allow_delegation=False,
            max_iter=15,
            max_execution_time=180,
        )

    def set_engine(self, engine) -> None:
        """Connect the simulation engine to tools. Called by CLI after creating the sim."""
        sim_state = SimulationState(engine=engine, graph=self.graph)
        set_sim_state(sim_state)

    def step(self, engine) -> List[Dict[str, Any]]:
        """
        Execute one decision cycle using 3-tier pipeline + CrewAI.

        Pipeline:
          Layer 1: Rule engine (free) — returns TimingAdjustment (±10s)
          Layer 2: Decision cache (free) — returns TrafficDecision (phase switch)
          Layer 3: CrewAI LLM agents (paid) — returns TrafficDecision (phase switch)
        """
        decisions = []
        needs_llm: List[str] = []

        # Phase 1: Apply 3-tier pipeline to each intersection
        for ix_id in self.intersection_ids:
            state = engine.get_state(ix_id)

            # Layer 1: Rule engine (returns TimingAdjustment with ±10s adjustment)
            if self.config.use_rules:
                rule_result = self.rule_engine.decide_from_state(state)
                if rule_result is not None:
                    self._total_rule_hits += 1
                    decisions.append({
                        "intersection_id": ix_id,
                        "decision": rule_result,
                        "layer": "rule",
                    })
                    # Apply timing adjustment directly
                    engine.apply_decision(ix_id, rule_result.to_dict())
                    continue

            # Layer 2: Cache (stores TrafficDecision from previous LLM calls)
            if self.cache:
                cached = self.cache.get(state)
                if cached:
                    self._total_cache_hits += 1
                    decisions.append({
                        "intersection_id": ix_id,
                        "decision": cached,
                        "layer": "cache",
                    })
                    engine.apply_decision(ix_id, cached.to_dict())
                    continue

            # Layer 3: Needs LLM
            needs_llm.append(ix_id)

        # Phase 2: If any intersection needs LLM, run CrewAI
        if needs_llm:
            llm_decisions = self._run_crewai(engine, needs_llm)
            for ix_id, decision in llm_decisions.items():
                decisions.append({
                    "intersection_id": ix_id,
                    "decision": decision,
                    "layer": "llm",
                })
                engine.apply_decision(ix_id, decision.to_dict())
                # Update cache with LLM decision
                if self.cache:
                    state = engine.get_state(ix_id)
                    self.cache.set(state, decision)

        # Record
        self._total_decisions += len(decisions)
        self._decision_history.append({
            "timestamp": time.time(),
            "decisions": decisions,
        })
        if len(self._decision_history) > 1000:
            self._decision_history = self._decision_history[-500:]

        return decisions

    def _run_crewai(
        self, engine, intersection_ids: List[str]
    ) -> Dict[str, TrafficDecision]:
        """Run CrewAI agents for intersections that need LLM decisions."""
        from crewai import Crew, Process, Task

        tasks = []
        agents = []

        for ix_id in intersection_ids:
            state = engine.get_state(ix_id)
            neighbors = self.graph.get(ix_id, [])
            neighbor_text = "\n".join(
                f"  {nid}: 排队{engine.get_state(nid).get_total_queue()}辆, "
                f"信号{engine.get_state(nid).current_phase}"
                for nid in neighbors if nid in self.intersection_ids
            )

            task = Task(
                description=(
                    f"## 任务: {ix_id} 信号灯决策\n\n"
                    f"### 当前路况\n{state.to_text()}\n\n"
                    f"### 邻居路口\n{neighbor_text}\n\n"
                    f"### 操作步骤\n"
                    f"1. 使用 Get Intersection State 工具获取 {ix_id} 最新状态\n"
                    f"2. 使用 Get Neighbor States 工具获取邻居状态\n"
                    f"3. 分析排队长度和等待时间，决定是否调整信号\n"
                    f"4. 使用 Apply Timing Adjustment 延长/缩短绿灯，"
                    f"或使用 Apply Signal Decision 切换相位\n\n"
                    f"### 约束\n"
                    f"- 调整范围: ±10秒\n"
                    f"- 安全绿灯: 15-90秒\n"
                    f"- 紧急车辆永远优先\n"
                    f"- 不要让任何方向等待超过60秒"
                ),
                expected_output=(
                    "A single JSON object with exactly these fields: "
                    "\"action\" (string: \"extend_green\" or \"switch_phase\"), "
                    "\"phase\" (string: \"NS_GREEN\" or \"EW_GREEN\"), "
                    "\"duration\" (integer: green duration in seconds, 10-60), "
                    "\"reasoning\" (string: 1-2 sentence explanation in Chinese). "
                    "Example: {\"action\": \"extend_green\", \"phase\": \"NS_GREEN\", "
                    "\"duration\": 35, \"reasoning\": \"北向排队18辆，建议延长5秒\"}"
                ),
                agent=self.intersection_agents[ix_id],
                guardrail=_validate_signal_decision,
                guardrail_max_retries=2,
            )
            tasks.append(task)
            agents.append(self.intersection_agents[ix_id])

        # Add coordination task if multiple intersections
        if len(intersection_ids) > 1 and self.config.enable_coordination:
            coord_task = Task(
                description=(
                    f"## 任务: 跨路口协调审查\n\n"
                    f"### 待审查路口\n{', '.join(intersection_ids)}\n\n"
                    f"### 操作步骤\n"
                    f"1. 使用 Get Intersection State 工具逐一检查各路口状态\n"
                    f"2. 使用 Check Conflicts 工具检测决策冲突\n"
                    f"3. 按优先级规则解决冲突:\n"
                    f"   - 紧急车辆优先\n"
                    f"   - 排队长的路口优先\n"
                    f"   - 等待时间长的路口优先\n"
                    f"4. 输出协调后的决策列表\n\n"
                    f"### 约束\n"
                    f"- 只修改有冲突的路口决策\n"
                    f"- 保持无冲突路口的原始决策不变"
                ),
                expected_output=(
                    "A JSON object with field \"decisions\" containing a list of "
                    "coordinated decisions. Each decision has: "
                    "\"intersection_id\" (string), \"phase\" (\"NS_GREEN\"/\"EW_GREEN\"), "
                    "\"duration\" (integer, 10-60), \"reasoning\" (string). "
                    "If no conflicts found, return the original decisions unchanged."
                ),
                agent=self.coordinator_agent,
                context=tasks,
            )
            tasks.append(coord_task)
            agents.append(self.coordinator_agent)

        # Create and run crew
        crew = Crew(
            agents=agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        self._total_llm_calls += 1

        # Parse results
        return self._parse_crew_result(result, intersection_ids)

    def _parse_crew_result(
        self, result, intersection_ids: List[str]
    ) -> Dict[str, TrafficDecision]:
        """Parse CrewAI output into TrafficDecision objects."""
        decisions = {}

        # Try to extract from tasks_output
        try:
            if hasattr(result, 'tasks_output') and result.tasks_output:
                for task_output in result.tasks_output:
                    raw = task_output.raw if hasattr(task_output, 'raw') else str(task_output)
                    parsed = ResponseParser.parse(raw)
                    if parsed:
                        # Match to intersection by agent role (CrewAI 1.14.x: agent is str)
                        agent = task_output.agent if hasattr(task_output, 'agent') else None
                        if agent:
                            role = agent.role if hasattr(agent, 'role') else str(agent)
                            for ix_id in intersection_ids:
                                if ix_id in role:
                                    decisions[ix_id] = parsed
                                    break
        except Exception:
            pass

        # Fallback: parse the raw result string
        if not decisions:
            raw = str(result)
            # Try to find JSON objects in the output
            for ix_id in intersection_ids:
                parsed = ResponseParser.parse(raw)
                if parsed:
                    decisions[ix_id] = parsed
                    break

        # Ensure all requested intersections have a decision
        for ix_id in intersection_ids:
            if ix_id not in decisions:
                decisions[ix_id] = ResponseParser.fallback(
                    f"LLM未能为 {ix_id} 生成决策"
                )

        return decisions

    def get_metrics(self) -> Dict[str, Any]:
        """Return crew metrics."""
        rule_hit_rate = self._total_rule_hits / max(1, self._total_decisions)
        cache_hit_rate = self._total_cache_hits / max(1, self._total_decisions)

        return {
            "total_decisions": self._total_decisions,
            "total_llm_calls": self._total_llm_calls,
            "total_rule_hits": self._total_rule_hits,
            "total_cache_hits": self._total_cache_hits,
            "rule_hit_rate": rule_hit_rate,
            "cache_hit_rate": cache_hit_rate,
            "cache_size": self.cache.size if self.cache else 0,
            "history_size": len(self._decision_history),
        }

    def get_reasoning_history(
        self, intersection_id: str, limit: int = 10
    ) -> List[Dict]:
        """Get recent reasoning history for an intersection."""
        history = []
        for record in reversed(self._decision_history):
            for d in record["decisions"]:
                if d.get("intersection_id") == intersection_id:
                    history.append(d)
                    if len(history) >= limit:
                        return history
        return history
