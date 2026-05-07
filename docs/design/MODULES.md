# 模块接口规范

> **本文件是编码指南。所有模块的类、接口、数据结构、依赖关系都在这里定义。**
> 开发时打开这个文件 + 对应的产品设计文档即可。

---

## 项目结构

```
src/traffic_agent/
├── __init__.py
├── main.py                    # 入口：串联所有模块
│
├── simulation/                # 模块1: 仿真层
│   ├── __init__.py
│   ├── engine.py              # SUMO 引擎封装
│   ├── state.py               # 路口状态数据结构
│   └── junction.py            # 路口类型定义
│
├── llm/                       # 模块2: LLM 决策层
│   ├── __init__.py
│   ├── agent.py               # Agent 核心
│   ├── prompts.py             # Prompt 模板
│   ├── safety_filter.py       # 输出安全过滤
│   └── fallback.py            # 降级策略
│
├── coordination/              # 模块3: 多路口协调
│   ├── __init__.py
│   ├── coordinator.py         # 协调器
│   ├── green_wave.py          # 绿波计算
│   ├── message_bus.py         # Agent 间通信
│   └── conflict.py            # 冲突检测
│
├── signal/                    # 模块4: 信号控制
│   ├── __init__.py
│   ├── controller.py          # 信号控制器
│   ├── phases.py              # 相位定义
│   └── pedestrian.py          # 行人信号
│
├── evaluation/                # 模块5: 评估
│   ├── __init__.py
│   ├── metrics.py             # 指标计算
│   ├── baseline.py            # 基线控制器
│   └── experiment.py          # 实验运行器
│
├── config/                    # 配置
│   ├── junctions.json         # 路口配置
│   ├── periods.json           # 时段配置
│   └── safety.json            # 安全约束配置
│
└── utils/                     # 工具
    ├── osm.py                 # OSM 路网导入
    └── logging.py             # 日志
```

---

## 模块1: 仿真层 (simulation/)

### 1.1 路口状态 `state.py`

```python
from dataclasses import dataclass, field
from enum import Enum

class Direction(str, Enum):
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"


class VehicleType(str, Enum):
    CAR = "car"
    BUS = "bus"
    TRUCK = "truck"
    MOTORCYCLE = "motorcycle"
    BICYCLE = "bicycle"
    PEDESTRIAN = "pedestrian"


@dataclass
class VehicleInfo:
    """单辆车信息。"""
    vehicle_id: str
    vehicle_type: VehicleType
    speed: float            # m/s
    position: tuple[float, float]  # (x, y)
    waiting_time: float     # 等待时间 (s)
    destination: str        # 目标方向
    is_emergency: bool = False


@dataclass
class ApproachState:
    """单个方向的状态。"""
    direction: Direction
    queue_length: int       # 排队车辆数
    waiting_time: float     # 平均等待时间 (s)
    vehicles: list[VehicleInfo] = field(default_factory=list)
    
    @property
    def has_emergency(self) -> bool:
        return any(v.is_emergency for v in self.vehicles)
    
    @property
    def composition(self) -> dict[str, int]:
        """混行构成统计。"""
        counts = {}
        for v in self.vehicles:
            counts[v.vehicle_type.value] = counts.get(v.vehicle_type.value, 0) + 1
        return counts


@dataclass
class IntersectionState:
    """路口完整状态——LLM Agent 的输入。"""
    intersection_id: str
    junction_type: str              # "cross" | "t_junction" | "y_junction" | "roundabout"
    approaches: list[ApproachState] # 各方向状态
    current_phase: str              # 当前相位
    phase_remaining: float          # 当前相位剩余时间 (s)
    pedestrian_waiting: int         # 等待过街的行人数
    timestamp: float
    
    def get_approach(self, direction: Direction) -> ApproachState | None:
        for a in self.approaches:
            if a.direction == direction:
                return a
        return None
    
    def total_queue(self) -> int:
        return sum(a.queue_length for a in self.approaches)
    
    def to_dict(self) -> dict:
        """转为 LLM 可读的字典。"""
        return {
            "intersection_id": self.intersection_id,
            "junction_type": self.junction_type,
            "current_phase": self.current_phase,
            "phase_remaining": self.phase_remaining,
            "approaches": {
                a.direction.value: {
                    "queue_length": a.queue_length,
                    "waiting_time": round(a.waiting_time, 1),
                    "composition": a.composition,
                    "has_emergency": a.has_emergency,
                }
                for a in self.approaches
            },
            "pedestrian_waiting": self.pedestrian_waiting,
        }
```

