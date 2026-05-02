"""
Multi-Agent Coordination — Agent communication and conflict resolution.

Agents share state, detect conflicts, and coordinate through LLM reasoning.
"""

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from traffic_agent.llm.client import LLMClient, LLMConfig
from traffic_agent.llm.parser import ResponseParser, TrafficDecision
from traffic_agent.simulation.grid import GridSimulation
from traffic_agent.tools.traffic_tools import IntersectionState


@dataclass
class AgentMessage:
    """Message between intersection agents."""
    sender: str
    receiver: str
    msg_type: str          # "state" | "request" | "agree" | "alert"
    content: str
    timestamp: float
    data: Optional[Dict] = None


@dataclass
class AgentDecision:
    """Decision made by an intersection agent."""
    intersection_id: str
    decision: TrafficDecision
    timestamp: float
    messages_sent: List[AgentMessage] = field(default_factory=list)
    messages_received: List[AgentMessage] = field(default_factory=list)


class MessageBus:
    """Simple in-memory message bus for agent communication."""
    
    def __init__(self):
        self.messages: Dict[str, List[AgentMessage]] = defaultdict(list)
    
    def send(self, message: AgentMessage) -> None:
        self.messages[message.receiver].append(message)
    
    def receive(self, agent_id: str) -> List[AgentMessage]:
        msgs = self.messages.pop(agent_id, [])
        return msgs
    
    def broadcast(self, sender: str, msg_type: str, content: str, 
                  data: Optional[Dict] = None) -> None:
        """Broadcast message to all agents (except sender)."""
        # This is handled at a higher level
        pass
    
    def clear(self):
        self.messages.clear()


class ConflictDetector:
    """Detect conflicts between neighboring agents."""
    
    @staticmethod
    def detect(
        decisions: Dict[str, TrafficDecision],
        graph: Dict[str, List[str]],
    ) -> List[Tuple[str, str, str]]:
        """
        Detect conflicts between neighboring intersections.
        
        Returns list of (agent1, agent2, conflict_type) tuples.
        """
        conflicts = []
        
        for ix_id, decision in decisions.items():
            neighbors = graph.get(ix_id, [])
            
            for nid in neighbors:
                if nid in decisions:
                    neighbor_decision = decisions[nid]
                    
                    # Conflict: adjacent intersections with incompatible phases
                    if (decision.phase == "NS_GREEN" and 
                        neighbor_decision.phase == "EW_GREEN"):
                        # Check if they share a road (adjacent = share road)
                        conflicts.append((ix_id, nid, "phase_mismatch"))
                    
                    # Conflict: both want to extend green excessively
                    if (decision.duration > 45 and 
                        neighbor_decision.duration > 45):
                        conflicts.append((ix_id, nid, "excessive_green"))
        
        return conflicts


