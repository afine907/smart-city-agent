# 🤖 CrewAI Multi-Agent Design

> **Detailed design for CrewAI-based traffic control system**

## Crew Structure

```
Traffic Control Crew
├── Agents
│   ├── 北路口 Agent (Intersection A)
│   ├── 南路口 Agent (Intersection B)
│   ├── 东路口 Agent (Intersection C)
│   ├── 西路口 Agent (Intersection D)
│   ├── 中心路口 Agent (Intersection E)
│   └── 协调 Agent (Coordinator)
│
├── Tasks
│   ├── observe_and_decide (per intersection)
│   ├── coordinate_neighbors (coordinator)
│   ├── resolve_conflicts (coordinator)
│   └── execute_decisions (all)
│
└── Tools
    ├── TrafficObservationTool
    ├── NeighborStateTool
    ├── SendCoordinationMessageTool
    └── EmergencyAlertTool
```

## Agent Definitions

### 1. Intersection Agent (per路口)

```python
intersection_agent = Agent(
    role="Traffic Signal Controller",
    goal="Minimize vehicle wait time at your intersection while "
         "maintaining safety and coordinating with neighbors",
    backstory=TRAFFIC_EXPERT_PROMPT,
    tools=[TrafficObservationTool(), NeighborStateTool()],
    llm="gpt-4o-mini",
    allow_delegation=False,
    max_iter=3,  # Max reasoning steps
)
```

### 2. Coordinator Agent

```python
coordinator_agent = Agent(
    role="Traffic Coordination Supervisor",
    goal="Resolve conflicts between intersection agents and "
         "optimize city-wide traffic flow",
    backstory=COORDINATOR_PROMPT,
    tools=[SendCoordinationMessageTool(), EmergencyAlertTool()],
    llm="gpt-4o",  # Stronger model for complex reasoning
    allow_delegation=True,
    max_iter=5,
)
```

## Task Definitions

### Task 1: Observe and Decide

```python
observe_task = Task(
    description="""
    你正在控制 {intersection_id} 路口。
    
    当前路况数据：
    {traffic_state}
    
    邻居路口状态：
    {neighbor_states}
    
    请分析当前路况并做出信号灯决策。
    
    考虑因素：
    1. 各方向排队长度
    2. 等待时间
    3. 邻居路口的需求
    4. 是否有紧急车辆
    5. 当前时段（早高峰/晚高峰/平峰）
    
    输出严格的JSON格式决策。
    """,
    agent=intersection_agent,
    expected_output="JSON decision with action/phase/duration/reasoning",
)
```

### Task 2: Coordinate

```python
coordinate_task = Task(
    description="""
    收集所有路口Agent的决策结果。
    
    各路口决策：
    {all_decisions}
    
    检查是否存在冲突（如相邻路口同时要求绿灯）。
    如果有冲突，根据以下规则协调：
    1. 紧急车辆优先
    2. 排队长的优先
    3. 公平轮转
    
    输出协调后的最终决策。
    """,
    agent=coordinator_agent,
    expected_output="Coordinated JSON decisions",
    context=[observe_task],  # Runs after observe_task
)
```

## Task Execution Flow

```
┌─────────────────────────────────────────────────────┐
│                CrewAI Execution Flow                 │
├─────────────────────────────────────────────────────┤
│                                                     │
│  1. 仿真引擎生成路况数据                              │
│     ↓                                               │
│  2. 创建 Observe Tasks (并行，每个路口一个)            │
│     ↓                                               │
│  3. 各 Intersection Agent 独立执行                    │
│     - 读取路况                                       │
│     - 调用 LLM 推理                                  │
│     - 输出决策                                       │
│     ↓                                               │
│  4. 收集所有决策                                     │
│     ↓                                               │
│  5. Coordinator Agent 协调                           │
│     - 检查冲突                                       │
│     - 协商解决                                       │
│     - 输出最终方案                                    │
│     ↓                                               │
│  6. 仿真引擎执行最终决策                              │
│     ↓                                               │
│  7. 记录推理过程 + 指标                               │
│     ↓                                               │
│  8. 返回步骤1 (下一个决策周期)                         │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## LLM Call Optimization

### Smart Decision Router

```python
class DecisionRouter:
    """Route decisions to appropriate tier."""
    
    def should_call_llm(self, state: TrafficState) -> Tuple[bool, str]:
        """Determine if LLM call is needed."""
        
        # Tier 1: Rule-based
        if self._is常规状态(state):
            return False, "rule_based"
        
        # Tier 2: Cache hit
        cache_key = self._state_to_key(state)
        if cache_key in self.cache:
            return False, "cache_hit"
        
        # Tier 3: Fast LLM
        if not self._needs_coordination(state):
            return True, "fast_llm"
        
        # Tier 4: Smart LLM
        return True, "smart_llm"
    
    def _is常规状态(self, state: TrafficState) -> bool:
        """Check if state is routine (small change from last decision)."""
        delta = abs(state.queue_total - self.last_state.queue_total)
        return delta < 5  # Less than 5 vehicles changed
```

## Error Handling

```python
class LLMFallbackChain:
    """Fallback chain when LLM fails."""
    
    def execute(self, state: TrafficState) -> Dict:
        try:
            # Try LLM
            return self.llm_agent.decide(state)
        except LLMTimeout:
            return self._cache_fallback(state)
        except LLMRateLimit:
            return self._queue_and_retry(state)
        except LLMInvalidResponse:
            return self._rule_based_fallback(state)
        except Exception:
            return self._safe_default(state)
    
    def _rule_based_fallback(self, state: TrafficState) -> Dict:
        """Simple rule-based decision."""
        max_queue_approach = np.argmax(state.queue_lengths)
        return {
            "action": "switch_phase",
            "phase": f"{'NS' if max_queue_approach in [0,2] else 'EW'}_GREEN",
            "duration": min(30, 10 + state.queue_lengths[max_queue_approach] * 2),
            "reasoning": "LLM失败，使用规则回退",
        }
```

## Cost Tracking

```python
class CostTracker:
    """Track LLM API costs."""
    
    def __init__(self):
        self.total_cost = 0.0
        self.calls_by_tier = defaultdict(int)
        self.cost_by_tier = defaultdict(float)
    
    def record_call(self, tier: str, tokens: int, model: str):
        cost = self._calculate_cost(tokens, model)
        self.total_cost += cost
        self.calls_by_tier[tier] += 1
        self.cost_by_tier[tier] += cost
    
    def get_daily_estimate(self) -> float:
        """Estimate daily cost based on current usage."""
        return self.total_cost * (24 * 3600 / elapsed_seconds)
```