### 1.2 仿真引擎 `engine.py`

```python
from abc import ABC, abstractmethod

class SimulationEngine(ABC):
    """仿真引擎抽象接口。"""
    
    @abstractmethod
    def connect(self, config: dict) -> None:
        """连接 SUMO / 初始化仿真。"""
        ...
    
    @abstractmethod
    def get_state(self, intersection_id: str) -> IntersectionState:
        """获取路口状态。"""
        ...
    
    @abstractmethod
    def apply_decision(self, intersection_id: str, decision: dict) -> bool:
        """执行信号决策。返回是否成功。"""
        ...
    
    @abstractmethod
    def step(self) -> float:
        """推进一个仿真步，返回当前时间。"""
        ...
    
    @abstractmethod
    def is_finished(self) -> bool:
        """仿真是否结束。"""
        ...
    
    @abstractmethod
    def close(self) -> None:
        """关闭连接，清理资源。"""
        ...


class SumoEngine(SimulationEngine):
    """SUMO/TraCI 引擎实现。"""
    
    def __init__(self):
        self._conn = None
        self._config = None
    
    def connect(self, config: dict) -> None:
        import traci
        sumo_cmd = [
            "sumo", "-c", config["sumo_config"],
            "--step-length", str(config.get("step_length", 1.0)),
            "--no-step-log",
        ]
        traci.start(sumo_cmd)
        self._conn = traci
        self._config = config
    
    def get_state(self, intersection_id: str) -> IntersectionState:
        # TODO: 从 TraCI 读取真实数据
        ...
    
    def apply_decision(self, intersection_id: str, decision: dict) -> bool:
        # TODO: 通过 TraCI 设置信号灯
        ...
    
    def step(self) -> float:
        self._conn.simulationStep()
        return self._conn.simulation.getTime()
    
    def is_finished(self) -> bool:
        return self._conn.simulation.getMinExpectedNumber() == 0
    
    def close(self) -> None:
        if self._conn:
            self._conn.close()
```

---

## 模块2: LLM 决策层 (llm/)

### 2.1 LLM Agent `agent.py`

```python
@dataclass
class LLMDecision:
    """LLM 输出结构。"""
    action: str           # "extend_green" | "switch_phase" | "emergency" | "none"
    phase: str            # 目标相位
    duration: int         # 持续时间 (s)
    reasoning: str        # 推理过程
    confidence: float     # 置信度 0-1
    coordination_message: str | None = None  # 给邻居的消息


class LLMAgent:
    """LLM 交通决策 Agent。"""
    
    def __init__(self, config: dict):
        self.model = config.get("model", "gpt-4o")
        self.api_key = config["api_key"]
        self.temperature = config.get("temperature", 0.3)
        self.max_retries = config.get("max_retries", 3)
        self.timeout = config.get("timeout", 10.0)
    
    def decide(
        self,
        state: IntersectionState,
        context: dict = None,
    ) -> LLMDecision:
        """
        根据路口状态做出决策。
        
        Args:
            state: 路口当前状态
            context: 额外上下文（邻居状态、时段信息等）
        
        Returns:
            LLMDecision: 决策结果
        """
        prompt = self._build_prompt(state, context)
        raw_response = self._call_llm(prompt)
        decision = self._parse_response(raw_response)
        return decision
    
    def _build_prompt(
        self,
        state: IntersectionState,
        context: dict = None,
    ) -> str:
        """构建 LLM Prompt。"""
        # 从 prompts.py 加载模板并填充
        ...
    
    def _call_llm(self, prompt: str) -> dict:
        """调用 LLM API（OpenAI 兼容格式）。"""
        import httpx
        
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是一个交通信号控制专家。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": self.temperature,
                "response_format": {"type": "json_object"},
            },
            timeout=self.timeout,
        )
        return response.json()
    
    def _parse_response(self, raw: dict) -> LLMDecision:
        """解析 LLM 输出为结构化决策。"""
        content = raw["choices"][0]["message"]["content"]
        data = json.loads(content)
        return LLMDecision(**data)
```

