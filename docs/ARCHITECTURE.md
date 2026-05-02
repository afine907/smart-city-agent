# 🏗️ Architecture — LLM Traffic Controller

> **System Design Document — LLM Multi-Agent Traffic Signal Control**

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [System Overview](#system-overview)
3. [Core Components](#core-components)
4. [Multi-Agent Protocol](#multi-agent-protocol)
5. [LLM Integration Design](#llm-integration-design)
6. [Simulation Engine](#simulation-engine)
7. [Observability & Explainability](#observability--explainability)
8. [Cost & Performance](#cost--performance)
9. [Failure Modes & Recovery](#failure-modes--recovery)

---

## 1. Design Philosophy

### Core Insight

> **LLMs are not just classifiers — they are reasoning engines.**
> Traffic signal control is not just optimization — it's **judgment under uncertainty**.

Traditional RL treats traffic control as a mathematical optimization problem.
LLM-based agents treat it as a **reasoning problem**: "Given what I know about
traffic engineering, what's the best decision right now?"

### Why LLM Wins Here

| Dimension | Traditional RL | LLM Multi-Agent |
|-----------|---------------|-----------------|
| Training | 100K+ episodes, GPU | Zero-shot, prompt only |
| Explainability | Black box | Natural language reasoning |
| Generalization | Limited to training distribution | Handles novel scenarios |
| Coordination | Complex reward shaping | Natural language negotiation |
| Maintenance | Retrain on distribution shift | Update prompt |
| Cost | GPU infrastructure | API calls only |

### Design Principles

1. **Explainability First** — Every decision has a reasoning trace
2. **Fail-Safe** — Rule-based fallback if LLM fails
3. **Cost-Aware** — Smart caching to minimize API calls
4. **Observable** — Dashboard shows agent "thoughts" in real-time
5. **Composable** — Agents, tasks, crews are pluggable

---

## 2. System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     LLM Traffic Controller                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐           │
│  │  Agent: 北路口 │  │  Agent: 东路口 │  │  Agent: 南路口 │           │
│  │  Role: 信号控制│  │  Role: 信号控制│  │  Role: 信号控制│           │
│  │  Goal: 最小化 │  │  Goal: 最小化 │  │  Goal: 最小化 │           │
│  │        等待时间 │  │        等待时间 │  │        等待时间 │           │
│  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘           │
│          │                  │                  │                   │
│          │    ┌─────────────┴─────────────┐    │                   │
│          │    │                           │    │                   │
│          ▼    ▼                           ▼    ▼                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    CrewAI Task Orchestration                │   │
│  │                                                             │   │
│  │  Task 1: 各Agent观察路况 → 独立决策                         │   │
│  │  Task 2: Agent间交换决策 → 协调冲突                         │   │
│  │  Task 3: 协调Agent仲裁 → 最终方案                           │   │
│  │  Task 4: 执行决策 → 记录推理过程                             │   │
│  └──────────────────────────┬──────────────────────────────────┘   │
│                              │                                     │
│                              ▼                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   Simulation Engine                          │   │
│  │  • 路网建模        • 车辆生成          • 状态采集            │   │
│  │  • 信号灯控制      • 指标统计          • 事件处理            │   │
│  └──────────────────────────┬──────────────────────────────────┘   │
│                              │                                     │
│                              ▼                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                  Real-Time Dashboard                         │   │
│  │  🧠 Agent推理过程  │  🚦 信号灯状态  │  📊 通行效率指标      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Components

### 3.1 Agent Layer (CrewAI Agents)

Each intersection is a **CrewAI Agent** with a specific role:

```python
from crewai import Agent, Task, Crew

class IntersectionAgentFactory:
    """Factory for creating intersection traffic agents."""
    
    @staticmethod
    def create(intersection_id: str, neighbors: List[str]) -> Agent:
        return Agent(
            role=f"Traffic Signal Controller for {intersection_id}",
            goal=f"Minimize vehicle wait time at {intersection_id} intersection "
                 f"while coordinating with neighboring intersections: {neighbors}",
            backstory="""You are an experienced traffic engineer with 20 years 
            of field experience. You understand signal timing, peak hour patterns, 
            emergency vehicle priority, and pedestrian safety. You make decisions 
            based on real-time data and coordinate with adjacent intersections 
            to create green waves.""",
            tools=[TrafficObservationTool(intersection_id)],
            llm="gpt-4o-mini",  # Fast, cheap for routine decisions
            allow_delegation=False,
            verbose=True,
        )
```

### 3.2 Task Layer (CrewAI Tasks)

```python
class TrafficControlCrew:
    """Orchestrates multi-agent traffic control."""
    
    def __init__(self, intersections: List[str], graph: Dict):
        self.agents = self._create_agents(intersections, graph)
        self.tasks = self._create_tasks(intersections)
    
    def _create_tasks(self, intersections: List[str]) -> List[Task]:
        tasks = []
        
        for ix_id in intersections:
            # Task 1: Observe and decide
            tasks.append(Task(
                description=f"""
                观察 {ix_id} 路口的实时路况，做出信号灯决策。
                
                当前路况数据：{{traffic_data}}
                邻居路口状态：{{neighbor_states}}
                
                输出格式：
                - 行动：extend_green / switch_phase / emergency
                - 阶段：NS_GREEN / EW_GREEN
                - 时长：秒数
                - 理由：你的决策推理过程
                - 协调消息：给邻居路口的建议
                """,
                agent=self.agents[ix_id],
                expected_output="JSON格式的决策结果，包含action/phase/duration/reasoning",
            ))
        
        # Task 2: Coordination
        tasks.append(Task(
            description="""
            收集所有路口Agent的决策，检查冲突并协调。
            
            如果两个相邻路口同时请求绿灯冲突，需要协商出一个方案。
            
            输出：协调后的最终决策列表。
            """,
            agent=self.agents["coordinator"],
            expected_output="协调后的JSON决策列表",
            context=tasks,  # Depends on all intersection tasks
        ))
        
        return tasks
```

### 3.3 Tool Layer

```python
from crewai.tools import BaseTool

class TrafficObservationTool(BaseTool):
    """Tool for agents to observe traffic state."""
    name: str = "observe_traffic"
    description: str = "获取当前路口的实时交通数据"
    
    def _run(self, intersection_id: str) -> str:
        """Return current traffic state as structured text."""
        state = simulation.get_state(intersection_id)
        return f"""
        路口: {intersection_id}
        时间: {state.timestamp}
        
        各方向排队:
        - 北: {state.queue_north}辆, 等待{state.wait_north}s
        - 南: {state.queue_south}辆, 等待{state.wait_south}s
        - 东: {state.queue_east}辆, 等待{state.wait_east}s
        - 西: {state.queue_west}辆, 等待{state.wait_west}s
        
        当前信号: {state.current_phase}, 已持续{state.phase_duration}s
        紧急车辆: {'有' if state.emergency else '无'}
        """

class CoordinationTool(BaseTool):
    """Tool for agents to communicate with neighbors."""
    name: str = "coordinate_with_neighbor"
    description: str = "向邻居路口发送协调消息"
    
    def _run(self, neighbor_id: str, message: str) -> str:
        """Send message to neighbor agent."""
        return message_bus.send(current_agent_id, neighbor_id, message)
```

---

## 4. Multi-Agent Protocol

### 4.1 Communication Flow

```
Round 1: Observation & Independent Decision
┌─────────┐         ┌─────────┐         ┌─────────┐
│ Agent A │         │ Agent B │         │ Agent C │
│         │         │         │         │         │
│ 观察路况 │         │ 观察路况 │         │ 观察路况 │
│ 独立决策 │         │ 独立决策 │         │ 独立决策 │
└────┬────┘         └────┬────┘         └────┬────┘
     │                   │                   │
     ▼                   ▼                   ▼
  决策A               决策B               决策C

Round 2: Coordination & Conflict Resolution
┌─────────┐         ┌─────────┐         ┌─────────┐
│ Agent A │◄───────►│ Coord.  │◄───────►│ Agent B │
│ "我要绿灯"│        │ Agent   │        │ "我也要" │
│         │         │ 协调仲裁 │         │         │
└─────────┘         └────┬────┘         └─────────┘
                         │
                    ┌────▼────┐
                    │ Agent C │
                    │ "同意让步"│
                    └─────────┘

Round 3: Execution
所有Agent执行协调后的决策
```

### 4.2 Message Protocol

```python
@dataclass
class AgentMessage:
    """Inter-agent communication message."""
    sender: str           # Agent ID
    receiver: str         # Agent ID or "broadcast"
    msg_type: str         # "decision" | "request" | "agree" | "alert"
    content: str          # Natural language content
    data: dict            # Structured data (optional)
    timestamp: float
    round_id: int         # Coordination round
```

### 4.3 Conflict Resolution Rules

1. **Emergency Priority**: Emergency vehicle requests always win
2. **Queue-based**: Higher queue length gets priority
3. **Fairness**: If both queues similar, alternate who gets green
4. **Coordinator Override**: Final tiebreaker by coordinator agent

---

## 5. LLM Integration Design

### 5.1 Prompt Engineering Strategy

```python
SYSTEM_PROMPT = """你是一个城市交通信号灯AI控制系统中的路口控制Agent。

## 角色
你负责控制 {intersection_id} 路口的信号灯。你有20年交通工程经验。

## 决策原则
1. **安全第一**: 确保行人和车辆安全
2. **效率优先**: 最小化总等待时间
3. **公平性**: 不要让任何一个方向等待过久
4. **协调性**: 与邻居路口配合，创造绿波带
5. **应急响应**: 紧急车辆永远优先

## 信号灯阶段
- NS_GREEN: 南北方向绿灯 (10-60秒)
- NS_YELLOW: 南北方向黄灯 (3秒)
- EW_GREEN: 东西方向绿灯 (10-60秒)
- EW_YELLOW: 东西方向黄灯 (3秒)

## 输出格式
你必须输出严格的JSON格式：
{
    "action": "extend_green" | "switch_phase" | "emergency",
    "phase": "NS_GREEN" | "EW_GREEN",
    "duration": <秒数, 10-60>,
    "reasoning": "<你的决策推理过程>",
    "confidence": <0.0-1.0>,
    "coordination_message": "<给邻居路口的消息, 可选>"
}
"""
```

### 5.2 Cost Optimization

```
┌─────────────────────────────────────────────────┐
│              Cost Optimization Strategy          │
├─────────────────────────────────────────────────┤
│                                                 │
│  Tier 1: Rule-based (FREE)                      │
│  ├─ 常规状态变化 < 10%                           │
│  ├─ 延长当前绿灯                                  │
│  └─ 无需调用 LLM                                 │
│                                                 │
│  Tier 2: Cached Decision (FREE)                 │
│  ├─ 相似路况模式                                  │
│  ├─ 查找历史缓存                                  │
│  └─ 命中率 ~40%                                  │
│                                                 │
│  Tier 3: Fast LLM ($0.001/call)                 │
│  ├─ 常规决策                                     │
│  ├─ GPT-4o-mini / Qwen-Turbo                    │
│  └─ 每5秒一次                                    │
│                                                 │
│  Tier 4: Smart LLM ($0.01/call)                 │
│  ├─ 复杂协调、异常场景                              │
│  ├─ GPT-4o / Qwen-Plus                          │
│  └─ 仅在需要时调用                                │
│                                                 │
│  预估成本: 9路口城市 × 24小时                     │
│  = ~$2-5/天 (大部分走Tier 1-2)                   │
│                                                 │
└─────────────────────────────────────────────────┘
```

### 5.3 Response Parsing & Validation

```python
class ResponseParser:
    """Parse and validate LLM responses."""
    
    VALID_ACTIONS = {"extend_green", "switch_phase", "emergency"}
    VALID_PHASES = {"NS_GREEN", "EW_GREEN", "NS_YELLOW", "EW_YELLOW"}
    
    @staticmethod
    def parse(response: str) -> Optional[Dict]:
        try:
            # Extract JSON from response
            data = json.loads(response)
            
            # Validate
            if data["action"] not in ResponseParser.VALID_ACTIONS:
                return None
            if data["phase"] not in ResponseParser.VALID_PHASES:
                return None
            if not (10 <= data["duration"] <= 60):
                data["duration"] = max(10, min(60, data["duration"]))
            
            return data
        except (json.JSONDecodeError, KeyError):
            return None
    
    @staticmethod
    def fallback(reason: str) -> Dict:
        """Rule-based fallback when LLM fails."""
        return {
            "action": "extend_green",
            "phase": "NS_GREEN",
            "duration": 15,
            "reasoning": f"LLM响应无效，使用规则回退: {reason}",
            "confidence": 0.5,
        }
```

---

## 6. Simulation Engine

### 6.1 Lightweight Simulation

```python
class SimulationEngine:
    """
    Lightweight traffic simulation.
    
    NOT SUMO — fully custom, zero dependencies.
    Purpose: Provide realistic enough data for LLM decision making.
    """
    
    def __init__(self, config: SimulationConfig):
        self.road_network = RoadNetwork()
        self.vehicle_manager = VehicleManager()
        self.clock = 0.0
        
    def get_state(self, intersection_id: str) -> IntersectionState:
        """Get current state for an intersection."""
        pass
    
    def apply_decision(self, intersection_id: str, decision: Dict) -> None:
        """Apply LLM decision to simulation."""
        pass
    
    def step(self, dt: float) -> None:
        """Advance simulation by dt seconds."""
        pass
```

### 6.2 Vehicle Behavior

```python
class Vehicle:
    """Simple vehicle model."""
    id: str
    approach: int       # 0=N, 1=E, 2=S, 3=W
    position: float     # meters from intersection
    speed: float        # m/s
    desired_speed: float
    waiting: bool
    
    def update(self, dt: float, has_green: bool) -> None:
        if at_intersection and not has_green:
            self.speed = 0
            self.waiting = True
        else:
            self.speed = self.desired_speed
            self.waiting = False
        self.position -= self.speed * dt
```

---

## 7. Observability & Explainability

### 7.1 Agent Reasoning Dashboard

```
┌─────────────────────────────────────────────────────────────────┐
│  🧠 Agent Reasoning — Intersection 北路口                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Time: 08:32:15  │  Phase: NS_GREEN  │  Duration: 45s/60s      │
│                                                                 │
│  ┌─ Traffic State ─────────────────────────────────────────┐   │
│  │  北: 23辆 ⏳12s  │  南: 18辆 ⏳8s                       │   │
│  │  东:  5辆 ⏳2s   │  西:  4辆 ⏳1s                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ Agent Reasoning ───────────────────────────────────────┐   │
│  │  "当前南北方向车流量明显高于东西方向（23+18 vs 5+4）。     │   │
│  │   南北绿灯已持续45秒，北方向仍有23辆车排队，需要延长。    │   │
│  │   东西方向车很少，不会造成太大影响。                       │   │
│  │   东路口Agent反馈他们那边东方向车多，                     │   │
│  │   但我评估后认为南北方向优先级更高。"                      │   │
│  │                                                          │   │
│  │   → 决策: 延长NS_GREEN 15秒                              │   │
│  │   → 置信度: 0.85                                         │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ Coordination Messages ─────────────────────────────────┐   │
│  │  ➜ 东路口: "我需要延长南北绿灯，请配合"                   │   │
│  │  ◀ 南路口: "同意，我这边南北方向也车多"                   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 Metrics

```python
METRICS = {
    # Traffic flow
    "traffic.wait_time_avg": Gauge,
    "traffic.wait_time_p95": Gauge,
    "traffic.throughput": Gauge,
    "traffic.queue_max": Gauge,
    
    # LLM performance
    "llm.calls_total": Counter,
    "llm.calls_by_tier": Counter,
    "llm.latency_ms": Histogram,
    "llm.cost_total": Gauge,
    "llm.cache_hit_rate": Gauge,
    "llm.fallback_rate": Gauge,
    
    # Agent reasoning
    "agent.confidence_avg": Gauge,
    "agent.coordination_success": Counter,
    "agent.conflict_resolution": Counter,
}
```

---

## 8. Cost & Performance

### 8.1 Cost Model

| Component | Cost | Notes |
|-----------|------|-------|
| GPT-4o-mini | $0.15/1M input tokens | Routine decisions |
| GPT-4o | $2.50/1M input tokens | Complex coordination |
| Qwen-Turbo | ¥0.003/千tokens | 国内替代 |
| Qwen-Plus | ¥0.008/千tokens | 国内高级 |

### 8.2 Latency Requirements

| Action | Target Latency | Strategy |
|--------|---------------|----------|
| Rule-based decision | < 1ms | No LLM call |
| Cached decision | < 5ms | Lookup |
| Fast LLM decision | < 500ms | GPT-4o-mini |
| Complex coordination | < 2s | GPT-4o |

---

## 9. Failure Modes & Recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| LLM timeout | Response > 5s | Use cached decision |
| LLM invalid response | Parse error | Rule-based fallback |
| LLM rate limit | 429 error | Queue + retry |
| Agent crash | No response | Restart agent, use rules |
| Network partition | API unreachable | Full rule-based mode |

### Fallback Chain

```
LLM Decision → Cache Hit → Rule-based → Safe Default (current phase extend)
```

---

## Appendix: Tech Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Multi-Agent | **CrewAI** | Role-based agents, task orchestration |
| LLM | OpenAI / Qwen API | Production-grade, flexible |
| Simulation | Custom lightweight | Zero deps, full control |
| Dashboard | React + WebSocket | Real-time, interactive |
| API | FastAPI | Async, fast, typed |
| Logging | Structured JSON | Observability |
