# 第5章 完整架构与代码结构

## 项目结构

```
smart-city-agent/
├── docs/
│   └── design/              # 设计文档（本目录）
│       ├── README.md
│       ├── 00-overview.md
│       ├── 01-simulation.md
│       ├── 02-llm-agent.md
│       ├── 03-road-network.md
│       ├── 04-evaluation.md
│       ├── 05-architecture.md
│       ├── 06-comparison.md
│       └── 07-implementation.md
├── src/
│   └── traffic_agent/
│       ├── __init__.py
│       ├── cli.py           # 命令行入口
│       ├── config.py        # 配置管理
│       ├── simulation/      # 仿真层
│       │   ├── __init__.py
│       │   ├── sumo.py      # SUMO TraCI 封装
│       │   ├── bridge.py    # Sim Bridge（状态编码/动作映射）
│       │   ├── metrics.py   # 指标采集
│       │   └── scenarios.py # 异常场景注入
│       ├── llm/             # LLM 层
│       │   ├── __init__.py
│       │   ├── client.py    # 多模型 LLM 客户端
│       │   ├── prompt.py    # Prompt 模板
│       │   └── parser.py    # 响应解析
│       ├── controller/      # 控制器
│       │   ├── __init__.py
│       │   ├── base.py      # 控制器基类
│       │   ├── fixed.py     # 固定时序
│       │   ├── adaptive.py  # 自适应
│       │   └── llm.py       # LLM 控制器
│       └── evaluation/      # 评估层
│           ├── __init__.py
│           ├── runner.py    # 实验运行器
│           ├── report.py    # 报告生成
│           └── stats.py     # 统计检验
├── networks/                # 路网文件
│   ├── shenzhen/            # 优先
│   ├── wuhan/
│   └── manhattan/
├── dashboard/               # Web Dashboard（可选）
├── tests/
├── pyproject.toml
└── README.md
```

## 核心模块

### 1. 仿真层 (simulation/sumo.py)

```python
"""SUMO 仿真封装。"""
import traci
from dataclasses import dataclass

@dataclass
class IntersectionState:
    intersection_id: str
    timestamp: float
    current_phase: int
    phase_duration: float
    north_queue: int
    north_wait: float
    south_queue: int
    south_wait: float
    east_queue: int
    east_wait: float
    west_queue: int
    west_wait: float

class SumoSimulation:
    """SUMO 仿真管理器。"""
    
    def __init__(self, config: str, gui: bool = False):
        self.config = config
        self.gui = gui
    
    def start(self):
        cmd = ["sumo-gui" if self.gui else "sumo", "-c", self.config]
        traci.start(cmd)
    
    def step(self):
        traci.simulationStep()
    
    def close(self):
        traci.close()
    
    def get_state(self, tl_id: str) -> IntersectionState:
        """获取路口状态。"""
        lanes = traci.trafficlight.getControlledLanes(tl_id)
        # ... 按方向聚合数据
        return IntersectionState(...)
    
    def apply_decision(self, tl_id: str, phase: int, duration: float):
        """应用决策。"""
        traci.trafficlight.setPhase(tl_id, phase)
        traci.trafficlight.setPhaseDuration(tl_id, duration)
    
    def get_metrics(self) -> dict:
        """采集全局指标。"""
        return {
            "total_vehicles": traci.simulation.getMinExpectedNumber(),
            # ...
        }
```

### 2. Sim Bridge (simulation/bridge.py)

```python
"""仿真接口层：状态编码 + 动作映射。"""

def encode_state(state: IntersectionState) -> dict:
    """将 SUMO 状态编码为 LLM 可理解的格式。"""
    return {
        "intersection_id": state.intersection_id,
        "timestamp": state.timestamp,
        "current_phase": phase_name(state.current_phase),
        "phase_duration": state.phase_duration,
        "north": {"queue": state.north_queue, "avg_wait": state.north_wait},
        "south": {"queue": state.south_queue, "avg_wait": state.south_wait},
        "east": {"queue": state.east_queue, "avg_wait": state.east_wait},
        "west": {"queue": state.west_queue, "avg_wait": state.west_wait},
    }

def decode_decision(decision: dict) -> tuple[int, float]:
    """将 LLM 决策解码为 SUMO 操作。"""
    phase_map = {"NS_GREEN": 0, "NS_YELLOW": 1, "EW_GREEN": 2, "EW_YELLOW": 3}
    phase = phase_map[decision["phase"]]
    duration = max(10, min(60, decision["duration"]))
    return phase, duration
```