### 2.2 安全过滤器 `safety_filter.py`

```python
class SafetyFilter:
    """LLM 输出安全过滤器——在决策执行前运行。"""
    
    def __init__(self, config: dict):
        self.max_green = config.get("max_green_time", 90)
        self.min_green = config.get("min_green_time", 10)
        self.max_yellow = config.get("max_yellow_time", 5)
        self.valid_phases = set(config.get("valid_phases", []))
    
    def validate(
        self,
        decision: LLMDecision,
        current_state: IntersectionState,
    ) -> tuple[bool, LLMDecision]:
        """
        验证并修正 LLM 决策。
        
        Returns:
            (is_safe, corrected_decision)
        """
        corrected = decision
        is_safe = True
        
        # 检查动作类型
        if corrected.action not in {"extend_green", "switch_phase", "emergency", "none"}:
            corrected.action = "none"
            is_safe = False
        
        # 检查相位
        if corrected.phase and corrected.phase not in self.valid_phases:
            corrected.action = "none"
            is_safe = False
        
        # 检查时长
        if corrected.duration > self.max_green:
            corrected.duration = self.max_green
        elif corrected.duration < self.min_green:
            corrected.duration = self.min_green
        
        # 检查安全约束
        violations = self._check_hard_constraints(corrected, current_state)
        if violations:
            corrected = self._auto_correct(corrected, violations)
            is_safe = False
        
        return is_safe, corrected
    
    def _check_hard_constraints(
        self,
        decision: LLMDecision,
        state: IntersectionState,
    ) -> list[str]:
        """检查硬约束。返回违反的约束列表。"""
        violations = []
        
        # 禁止同时绿灯（简化检查）
        # 实际需要根据相位定义判断
        
        # 行人安全
        if decision.action == "switch_phase" and state.pedestrian_waiting > 0:
            if decision.duration < 15:  # 行人最小过街时间
                violations.append("pedestrian_clearance")
        
        return violations
```

### 2.3 降级策略 `fallback.py`

```python
class FallbackStrategy:
    """降级策略：LLM 不可用时切换到规则引擎。"""
    
    def __init__(self):
        self.rule_engine = RuleBasedController()
    
    def decide(
        self,
        state: IntersectionState,
        llm_available: bool,
        llm_error_count: int,
    ) -> LLMDecision:
        """
        根据 LLM 可用性决定使用哪个决策源。
        
        降级路径:
        LLM → 缓存复用 → 规则引擎 → 固定配时
        """
        if llm_available and llm_error_count == 0:
            return None  # 使用 LLM 决策
        
        if llm_error_count <= 2:
            # 尝试复用最近的成功决策
            cached = self._get_cached_decision(state)
            if cached:
                return cached
        
        if llm_error_count <= 5:
            # 规则引擎
            return self.rule_engine.decide(state)
        
        # 固定配时
        return self._fixed_timing(state)
    
    def _fixed_timing(self, state: IntersectionState) -> LLMDecision:
        """固定配时兜底。"""
        return LLMDecision(
            action="switch_phase",
            phase="NS_GREEN" if state.total_queue() > 10 else "EW_GREEN",
            duration=30,
            reasoning="[降级] 固定配时模式",
            confidence=1.0,
        )
```

---

## 模块3: 多路口协调 (coordination/)

### 3.1 协调器 `coordinator.py`

