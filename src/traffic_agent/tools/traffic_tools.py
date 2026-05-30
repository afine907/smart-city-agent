"""
Traffic Tools — Shared data structures, prompt templates, and CrewAI tools.

IntersectionState is used across the codebase for traffic state representation.
Prompts are used by the multi-agent coordination system.
Tools are used by CrewAI agents to interact with the simulation.
"""

from __future__ import annotations


from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ─── Prompt Templates ──────────────────────────────────────────

TRAFFIC_EXPERT_PROMPT = """你是一个城市交通信号灯AI控制专家，负责控制 {intersection_id} 路口。

## 角色
你有20年交通工程经验。你理解信号配时、高峰潮汐、紧急车辆优先、行人安全。
你基于实时数据做决策，并与相邻路口协调以创建绿波带。

## 决策原则
1. **安全第一**: 确保行人和车辆安全
2. **效率优先**: 最小化总等待时间
3. **公平性**: 不让任何一个方向等待过久
4. **协调性**: 与邻居路口配合
5. **应急响应**: 紧急车辆永远优先

## 信号灯阶段
- NS_GREEN: 南北方向绿灯 (10-60秒)
- NS_YELLOW: 南北方向黄灯 (3秒)
- EW_GREEN: 东西方向绿灯 (10-60秒)
- EW_YELLOW: 东西方向黄灯 (3秒)

## 输出格式
你必须输出严格的JSON格式：
{{
    "action": "extend_green" | "switch_phase" | "emergency",
    "phase": "NS_GREEN" | "EW_GREEN",
    "duration": <秒数, 10-60>,
    "reasoning": "<你的决策推理过程, 中文>",
    "confidence": <0.0-1.0>,
    "coordination_message": "<给邻居路口的消息, 可选>"
}}

注意：只输出JSON，不要有其他文字。"""

COORDINATOR_PROMPT = """你是城市交通协调主管，负责协调多个路口Agent的决策。

## 角色
你有15年交通管理中心经验。你负责：
1. 收集各路口Agent的决策
2. 检查冲突（如相邻路口同时要求绿灯）
3. 根据优先级规则协调
4. 输出最终方案

## 协调规则
1. **紧急车辆优先**: 有emergency请求的路口优先
2. **排队长度**: 排队长的路口优先获得绿灯
3. **公平轮转**: 如果条件相近，轮流优先
4. **绿波协调**: 相邻路口尽量配合，形成绿波带

## 输出格式
输出协调后的JSON决策列表：
{{
    "decisions": [
        {{
            "intersection_id": "<路口ID>",
            "action": "extend_green" | "switch_phase",
            "phase": "NS_GREEN" | "EW_GREEN",
            "duration": <秒数>,
            "reasoning": "<协调理由>"
        }}
    ],
    "conflicts_resolved": <解决的冲突数>,
    "coordination_notes": "<协调说明>"
}}
"""


# ─── Data Structures ──────────────────────────────────────────

@dataclass
class IntersectionState:
    """Current state of an intersection."""
    intersection_id: str
    timestamp: float

    # Queue lengths per approach (N, E, S, W)
    queue_north: int = 0
    queue_south: int = 0
    queue_east: int = 0
    queue_west: int = 0

    # Wait times per approach
    wait_north: float = 0.0
    wait_south: float = 0.0
    wait_east: float = 0.0
    wait_west: float = 0.0

    # Signal state
    current_phase: str = "NS_GREEN"
    phase_duration: float = 0.0
    base_duration: float = 0.0  # baseline green duration before adjustment

    # Special conditions
    emergency: bool = False
    emergency_approach: Optional[int] = None

    def to_text(self) -> str:
        """Format state as human-readable text for LLM."""
        duration_info = f"已持续{self.phase_duration:.0f}s"
        if self.base_duration > 0 and self.base_duration != self.phase_duration:
            duration_info += f" (基线{self.base_duration:.0f}s)"

        return f"""路口: {self.intersection_id}
时间: {self.timestamp:.1f}s

各方向排队:
- 北: {self.queue_north}辆, 等待{self.wait_north:.0f}s
- 南: {self.queue_south}辆, 等待{self.wait_south:.0f}s
- 东: {self.queue_east}辆, 等待{self.wait_east:.0f}s
- 西: {self.queue_west}辆, 等待{self.wait_west:.0f}s

当前信号: {self.current_phase}, {duration_info}
紧急车辆: {'有' if self.emergency else '无'}
"""

    def get_max_queue(self) -> int:
        return max(self.queue_north, self.queue_south, self.queue_east, self.queue_west)

    def get_total_queue(self) -> int:
        return self.queue_north + self.queue_south + self.queue_east + self.queue_west


# ─── Shared State Container ────────────────────────────────────

class SimulationState:
    """Shared state between all CrewAI tools and the simulation."""

    def __init__(self, engine=None, graph: Optional[Dict[str, List[str]]] = None):
        self.engine = engine
        self.graph = graph or {}


# ─── CrewAI Tools ──────────────────────────────────────────────

# Global state reference for tools (set by TrafficControlCrew.set_engine)
_sim_state: Optional[SimulationState] = None


def set_sim_state(state: SimulationState) -> None:
    global _sim_state
    _sim_state = state


