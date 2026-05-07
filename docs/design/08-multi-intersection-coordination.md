# 第8章 多路口协调设计

> **核心问题：每个路口的 Agent 不是孤岛，它们需要对话、协商、达成共识。**

## 问题本质

单路口控制是局部优化——只关心自己路口的等待时间。
多路口协调是全局优化——相邻路口必须配合，否则一个路口的优化可能导致邻居更堵。

**真实案例**：A 路口把南北绿灯延长到 60 秒，大量车流涌向 B 路口。
如果 B 路口不知道 A 刚刚放了 60 秒的绿灯，它可能正在放东西方向绿灯，
导致 A 放过来的车全部堵在 B 路口。

这就是为什么需要协调。

---

## 1. 协调架构

### 1.1 三种架构选择

| 架构 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| **集中式** | 中央控制器统一决策所有路口 | 全局最优 | 单点故障、扩展性差 |
| **分布式** | 每个路口独立决策，无通信 | 简单、鲁棒 | 无法协调，局部最优 |
| **混合式** | 本地决策 + 协调层仲裁 | 平衡全局和局部 | 复杂度中等 |

**选择：混合式架构。**

理由：
- 每个路口 Agent 有本地决策能力（鲁棒性）
- 协调层检测冲突并促成共识（全局优化）
- 协调层失败时本地仍能工作（降级能力）

### 1.2 架构图

```
┌──────────────────────────────────────────────────────────┐
│                    协调层 (Coordinator)                    │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ 冲突检测器    │  │ 绿波计算器    │  │ LLM 协调器   │  │
│  │ ConflictDetect│  │ GreenWaveCalc │  │ LLM Arbitrate│  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                 │           │
│         └─────────────────┼─────────────────┘           │
│                           │                             │
└───────────────────────────┼─────────────────────────────┘
                            │ 协调指令
            ┌───────────────┼───────────────┐
            │               │               │
     ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
     │  Agent A    │ │  Agent B    │ │  Agent C    │
     │  (本地决策)  │ │  (本地决策)  │ │  (本地决策)  │
     │  + 协调约束  │ │  + 协调约束  │ │  + 协调约束  │
     └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
            │               │               │
     ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
     │   路口 A    │ │   路口 B    │ │   路口 C    │
     └─────────────┘ └─────────────┘ └─────────────┘
```

### 1.3 协调时机

协调不是每秒都做，而是在特定时机触发：

| 时机 | 触发条件 | 协调内容 |
|------|---------|---------|
| **相位切换时** | 某路口即将切换相位 | 通知下游路口准备接收车流 |
| **冲突检测时** | 相邻路口需求冲突 | 协商谁先谁后 |
| **绿波计算时** | 周期性（每 5 分钟） | 计算相邻路口相位差 |
| **异常触发时** | 事故/紧急车辆 | 多路口联合响应 |

---

## 2. Agent 间通信协议

### 2.1 消息类型

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional

class MessageType(str, Enum):
    """Agent 间消息类型。"""
    
    # 状态共享
    STATE_BROADCAST = "state_broadcast"      # 广播本路口状态摘要
    STATE_REQUEST = "state_request"          # 请求邻居状态
    
    # 协调
    PHASE_INTENT = "phase_intent"            # "我打算切换到 XX 相位"
    PHASE_NEGOTIATE = "phase_negotiate"      # "我请求你推迟切换"
    PHASE_AGREE = "phase_agree"             # "同意你的请求"
    PHASE_DISAGREE = "phase_disagree"       # "不同意，原因：..."
    
    # 绿波
    GREEN_WAVE_PROPOSAL = "green_wave_proposal"   # "建议相位差 XX 秒"
    GREEN_WAVE_ACCEPT = "green_wave_accept"
    
    # 紧急
    EMERGENCY_ALERT = "emergency_alert"     # "有紧急车辆，需要优先"
    EMERGENCY_ACK = "emergency_ack"         # "收到，已让行"
    
    # 事件
    INCIDENT通报 = "incident_report"        # "我这边有事故/施工"


@dataclass
class AgentMessage:
    """Agent 间通信消息。"""
    sender: str                    # 发送者 intersection_id
    receiver: str                  # 接收者 intersection_id 或 "broadcast"
    msg_type: MessageType
    content: dict                  # 结构化数据
    timestamp: float
    round_id: int                  # 协调轮次
    priority: int = 0              # 优先级（紧急消息高优先级）