```python
class Coordinator:
    """多路口协调器。"""
    
    def __init__(self, config: dict):
        self.intersection_ids = config["intersections"]
        self.state_broadcaster = StateBroadcaster()
        self.green_wave = GreenWaveCalculator()
        self.conflict_detector = ConflictDetector()
        self.agent_states: dict[str, dict] = {}
    
    def update_state(self, intersection_id: str, state: dict):
        """接收路口状态更新。"""
        self.agent_states[intersection_id] = state
    
    def check_conflicts(self) -> list[dict]:
        """检测所有冲突。"""
        return self.conflict_detector.detect_all(self.agent_states)
    
    def compute_green_wave(self, route: list[str]) -> list[dict]:
        """计算绿波方案。"""
        return self.green_wave.calculate(route, self.agent_states)
    
    def get_context(self, intersection_id: str) -> dict:
        """获取某路口的协调上下文（邻居状态、绿波约束）。"""
        neighbors = self._get_neighbors(intersection_id)
        return {
            "neighbors": {
                nid: self.agent_states.get(nid, {})
                for nid in neighbors
            },
            "green_wave_constraints": self._get_wave_constraints(intersection_id),
        }
```

### 3.2 Agent 间消息 `message_bus.py`

```python
from enum import Enum

class MessageType(str, Enum):
    STATE_BROADCAST = "state_broadcast"
    PHASE_INTENT = "phase_intent"
    PHASE_NEGOTIATE = "phase_negotiate"
    EMERGENCY_ALERT = "emergency_alert"
    INCIDENT_REPORT = "incident_report"
    COORDINATION_REQUEST = "coordination_request"


@dataclass
class Message:
    message_type: MessageType
    source_id: str
    target_id: str | None   # None = 广播
    payload: dict
    timestamp: float


class MessageBus:
    """Agent 间消息总线（内存实现，可替换为 Redis/RabbitMQ）。"""
    
    def __init__(self):
        self._handlers: dict[MessageType, list[callable]] = {}
        self._inbox: dict[str, list[Message]] = {}
    
    def publish(self, message: Message):
        """发布消息。"""
        if message.target_id:
            self._inbox.setdefault(message.target_id, []).append(message)
        else:
            # 广播给所有
            for agent_id in self._inbox:
                self._inbox[agent_id].append(message)
    
    def consume(self, agent_id: str) -> list[Message]:
        """消费某 Agent 的所有消息。"""
        messages = self._inbox.pop(agent_id, [])
        return messages
```

---

## 模块4: 信号控制 (signal/)

### 4.1 相位定义 `phases.py`

```python
@dataclass
class SignalPhase:
    """单个相位。"""
    phase_id: str
    name: str
    allowed_directions: list[str]    # 允许通行的方向
    pedestrian_phase: str | None     # 对应的行人相位
    min_duration: float = 10.0
    max_duration: float = 90.0
    yellow_duration: float = 3.0
    all_red_duration: float = 2.0


# 标准 4 相位（十字路口）
STANDARD_4_PHASES = [
    SignalPhase("NS_GREEN", "南北直行", ["north_straight", "south_straight"], "NS_PED"),
    SignalPhase("NS_LEFT", "南北左转", ["north_left", "south_left"], None),
    SignalPhase("EW_GREEN", "东西直行", ["east_straight", "west_straight"], "EW_PED"),
    SignalPhase("EW_LEFT", "东西左转", ["east_left", "west_left"], None),
]

# 丁字路口 3 相位
T_JUNCTION_3_PHASES = [
    SignalPhase("NS_GREEN", "南北直行", ["north_straight", "south_straight"], "NS_PED"),
    SignalPhase("NS_LEFT", "南北左转", ["north_left", "south_left"], None),
    SignalPhase("EW_STRAIGHT", "东西直行", ["east_straight"], "EW_PED"),
]

# 行人相位
PEDESTRIAN_PHASES = [
    SignalPhase("NS_PED", "南北行人", ["ped_north", "ped_south"], None, min_duration=15),
    SignalPhase("EW_PED", "东西行人", ["ped_east", "ped_west"], None, min_duration=15),
    SignalPhase("ALL_PED", "全向行人", ["ped_north", "ped_south", "ped_east", "ped_west"], None, min_duration=20),
]
```