### 3. LLM 客户端 (llm/client.py)

```python
"""多模型 LLM 客户端。"""
from abc import ABC, abstractmethod

class BaseLLMClient(ABC):
    @abstractmethod
    def chat(self, system: str, user: str) -> str:
        pass

class OpenAIClient(BaseLLMClient):
    def __init__(self, model: str = "gpt-4o"):
        from openai import OpenAI
        self.client = OpenAI()
        self.model = model
    
    def chat(self, system: str, user: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content

class QwenClient(BaseLLMClient):
    # 类似实现，使用 dashscope SDK
    pass
```

### 4. 控制器 (controller/base.py)

```python
"""控制器基类。"""
from abc import ABC, abstractmethod

class BaseController(ABC):
    @abstractmethod
    def decide(self, states: dict[str, dict]) -> dict[str, dict]:
        """对所有路口做出决策。"""
        pass

class LLMController(BaseController):
    def __init__(self, llm_client, prompt_builder, parser):
        self.llm = llm_client
        self.prompt = prompt_builder
        self.parser = parser
    
    def decide(self, states):
        decisions = {}
        for tl_id, state in states.items():
            response = self.llm.chat(
                self.prompt.system(state),
                self.prompt.user(state),
            )
            decision = self.parser.parse(response)
            if not decision:
                decision = self.parser.fallback("parse error")
            decisions[tl_id] = decision
        return decisions
```

### 5. 评估运行器 (evaluation/runner.py)

```python
"""实验运行器。"""
import traci
from itertools import product

class ExperimentRunner:
    def __init__(self, networks: list, demands: list, controllers: dict):
        self.networks = networks
        self.demands = demands
        self.controllers = controllers
    
    def run_all(self):
        results = []
        for network, demand, (name, ctrl) in product(
            self.networks, self.demands, self.controllers.items()
        ):
            config = f"networks/{network}/{network}_{demand}.sumocfg"
            metrics = self._run_single(config, ctrl)
            results.append({
                "network": network,
                "demand": demand,
                "controller": name,
                **metrics,
            })
        return pd.DataFrame(results)
    
    def _run_single(self, config, controller, steps=3600):
        traci.start(["sumo", "-c", config])
        collector = MetricsCollector()
        
        for _ in range(steps):
            states = self._read_all_states()
            decisions = controller.decide(states)
            self._apply_decisions(decisions)
            traci.simulationStep()
            collector.collect()
        
        traci.close()
        return collector.summary()
```

## 数据流

```
SUMO 仿真
    ↓ traci 读取
IntersectionState (原始数据)
    ↓ encode_state()
LLM 可理解的 dict
    ↓ prompt 构建
LLM API 调用
    ↓ 响应解析
LLMDecision (结构化决策)
    ↓ decode_decision()
SUMO 操作 (setPhase, setPhaseDuration)
    ↓ 执行
SUMO 仿真推进
    ↓ 采集指标
评估报告
```

## 配置管理

```python
# config.py
from pydantic import BaseModel

class SimulationConfig(BaseModel):
    network: str = "manhattan"
    demand_level: str = "medium"
    duration: int = 3600
    step_length: int = 1

class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_tokens: int = 500
    timeout: int = 5

class EvaluationConfig(BaseModel):
    networks: list[str] = ["manhattan", "wuhan", "shenzhen"]
    demands: list[str] = ["low", "medium", "high"]
    runs_per_config: int = 5  # 统计显著性
```

## CLI 入口

```python
# cli.py
import click

@click.group()
def cli():
    pass

@cli.command()
@click.option("--network", default="manhattan")
@click.option("--controller", default="llm")
@click.option("--gui/--no-gui", default=False)
def run(network, controller, gui):
    """运行单次仿真。"""
    ...

@cli.command()
@click.option("--networks", multiple=True, default=["manhattan"])
@click.option("--output", default="report.html")
def evaluate(networks, output):
    """运行评估实验。"""
    ...

@cli.command()
def dashboard():
    """启动 Dashboard。"""
    ...
```