```

### 2.2 状态共享协议

每个路口 Agent 周期性地向邻居广播**状态摘要**（不是全量数据，减少通信开销）：

```python
@dataclass
class StateSummary:
    """路口状态摘要——用于 Agent 间共享。"""
    intersection_id: str
    timestamp: float
    
    # 各方向排队长度（只共享排队，不共享每辆车）
    queue: dict[str, int]     # {"north": 12, "south": 8, "east": 3, "west": 5}
    
    # 当前信号状态
    current_phase: str        # "NS_GREEN"
    phase_elapsed: float      # 已持续秒数
    phase_remaining: float    # 剩余秒数
    
    # 关键特征
    total_queue: int          # 总排队
    max_direction: str        # 排队最多的方向
    has_emergency: bool       # 是否有紧急车辆
    
    # 混行信息
    ebike_ratio: float        # 电动车占比
    pedestrian_count: int     # 行人数
    
    # 意图（即将做什么）
    planned_action: Optional[str] = None   # "switch_to EW_GREEN in 5s"
    planned_phase: Optional[str] = None
    planned_time: Optional[float] = None
```

**广播频率**：每 10 秒广播一次（与 LLM 决策周期对齐）。

### 2.3 冲突检测

协调层的冲突检测器持续监控相邻路口的状态：

```python
@dataclass
class Conflict:
    """检测到的冲突。"""
    conflict_id: str
    conflict_type: str    # "simultaneous_green" | "excessive_green" | "flow_mismatch"
    intersections: list[str]  # 涉及的路口
    severity: float       # 0.0-1.0
    description: str
    suggested_resolution: str


class ConflictDetector:
    """冲突检测器。"""
    
    def detect(self, states: dict[str, StateSummary], graph: dict) -> list[Conflict]:
        conflicts = []
        
        for ix_id, neighbors in graph.items():
            state = states.get(ix_id)
            if not state:
                continue
            
            for neighbor_id in neighbors:
                neighbor = states.get(neighbor_id)
                if not neighbor:
                    continue
                
                # 检测 1：同时绿灯冲突
                # 如果两个相邻路口同时给垂直方向绿灯，
                # 车流会在交叉区域冲突
                c1 = self._check_simultaneous_green(state, neighbor)
                if c1:
                    conflicts.append(c1)
                
                # 检测 2：单方向过度绿灯
                # 如果某路口给了某方向超长绿灯，下游路口可能来不及消化
                c2 = self._check_excessive_green(state, neighbor)
                if c2:
                    conflicts.append(c2)
                
                # 检测 3：流量不匹配
                # A 路口放了大量南向车，但 B 路口南向正在红灯
                c3 = self._check_flow_mismatch(state, neighbor)
                if c3:
                    conflicts.append(c3)
        
        return conflicts
    
    def _check_simultaneous_green(self, state_a, state_b) -> Optional[Conflict]:
        """检测同时绿灯冲突。"""
        # 如果 A 和 B 相邻，且分别给垂直方向绿灯，
        # 且中间有车流交汇，就是冲突
        # （简化版：只要方向垂直 + 都是绿灯 + 排队都不为空）
        if state_a.has_emergency or state_b.has_emergency:
            return None  # 紧急情况不冲突检测
        
        # 具体检测逻辑取决于路口拓扑
        return None
    
    def _check_excessive_green(self, state, neighbor) -> Optional[Conflict]:
        """检测单方向过度绿灯。"""
        if state.phase_elapsed > 50:  # 绿灯超过 50 秒
            return Conflict(
                conflict_id=f"excessive_{state.intersection_id}",
                conflict_type="excessive_green",
                intersections=[state.intersection_id],
                severity=0.6,
                description=f"{state.intersection_id} {state.current_phase} 已持续 {state.phase_elapsed:.0f}s",
                suggested_resolution="建议切换相位或缩短剩余时间",
            )
        return None
    
    def _check_flow_mismatch(self, state, neighbor) -> Optional[Conflict]:
        """检测流量不匹配。"""
        # 如果 A 路口南向排队多（正在放南向绿灯），
        # 而 B 路口（A 的南边）南向正在红灯，
        # 那 A 放过来的车会在 B 路口排队
        if (state.queue.get("south", 0) > 10 and
            neighbor.current_phase in ["EW_GREEN", "EW_YELLOW"]):
            return Conflict(
                conflict_id=f"mismatch_{state.intersection_id}_{neighbor.intersection_id}",
                conflict_type="flow_mismatch",
                intersections=[state.intersection_id, neighbor.intersection_id],
                severity=0.7,
                description=(
                    f"{state.intersection_id} 南向排队 {state.queue['south']} 辆，"
                    f"但 {neighbor.intersection_id} 正在 {neighbor.current_phase}，"
                    f"南向车流将在 {neighbor.intersection_id} 排队"
                ),
                suggested_resolution=f"建议 {neighbor.intersection_id} 切换到 NS_GREEN",
            )
        return None