### 4.2 信号控制器 `controller.py`

```python
class SignalController:
    """信号灯控制器——执行决策。"""
    
    def __init__(self, config: dict):
        self.intersection_id = config["intersection_id"]
        self.phases = config["phases"]
        self.current_phase = self.phases[0]
        self.phase_elapsed = 0.0
    
    def execute(self, decision: LLMDecision) -> bool:
        """
        执行 LLM 决策。
        
        Returns: 是否成功
        """
        if decision.action == "switch_phase":
            return self._switch_to(decision.phase, decision.duration)
        
        elif decision.action == "extend_green":
            return self._extend_current(decision.duration)
        
        elif decision.action == "emergency":
            return self._emergency_stop()
        
        elif decision.action == "none":
            return True  # 不操作
        
        return False
    
    def _switch_to(self, phase_id: str, duration: float) -> bool:
        """切换到指定相位。"""
        # 1. 黄灯过渡
        self._set_yellow()
        
        # 2. 全红清空
        self._set_all_red()
        
        # 3. 切换到目标相位
        phase = self._find_phase(phase_id)
        if not phase:
            return False
        
        self.current_phase = phase
        self.phase_elapsed = 0.0
        self._set_green(phase)
        return True
    
    def _emergency_stop(self) -> bool:
        """紧急停车：所有方向红灯。"""
        self._set_all_red()
        return True
    
    def _set_green(self, phase: SignalPhase):
        """设置绿灯。"""
        # 与 SUMO TraCI 交互
        ...
    
    def _set_yellow(self):
        """设置黄灯。"""
        ...
    
    def _set_all_red(self):
        """全红。"""
        ...
```

---

## 模块5: 评估 (evaluation/)

### 5.1 指标 `metrics.py`

```python
@dataclass
class StepMetrics:
    """单步指标。"""
    timestamp: float
    intersection_id: str
    
    # 流量指标
    total_vehicles: int
    throughput: int              # 通过路口的车辆数
    arrival_rate: float          # 到达率 (veh/s)
    
    # 延误指标
    avg_delay: float             # 平均延误 (s)
    max_delay: float             # 最大延误 (s)
    delay_p95: float             # 95分位延误
    
    # 排队指标
    avg_queue: float             # 平均排队长度
    max_queue: int               # 最大排队长度
    total_wait_time: float       # 总等待时间 (veh·s)
    
    # LLM 指标
    llm_latency: float           # LLM 响应时间 (s)
    llm_tokens: int              # token 数
    llm_cost: float              # API 成本
    llm_confidence: float        # 置信度
    llm_fallback: bool           # 是否降级


class MetricsCollector:
    """指标收集器。"""
    
    def __init__(self):
        self.steps: list[StepMetrics] = []
    
    def record(self, metrics: StepMetrics):
        self.steps.append(metrics)
    
    def get_summary(self, start: int = 0, end: int = None) -> dict:
        """获取指标汇总。"""
        data = self.steps[start:end]
        if not data:
            return {}
        
        return {
            "total_steps": len(data),
            "avg_delay": sum(m.avg_delay for m in data) / len(data),
            "avg_queue": sum(m.avg_queue for m in data) / len(data),
            "total_throughput": sum(m.throughput for m in data),
            "avg_llm_latency": sum(m.llm_latency for m in data) / len(data),
            "total_cost": sum(m.llm_cost for m in data),
            "fallback_rate": sum(1 for m in data if m.llm_fallback) / len(data),
        }
```

### 5.2 基线控制器 `baseline.py`

