"""
Agent Tools — Tools for CrewAI agents to interact with the simulation.

Each tool represents a capability that an agent can use:
- Observe traffic state
- Send messages to neighbors
- Check for emergencies
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np


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
    
    # Special conditions
    emergency: bool = False
    emergency_approach: Optional[int] = None
    
    def to_text(self) -> str:
        """Format state as human-readable text for LLM."""
        return f"""路口: {self.intersection_id}
时间: {self.timestamp:.1f}s

各方向排队:
- 北: {self.queue_north}辆, 等待{self.wait_north:.0f}s
- 南: {self.queue_south}辆, 等待{self.wait_south:.0f}s
- 东: {self.queue_east}辆, 等待{self.wait_east:.0f}s
- 西: {self.queue_west}辆, 等待{self.wait_west:.0f}s

当前信号: {self.current_phase}, 已持续{self.phase_duration:.0f}s
紧急车辆: {'有' if self.emergency else '无'}
"""
    
    def get_max_queue(self) -> int:
        return max(self.queue_north, self.queue_south, self.queue_east, self.queue_west)
    
    def get_total_queue(self) -> int:
        return self.queue_north + self.queue_south + self.queue_east + self.queue_west


class TrafficObservationTool:
    """
    Tool for agents to observe traffic state.
    
    In CrewAI, this would be a BaseTool subclass.
    Here we implement it standalone for flexibility.
    """
    
    name: str = "observe_traffic"
    description: str = "获取当前路口的实时交通数据"
    
    def __init__(self, simulation_engine=None):
        self.engine = simulation_engine
    
    def run(self, intersection_id: str) -> str:
        """Observe traffic state at an intersection."""
        if self.engine is None:
            return "仿真引擎未初始化"
        
        state = self.engine.get_state(intersection_id)
        return state.to_text()


class NeighborStateTool:
    """Tool for agents to check neighbor intersection states."""
    
    name: str = "check_neighbors"
    description: str = "获取邻居路口的状态"
    
    def __init__(self, simulation_engine=None):
        self.engine = simulation_engine
    
    def run(self, intersection_id: str, neighbor_ids: list) -> str:
        """Get states of neighbor intersections."""
        if self.engine is None:
            return "仿真引擎未初始化"
        
        lines = [f"邻居路口状态 ({len(neighbor_ids)} 个):"]
        for nid in neighbor_ids:
            state = self.engine.get_state(nid)
            lines.append(f"  {nid}: 排队{state.get_total_queue()}辆, "
                        f"信号{state.current_phase}")
        
        return "\n".join(lines)


class CoordinationMessageTool:
    """Tool for agents to send coordination messages."""
    
    name: str = "send_message"
    description: str = "向邻居路口发送协调消息"
    
    def __init__(self):
        self.messages: Dict[str, list] = {}  # recipient -> [messages]
    
    def run(self, sender: str, recipient: str, message: str) -> str:
        """Send a coordination message."""
        if recipient not in self.messages:
            self.messages[recipient] = []
        self.messages[recipient].append({
            "from": sender,
            "message": message,
        })
        return f"消息已发送给 {recipient}"
    
    def get_messages(self, recipient: str) -> list:
        """Get all messages for an agent."""
        return self.messages.pop(recipient, [])
    
    def clear(self):
        self.messages.clear()


class EmergencyAlertTool:
    """Tool for emergency vehicle alerts."""
    
    name: str = "alert_emergency"
    description: str = "广播紧急车辆警报"
    
    def __init__(self):
        self.alerts: list = []
    
    def run(self, intersection_id: str, approach: int, 
            vehicle_type: str = "救护车") -> str:
        """Broadcast emergency alert."""
        self.alerts.append({
            "intersection": intersection_id,
            "approach": approach,
            "type": vehicle_type,
        })
        return f"紧急警报已广播: {vehicle_type}从{intersection_id}的approach {approach}接近"
    
    def get_alerts(self) -> list:
        alerts = self.alerts.copy()
        self.alerts.clear()
        return alerts