```

---

## 3. 绿波带设计

### 3.1 什么是绿波带

绿波带（Green Wave）：让车辆以设计速度行驶时，能连续通过多个路口的绿灯。

```
路口 A        路口 B        路口 C
  🟢 ──── 30s ──── 🟢 ──── 30s ──── 🟢
  ↑               ↑               ↑
  t=0            t=30           t=60
```

如果 A 在 t=0 给绿灯，B 应该在 t=30 给绿灯（假设车间距 30 秒），
这样从 A 出发的车到达 B 时刚好是绿灯。

### 3.2 相位差计算

```python
@dataclass
class GreenWavePlan:
    """绿波方案。"""
    corridor: str              # 走廊名称（如 "南北主干道"）
    intersections: list[str]   # 沿线路口列表（从北到南）
    direction: str             # "north_to_south" 或 "south_to_north"
    design_speed: float        # 设计速度 (m/s)
    cycle_time: float          # 信号周期 (s)
    offsets: dict[str, float]  # 各路口的相位偏移 (s)


def calculate_green_wave(
    intersections: list[str],
    distances: dict[tuple[str, str], float],  # 路口间距离 (m)
    design_speed: float = 11.11,  # 40 km/h，适合混行交通
    cycle_time: float = 90.0,
) -> GreenWavePlan:
    """
    计算绿波方案。
    
    原理：offset = distance / design_speed
    第一个路口 offset=0，后续路口的 offset 根据距离累加。
    """
    offsets = {intersections[0]: 0.0}
    
    for i in range(1, len(intersections)):
        prev = intersections[i - 1]
        curr = intersections[i]
        dist = distances.get((prev, curr), 200.0)  # 默认 200m
        travel_time = dist / design_speed
        offsets[curr] = (offsets[prev] + travel_time) % cycle_time
    
    return GreenWavePlan(
        corridor=f"{intersections[0]}→{intersections[-1]}",
        intersections=intersections,
        direction="north_to_south",
        design_speed=design_speed,
        cycle_time=cycle_time,
        offsets=offsets,
    )
```

### 3.3 绿波与 LLM 的结合

**关键设计**：绿波方案由协调层计算，LLM Agent 在绿波约束内做微调。

```python
class CoordinatedAgent:
    """带绿波约束的路口 Agent。"""
    
    def __init__(self, intersection_id: str, llm_client, green_wave: GreenWavePlan):
        self.intersection_id = intersection_id
        self.llm = llm_client
        self.green_wave = green_wave
        self.offset = green_wave.offsets.get(intersection_id, 0.0)
    
    def decide(self, state: dict, time: float) -> dict:
        # 计算当前周期内的时间点
        cycle_position = time % self.green_wave.cycle_time
        
        # 判断是否在绿波窗口内
        in_green_wave = abs(cycle_position - self.offset) < 5.0  # 5 秒容差
        
        # 构建带绿波信息的 prompt
        prompt = self._build_prompt(state, in_green_wave, cycle_position)
        
        # LLM 决策
        decision = self.llm.decide(prompt)
        
        # 绿波约束：如果在绿波窗口内，不允许切换相位
        if in_green_wave and decision["action"] == "switch_phase":
            decision["action"] = "extend_green"
            decision["reasoning"] += " [绿波约束：保持当前相位]"
        
        return decision
```

---

## 4. 协调决策流程

### 4.1 完整的协调流程

```
每个决策周期（10 秒）:

Step 1: 状态收集
  各 Agent 读取本地状态 → 广播 StateSummary 给邻居

Step 2: 独立决策
  各 Agent 基于本地状态 + 邻居状态，独立做出初步决策

Step 3: 冲突检测
  协调层收集所有 Agent 的初步决策
  检测是否存在冲突

Step 4: 协调（如果存在冲突）
  有冲突的 Agent 进入协商：
  - 发送 PHASE_NEGOTIATE 消息
  - 对方评估后回复 AGREE 或 DISAGREE
  - 如果 DISAGREE，协调层 LLM 仲裁

Step 5: 执行
  各 Agent 执行最终决策

Step 6: 记录
  记录协调过程、冲突解决、决策理由
```

### 4.2 协调层 LLM 仲裁

当两个 Agent 的本地决策冲突时，协调层用 LLM 仲裁：

```python
COORDINATION_PROMPT = """你是城市交通协调主管，负责仲裁多个路口 Agent 的决策冲突。

## 仲裁原则
1. **紧急优先**: 有紧急车辆的路口决策优先
2. **排队长度**: 排队长的方向优先获得绿灯
3. **绿波保持**: 正在绿波走廊中的路口优先保持相位
4. **公平性**: 不让任何方向等待超过 60 秒

## 输入
冲突路口的当前状态和各自决策。

## 输出
仲裁后的最终决策（JSON 格式）。
"""