```python
class BaselineController(ABC):
    """基线控制器抽象接口。"""
    
    @abstractmethod
    def decide(self, state: IntersectionState) -> LLMDecision:
        ...


class FixedTimeController(BaselineController):
    """固定配时基线。"""
    
    def __init__(self, cycle: float = 90, green_ratio: float = 0.45):
        self.cycle = cycle
        self.green_ratio = green_ratio
    
    def decide(self, state: IntersectionState) -> LLMDecision:
        # 简单轮转
        if state.phase_remaining <= 0:
            next_phase = self._next_phase(state.current_phase)
            return LLMDecision(
                action="switch_phase",
                phase=next_phase,
                duration=int(self.cycle * self.green_ratio),
                reasoning="[FixedTime] 固定配时轮转",
                confidence=1.0,
            )
        return LLMDecision(action="none", phase="", duration=0,
                          reasoning="", confidence=1.0)


class MaxQueueController(BaselineController):
    """最长排队优先基线。"""
    
    def decide(self, state: IntersectionState) -> LLMDecision:
        # 找排队最长的方向，给它绿灯
        longest = max(state.approaches, key=lambda a: a.queue_length)
        target_phase = f"{longest.direction.value.upper()}_GREEN"
        
        return LLMDecision(
            action="switch_phase",
            phase=target_phase,
            duration=30,
            reasoning=f"[MaxQueue] {longest.direction.value} 排队最长 ({longest.queue_length})",
            confidence=1.0,
        )
```

---

## 模块6: 入口 `main.py`

```python
def run_single_intersection(config: dict):
    """单路口最小闭环。"""
    # 初始化
    sim = SumoEngine()
    sim.connect(config["simulation"])
    
    agent = LLMAgent(config["llm"])
    safety = SafetyFilter(config["safety"])
    fallback = FallbackStrategy()
    controller = SignalController(config["signal"])
    metrics = MetricsCollector()
    
    llm_error_count = 0
    
    # 仿真循环
    while not sim.is_finished():
        current_time = sim.step()
        state = sim.get_state(config["intersection_id"])
        
        # LLM 决策
        decision = agent.decide(state)
        
        # 安全过滤
        is_safe, decision = safety.validate(decision, state)
        
        # 降级检查
        if not is_safe:
            llm_error_count += 1
            fallback_decision = fallback.decide(state, is_safe, llm_error_count)
            if fallback_decision:
                decision = fallback_decision
        else:
            llm_error_count = 0
        
        # 执行
        controller.execute(decision)
        
        # 记录指标
        metrics.record(StepMetrics(
            timestamp=current_time,
            intersection_id=config["intersection_id"],
            # ... 其他指标
        ))
    
    # 输出结果
    summary = metrics.get_summary()
    print(json.dumps(summary, indent=2))
    
    sim.close()


def run_multi_intersection(config: dict):
    """多路口协调闭环。"""
    coordinator = Coordinator(config["coordination"])
    agents = {
        iid: LLMAgent(config["llm"])
        for iid in config["intersections"]
    }
    # ... 类似单路口，但加入协调层
```

---

## 数据流总览

```
仿真引擎 (SumoEngine)
    │ get_state()
    ▼
IntersectionState ──→ LLMAgent.decide() ──→ LLMDecision
                          │                      │
                     context ◄── Coordinator      │
                          │                      ▼
                     SafetyFilter.validate() ──→ (安全, 修正后决策)
                                                     │
                          FallbackStrategy ◄─────────┤ (如需降级)
                                                     │
                                                     ▼
                                          SignalController.execute()
                                                     │
                                                     ▼
                                              仿真引擎.apply_decision()
                                                     │
                                                     ▼
                                            MetricsCollector.record()
```

---

## 开发顺序

| 阶段 | 模块 | 文件 | 依赖 |
|------|------|------|------|
| 1 | 仿真引擎 | simulation/engine.py, state.py | SUMO |
| 2 | LLM Agent | llm/agent.py, prompts.py | OpenAI API |
| 3 | 安全过滤 | llm/safety_filter.py | 无 |
| 4 | 信号控制 | signal/controller.py, phases.py | 仿真引擎 |
| 5 | 主循环 | main.py | 全部 |
| 6 | 评估 | evaluation/metrics.py, baseline.py | 主循环 |
| 7 | 降级 | llm/fallback.py | 规则引擎 |
| 8 | 多路口 | coordination/* | 主循环 |
| 9 | 行人 | signal/pedestrian.py | 信号控制 |
| 10 | 潮汐 | config/periods.json | 配置 |