class CoordinationCrew:
    """
    Multi-agent coordination using LLM.
    
    Workflow:
    1. Each agent observes state
    2. Each agent makes independent decision
    3. Agents share decisions with neighbors
    4. Coordinator resolves conflicts
    5. Final decisions executed
    """
    
    def __init__(
        self,
        simulation: GridSimulation,
        config: Optional[LLMConfig] = None,
    ):
        self.sim = simulation
        self.llm_config = config or LLMConfig()
        self.llm_client = LLMClient(self.llm_config)
        
        self.message_bus = MessageBus()
        self.conflict_detector = ConflictDetector()
        
        self.graph = self.sim.get_graph()
        self.intersection_ids = list(self.sim.intersections.keys())
        
        # Track decisions and reasoning
        self.decision_history: List[Dict] = []
        self.total_llm_calls = 0
        self.total_conflicts = 0
    
    def step(self) -> List[Dict[str, Any]]:
        """
        Execute one coordination cycle.
        
        Returns list of final decisions.
        """
        # 1. Each agent observes and decides
        agent_decisions = {}
        for ix_id in self.intersection_ids:
            decision = self._agent_decide(ix_id)
            agent_decisions[ix_id] = decision
        
        # 2. Detect conflicts
        conflicts = self.conflict_detector.detect(
            {ix_id: d.decision for ix_id, d in agent_decisions.items()},
            self.graph,
        )
        self.total_conflicts += len(conflicts)
        
        # 3. Resolve conflicts via coordinator
        if conflicts:
            agent_decisions = self._resolve_conflicts(agent_decisions, conflicts)
        
        # 4. Execute decisions
        results = []
        for ix_id, agent_dec in agent_decisions.items():
            self.sim.apply_decision(ix_id, agent_dec.decision.to_dict())
            results.append({
                "intersection_id": ix_id,
                **agent_dec.decision.to_dict(),
                "messages_sent": len(agent_dec.messages_sent),
                "messages_received": len(agent_dec.messages_received),
            })
        
        # 5. Record
        self.decision_history.append({
            "timestamp": time.time(),
            "sim_time": self.sim.time,
            "decisions": results,
            "conflicts": len(conflicts),
        })
        
        return results
    
    def _agent_decide(self, ix_id: str) -> AgentDecision:
        """Get decision from a single agent via LLM."""
        state = self.sim.get_state(ix_id)
        neighbors = self.graph.get(ix_id, [])
        
        # Build neighbor info
        neighbor_text = ""
        for nid in neighbors:
            n_state = self.sim.get_state(nid)
            neighbor_text += f"  {nid}: 排队{self._total_queue(n_state)}辆, {n_state.current_phase}\n"
        
        # Build prompt
        system_prompt = f"""你是{ix_id}路口的交通信号灯AI控制专家。
当前路况：
{state.to_text()}

邻居路口状态：
{neighbor_text}

请做出信号灯决策（JSON格式）：
{{"action": "extend_green/switch_phase", "phase": "NS_GREEN/EW_GREEN", "duration": 秒数, "reasoning": "理由"}}"""
        
        response = self.llm_client.chat(
            system_prompt=system_prompt,
            user_message="请做出决策。",
            temperature=0.3,
        )
        self.total_llm_calls += 1
        
        decision = ResponseParser.parse(response.content)
        if decision is None:
            decision = ResponseParser.fallback("LLM响应解析失败")
        
        return AgentDecision(
            intersection_id=ix_id,
            decision=decision,
            timestamp=time.time(),
        )
    
    def _resolve_conflicts(
        self,
        decisions: Dict[str, AgentDecision],
        conflicts: List[Tuple[str, str, str]],
    ) -> Dict[str, AgentDecision]:
        """Resolve conflicts using coordinator LLM."""
        
        # Build conflict summary
        conflict_text = "\n".join(
            f"  - {c[0]} 和 {c[1]}: {c[2]}"
            for c in conflicts
        )
        
        decisions_text = "\n".join(
            f"  {ix_id}: {d.decision.phase} {d.decision.duration}s"
            for ix_id, d in decisions.items()
        )
        
        system_prompt = """你是交通协调主管。请协调解决路口间的冲突。

协调规则：
1. 紧急车辆优先
2. 排队长的路口优先
3. 相邻路口尽量配合形成绿波带"""
        
        user_message = f"""路口决策：
{decisions_text}

冲突：
{conflict_text}

请输出协调后的决策（JSON数组格式）：
[{{"intersection_id": "ix_X_X", "phase": "NS_GREEN/EW_GREEN", "duration": 秒数, "reasoning": "协调理由"}}]"""
        
        response = self.llm_client.chat(
            system_prompt=system_prompt,
            user_message=user_message,
            model=self.llm_config.smart_model,
            temperature=0.2,
        )
        self.total_llm_calls += 1
        
        # Parse coordinator response
        try:
            # Extract JSON array from response
            content = response.content
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                coordinated = json.loads(content[start:end])
                
                for d in coordinated:
                    ix_id = d.get("intersection_id")
                    if ix_id in decisions:
                        new_decision = ResponseParser.parse(json.dumps(d))
                        if new_decision:
                            decisions[ix_id].decision = new_decision
        except (json.JSONDecodeError, ValueError):
            pass  # Keep original decisions on parse failure
        
        return decisions
    
    def _total_queue(self, state: IntersectionState) -> int:
        return (state.queue_north + state.queue_south + 
                state.queue_east + state.queue_west)
    
    def get_metrics(self) -> Dict[str, Any]:
        return {
            "total_llm_calls": self.total_llm_calls,
            "total_conflicts": self.total_conflicts,
            "history_size": len(self.decision_history),
        }
    
    def get_reasoning_history(self, ix_id: str, limit: int = 5) -> List[Dict]:
        """Get recent reasoning for an intersection."""
        history = []
        for record in reversed(self.decision_history):
            for d in record["decisions"]:
                if d.get("intersection_id") == ix_id:
                    history.append(d)
                    if len(history) >= limit:
                        return history
        return history