def arbitrate(
    conflict: Conflict,
    agent_decisions: dict[str, dict],
    states: dict[str, StateSummary],
) -> dict[str, dict]:
    """LLM 仲裁冲突。"""
    # 构建仲裁 prompt
    input_data = {
        "conflict": {
            "type": conflict.conflict_type,
            "intersections": conflict.intersections,
            "severity": conflict.severity,
        },
        "decisions": {},
    }
    
    for ix_id in conflict.intersections:
        input_data["decisions"][ix_id] = {
            "state": states[ix_id].__dict__,
            "proposed_decision": agent_decisions[ix_id],
        }
    
    # 调用 LLM 仲裁
    response = llm_client.chat(
        system_prompt=COORDINATION_PROMPT,
        user_message=json.dumps(input_data, ensure_ascii=False),
    )
    
    return parse_arbitration_result(response)
```

---

## 5. 降级策略

协调层失败时，系统应该降级到本地独立决策：

```
协调层正常
  ├─ 冲突检测 → LLM 仲裁 → 协调决策
  │
协调层超时/失败
  ├─ 各 Agent 独立决策（退化为单路口控制）
  ├─ 记录降级事件
  └─ 下一周期重试协调
  │
协调层完全不可用
  ├─ 切换到固定配时模式
  └─ 通知运维
```

```python
class CoordinationFallback:
    """协调降级策略。"""
    
    def decide_with_fallback(
        self,
        agents: dict[str, CoordinatedAgent],
        states: dict[str, StateSummary],
    ) -> dict[str, dict]:
        try:
            # 尝试协调决策
            return self._coordinated_decide(agents, states)
        except CoordinationTimeout:
            # 降级：各 Agent 独立决策
            decisions = {}
            for ix_id, agent in agents.items():
                decisions[ix_id] = agent.decide_local_only(states[ix_id])
            return decisions
        except CoordinationFailure:
            # 降级：固定配时
            return {ix_id: FIXED_PHASE_DECISION for ix_id in agents}
```

---

## 6. 多路口协调的 LLM Prompt

Agent 在做本地决策时，需要看到邻居的状态。以下是增强版的 prompt：

```python
COORDINATED_PROMPT = """你是一个城市交通信号灯AI控制专家，负责控制 {intersection_id} 路口。

## 角色
你有20年交通工程经验。你不仅关注自己路口，还与相邻路口协调。

## ⚠️ 协调意识
你不是孤立工作的。你必须考虑：
1. **下游消化能力**: 你放过去的车，下游路口能不能消化？
2. **上游车流**: 上游路口正在放什么方向的车？你需要提前准备吗？
3. **绿波配合**: 如果你在一个绿波走廊中，尽量保持相位不打断绿波。
4. **冲突避免**: 你的决策不能和相邻路口冲突。

## 协调信息
邻居路口状态：
{neighbor_states}

绿波信息：
{green_wave_info}

## 决策原则
1. **安全第一**: 确保行人和车辆安全
2. **效率优先**: 最小化总等待时间（考虑相邻路口）
3. **公平性**: 不让任何一个方向等待过久
4. **协调性**: 优先保持绿波，必要时让步
5. **应急响应**: 紧急车辆永远优先

## 输出格式
{{
    "action": "extend_green" | "switch_phase" | "emergency",
    "phase": "NS_GREEN" | "EW_GREEN",
    "duration": <秒数, 10-60>,
    "reasoning": "<决策推理，须说明协调考量>",
    "confidence": <0.0-1.0>,
    "coordination_message": "<给邻居路口的建议，可选>"
}}
"""
```

---

## 7. 通信开销分析

| 项目 | 数值 | 说明 |
|------|------|------|
| 消息大小 | ~200 bytes | StateSummary |
| 广播频率 | 每 10 秒 | 与决策周期对齐 |
| 9 路口网络 | 9 × 4 = 36 条/周期 | 每个路口向 4 个邻居广播 |
| 带宽需求 | ~7 KB/s | 36 × 200B / 10s |
| 协调 LLM 调用 | 仅冲突时 | 正常情况 0 次/周期 |

**结论**：通信开销极低，可以在任何网络环境下运行。
协调 LLM 调用只在冲突时触发，大部分周期不需要额外 API 费用。

---

## 8. 与现有代码的衔接

当前代码中已有协调的雏形：

- `crew/coordination.py` — MessageBus + ConflictDetector
- `tools/traffic_tools.py` — CoordinationMessageTool

需要的改动：
1. 将现有的 `ConflictDetector` 升级为本章设计的冲突检测规则
2. 将 `CoordinationMessageTool` 的消息格式改为 `AgentMessage` 结构
3. 新增绿波计算模块
4. 新增协调降级策略
5. 更新 LLM prompt 加入协调信息
