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

## ⚠️ 混行交通意识
本路口是**混行交通**环境，交通参与者包括：
- 🚗 **汽车**：正常速度50km/h，占主要流量
- 🚌 **公交车**：体积大，加速慢，停站频繁
- 🛵 **电动自行车**：速度22-30km/h，可能穿插机动车道，需注意非机动车道管理
- 🚲 **自行车**：速度15km/h，可能闯红灯
- 🚶 **行人**：速度5km/h，可能闯红灯横穿马路
- 🚑 **紧急车辆**：永远优先，可闯红灯

**混行决策要点：**
1. 电动自行车占比高时 → 考虑延长绿灯清空非机动车
2. 行人较多时 → 确保行人过街相位充足，避免过长等待导致闯红灯
3. 公交车多时 → 适当延长绿灯，减少公交频繁启停
4. 自行车和行人可能不遵守信号 → 绿灯尾部预留安全间隔

## 决策原则
1. **安全第一**: 确保行人和车辆安全，特别是弱势交通参与者
2. **效率优先**: 最小化总等待时间（考虑不同车型的等待成本不同）
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
    "reasoning": "<你的决策推理过程, 中文, 须说明混行交通考量>",
    "confidence": <0.0-1.0>,
    "coordination_message": "<给邻居路口的消息, 可选>"
}}

注意：只输出JSON，不要有其他文字。reasoning 中必须体现你对混行交通的分析。"""

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
    """Current state of an intersection — with mixed traffic breakdown."""
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

    # Mixed traffic: {vehicle_type: {total: int, waiting: int}}
    vehicle_type_breakdown: Optional[Dict[str, Dict[str, int]]] = None
    
    def to_text(self) -> str:
        """Format state as human-readable text for LLM — including mixed traffic info."""
        # Build vehicle type summary
        type_lines = ""
        if self.vehicle_type_breakdown:
            type_map = {
                "car": "汽车", "bus": "公交车", "e_bike": "电动自行车",
                "bicycle": "自行车", "pedestrian": "行人", "emergency": "紧急车辆",
            }
            parts = []
            for vtype, counts in self.vehicle_type_breakdown.items():
                zh = type_map.get(vtype, vtype)
                total = counts.get("total", 0)
                waiting = counts.get("waiting", 0)
                if total > 0:
                    parts.append(f"{zh}{total}辆(等{waiting})")
            if parts:
                type_lines = f"\n交通构成: {', '.join(parts)}"

        # Mixed traffic advisory
        advisory = ""
        if self.vehicle_type_breakdown:
            eb = self.vehicle_type_breakdown.get("e_bike", {}).get("total", 0)
            ped = self.vehicle_type_breakdown.get("pedestrian", {}).get("total", 0)
            total = self.get_total_queue()
            if total > 0:
                eb_pct = eb / total
                ped_pct = ped / total
                if eb_pct > 0.3:
                    advisory += "\n⚠️ 电动自行车占比高，注意非机动车道管理和穿插行为"
                if ped_pct > 0.15:
                    advisory += "\n⚠️ 行人较多，注意行人过街安全和信号配时"

        return f"""路口: {self.intersection_id}
时间: {self.timestamp:.1f}s

各方向排队:
- 北: {self.queue_north}辆, 等待{self.wait_north:.0f}s
- 南: {self.queue_south}辆, 等待{self.wait_south:.0f}s
- 东: {self.queue_east}辆, 等待{self.wait_east:.0f}s
- 西: {self.queue_west}辆, 等待{self.wait_west:.0f}s
{type_lines}
当前信号: {self.current_phase}, 已持续{self.phase_duration:.0f}s
紧急车辆: {'有 — 需立即给予优先通行' if self.emergency else '无'}{advisory}
"""
    
    def get_max_queue(self) -> int:
        return max(self.queue_north, self.queue_south, self.queue_east, self.queue_west)
    
    def get_total_queue(self) -> int:
        return self.queue_north + self.queue_south + self.queue_east + self.queue_west

    def get_total_by_type(self, vehicle_type: str) -> int:
        """Get total count of a specific vehicle type."""
        if self.vehicle_type_breakdown and vehicle_type in self.vehicle_type_breakdown:
            return self.vehicle_type_breakdown[vehicle_type].get("total", 0)
        return 0

    def get_mixed_traffic_summary(self) -> str:
        """Return a one-line summary of mixed traffic composition."""
        if not self.vehicle_type_breakdown:
            return "无混行数据"
        total = self.get_total_queue()
        if total == 0:
            return "无车辆"
        parts = []
        type_map = {
            "car": "汽车", "bus": "公交", "e_bike": "电自",
            "bicycle": "单车", "pedestrian": "行人", "emergency": "急救",
        }
        for vtype, counts in self.vehicle_type_breakdown.items():
            c = counts.get("total", 0)
            if c > 0:
                pct = c / total * 100
                zh = type_map.get(vtype, vtype)
                parts.append(f"{zh}{c}({pct:.0f}%)")
        return " ".join(parts) if parts else "无车辆"


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