def _get_state() -> SimulationState:
    if _sim_state is None:
        raise RuntimeError("SimulationState not initialized. Call set_sim_state() first.")
    return _sim_state


def _create_tools():
    """Create all CrewAI tools. Returns list of tool instances."""
    from crewai.tools import tool

    @tool("Get Intersection State")
    def get_intersection_state(intersection_id: str) -> str:
        """Get the real-time traffic state for a specific intersection. Returns queue lengths, wait times, current signal phase, and emergency status. Use this to understand the current conditions before making a decision."""
        state = _get_state()
        ix_state = state.engine.get_state(intersection_id)
        return ix_state.to_text()

    @tool("Get Neighbor States")
    def get_neighbor_states(intersection_id: str) -> str:
        """Get a summary of queue lengths and signal phases for all neighboring intersections. Use this to coordinate with adjacent intersections and avoid conflicts."""
        state = _get_state()
        neighbors = state.graph.get(intersection_id, [])
        if not neighbors:
            return f"{intersection_id} 没有邻居路口。"

        lines = [f"{intersection_id} 的邻居路口:"]
        for nid in neighbors:
            try:
                ns = state.engine.get_state(nid)
                lines.append(
                    f"  {nid}: 排队{ns.get_total_queue()}辆, "
                    f"信号{ns.current_phase}, "
                    f"北{ns.queue_north}/南{ns.queue_south}/东{ns.queue_east}/西{ns.queue_west}"
                )
            except (KeyError, Exception):
                lines.append(f"  {nid}: 无数据")
        return "\n".join(lines)

    @tool("Apply Signal Decision")
    def apply_signal_decision(intersection_id: str, phase: str, reasoning: str) -> str:
        """Apply a signal phase decision to an intersection. Use phase='NS_GREEN' for north-south green or phase='EW_GREEN' for east-west green. Always provide your reasoning."""
        state = _get_state()
        valid_phases = {"NS_GREEN", "EW_GREEN"}
        if phase not in valid_phases:
            return f"错误: 无效相位 '{phase}'。有效值: {valid_phases}"

        state.engine.apply_decision(intersection_id, {"phase": phase})
        return f"已将 {intersection_id} 信号切换为 {phase}。理由: {reasoning}"

    @tool("Apply Timing Adjustment")
    def apply_timing_adjustment(intersection_id: str, adjustment: int, reasoning: str) -> str:
        """Apply a timing adjustment of -10 to +10 seconds to the current green phase. Positive values extend green, negative values shorten it. The adjustment is clamped to [-10, +10] and the resulting green duration is clamped to [15, 90] seconds."""
        state = _get_state()
        adjustment = max(-10, min(10, int(adjustment)))
        state.engine.apply_decision(intersection_id, {"adjustment": adjustment})
        return f"已对 {intersection_id} 应用 {adjustment:+d}s 调整。理由: {reasoning}"

    @tool("Check Conflicts")
    def check_conflicts(decisions_json: str) -> str:
        """Check for conflicts between intersection decisions. Pass a JSON string of decisions to analyze. Returns any detected conflicts (phase mismatches or excessive green durations)."""
        import json
        from traffic_agent.crew.coordination import ConflictDetector
        from traffic_agent.llm.parser import TrafficDecision

        state = _get_state()
        try:
            raw = json.loads(decisions_json)
        except json.JSONDecodeError:
            return "错误: 无法解析决策JSON"

        decisions = {}
        for d in raw if isinstance(raw, list) else [raw]:
            ix_id = d.get("intersection_id", "")
            decisions[ix_id] = TrafficDecision(
                action=d.get("action", "extend_green"),
                phase=d.get("phase", "NS_GREEN"),
                duration=d.get("duration", 30),
                reasoning=d.get("reasoning", ""),
                confidence=d.get("confidence", 0.5),
            )

        conflicts = ConflictDetector.detect(decisions, state.graph)
        if not conflicts:
            return "没有检测到冲突。"
        lines = [f"检测到 {len(conflicts)} 个冲突:"]
        for a, b, ctype in conflicts:
            lines.append(f"  - {a} 和 {b}: {ctype}")
        return "\n".join(lines)

    @tool("Get Traffic Trend")
    def get_traffic_trend(intersection_id: str, direction: str) -> str:
        """Get the recent traffic trend for a specific direction at an intersection. Direction should be 'north', 'south', 'east', or 'west'. Returns whether traffic is increasing, decreasing, or stable."""
        state = _get_state()
        valid_dirs = {"north", "south", "east", "west"}
        if direction not in valid_dirs:
            return f"错误: 无效方向 '{direction}'。有效值: {valid_dirs}"

        ix_state = state.engine.get_state(intersection_id)
        queue = getattr(ix_state, f"queue_{direction}", 0)
        wait = getattr(ix_state, f"wait_{direction}", 0.0)

        # Simple trend based on current state
        if queue > 10:
            trend = "高负载"
        elif queue > 5:
            trend = "中等负载"
        else:
            trend = "低负载"

        return (
            f"{intersection_id} {direction}方向: "
            f"排队{queue}辆, 等待{wait:.0f}s, 趋势={trend}"
        )

    return [
        get_intersection_state,
        get_neighbor_states,
        apply_signal_decision,
        apply_timing_adjustment,
        check_conflicts,
        get_traffic_trend,
    ]
