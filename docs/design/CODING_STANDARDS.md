# 编码规范

> **代码是给人读的，顺便让机器执行。**

---

## 1. SOLID 原则

### S — 单一职责 (Single Responsibility)

**每个类只做一件事。** 判断标准：如果一个类的名字里有两个动词，拆开。

```python
# ❌ 一个类干两件事
class TrafficManager:
    def decide_phase(self, state): ...
    def send_to_sumo(self, decision): ...

# ✅ 拆成两个类
class PhaseDecider:
    """决策：根据状态选相位。"""
    def decide(self, state: IntersectionState) -> LLMDecision: ...

class SignalExecutor:
    """执行：把决策发给 SUMO。"""
    def execute(self, decision: LLMDecision) -> bool: ...
```

### O — 开闭原则 (Open/Closed)

**对扩展开放，对修改关闭。** 新增基线控制器不需要改已有代码。

```python
# ✅ 基类定义接口
class BaselineController(ABC):
    @abstractmethod
    def decide(self, state: IntersectionState) -> LLMDecision: ...

# ✅ 新增控制器只需继承
class FixedTimeController(BaselineController):
    def decide(self, state): ...

class MaxQueueController(BaselineController):
    def decide(self, state): ...

class AdaptiveController(BaselineController):
    def decide(self, state): ...

# ❌ 每新增一种就改 if-else
def get_controller(type):
    if type == "fixed": return FixedTimeController()
    elif type == "max_queue": return MaxQueueController()  # 每次加新的都要改这里
```

### L — 里氏替换 (Liskov Substitution)

**子类必须能替换父类。** 如果子类的行为和父类不一致，继承就是错的。

```python
# ❌ MaxQueueController 忽略行人，行为不一致
class MaxQueueController(BaselineController):
    def decide(self, state):
        # 纯看排队，完全不管行人
        longest = max(state.approaches, key=lambda a: a.queue_length)
        ...

# ✅ 如果行为不同，要么改名，要么组合
class MaxQueueIgnoringPedestrians(BaselineController):
    """最长排队优先（不考虑行人）。用于对比评估。"""
    ...
```

### I — 接口隔离 (Interface Segregation)

**不要强迫实现不需要的方法。**

```python
# ❌ 巨型接口
class SimulationInterface(ABC):
    def connect(self): ...
    def get_state(self): ...
    def apply_decision(self): ...
    def get_metrics(self): ...
    def export_log(self): ...
    def render_video(self): ...  # 不是所有引擎都支持渲染

# ✅ 拆成小接口
class Readable(ABC):
    @abstractmethod
    def get_state(self, id: str) -> IntersectionState: ...

class Writable(ABC):
    @abstractmethod
    def apply_decision(self, id: str, decision: dict) -> bool: ...

class Steppable(ABC):
    @abstractmethod
    def step(self) -> float: ...

# SumoEngine 实现三个接口
class SumoEngine(Readable, Writable, Steppable): ...

# 某些引擎可能不支持写入（只读回放）
class ReplayEngine(Readable, Steppable): ...
```

### D — 依赖倒置 (Dependency Inversion)

**依赖抽象，不依赖具体实现。** 用构造函数注入。

```python
# ❌ 硬编码依赖
class TrafficController:
    def __init__(self):
        self.agent = OpenAIAgent()  # 写死了 OpenAI

# ✅ 依赖注入
class TrafficController:
    def __init__(self, agent: LLMAgent):  # 接口类型
        self.agent = agent  # 可以是 OpenAI、Qwen、本地模型

# ❌ 在类内部创建依赖
class LLMAgent:
    def decide(self, state):
        prompt = PromptBuilder.build(state)  # 内部创建
        ...

# ✅ 外部注入
class LLMAgent:
    def __init__(self, prompt_builder: PromptBuilder):
        self.prompt_builder = prompt_builder
```

---

## 2. DRY — 不要重复自己

**三条规则：**
1. **逻辑重复** → 提取函数
2. **结构重复** → 提取基类
3. **概念重复** → 提取常量

```python
# ❌ 逻辑重复
if vehicle.speed == 0 and vehicle.waiting_time > 30:
    ...
if vehicle.speed == 0 and vehicle.waiting_time > 60:
    ...

# ✅ 提取函数
def is_queueing(vehicle: VehicleInfo, threshold: float = 30) -> bool:
    return vehicle.speed == 0 and vehicle.waiting_time > threshold

# ❌ 字符串重复
if direction == "north" or direction == "south":
    ...
if direction == "east" or direction == "west":
    ...

# ✅ 提取常量
NS_DIRECTIONS = {Direction.NORTH, Direction.SOUTH}
EW_DIRECTIONS = {Direction.EAST, Direction.WEST}

if direction in NS_DIRECTIONS:
    ...
```

**DRY 的反面：不要过度抽象。** 如果两段代码只是长得像但语义不同，不要合并。

```python
# ❌ 过度抽象：两个完全不同的场景硬凑在一起
def handle_vehicle(v, context):
    if context == "simulation":
        return _sim_handle(v)
    elif context == "real_world":
        return _real_handle(v)

# ✅ 语义不同就分开
class SimVehicleHandler: ...
class RealVehicleHandler: ...
```

---

## 3. TDD — 测试驱动开发

### 开发流程

```
1. 写测试（定义期望行为）
2. 运行测试（应该失败）
3. 写最少的代码让测试通过
4. 重构（保持测试通过）
5. 重复
```

### 测试命名规范

```python
# 格式: test_<被测行为>_<场景>_<期望结果>
def test_safety_filter_rejects_simultaneous_green():
    ...

def test_safety_filter_allows_valid_phase_switch():
    ...

def test_llm_agent_returns_fallback_on_api_timeout():
    ...
```

### 测试结构：Arrange-Act-Assert

```python
def test_safety_filter_rejects_simultaneous_green():
    # Arrange
    safety = SafetyFilter(config={"max_green_time": 90})
    state = IntersectionState(
        intersection_id="test",
        junction_type="cross",
        approaches=[...],
        current_phase="NS_GREEN",
        phase_remaining=0,
        pedestrian_waiting=0,
        timestamp=0,
    )
    decision = LLMDecision(
        action="switch_phase",
        phase="EW_GREEN",  # 错误：NS 和 EW 不能同时绿灯
        duration=30,
        reasoning="test",
        confidence=0.9,
    )
    
    # Act
    is_safe, corrected = safety.validate(decision, state)
    
    # Assert
    assert not is_safe
    assert corrected.action == "none"
```

### Mock 原则

```python
# ✅ Mock 外部依赖（LLM API、SUMO、网络）
@patch("traffic_agent.llm.agent.httpx.post")
def test_llm_agent_handles_api_timeout(mock_post):
    mock_post.side_effect = httpx.TimeoutException("timeout")
    agent = LLMAgent(config)
    decision = agent.decide(state)
    assert decision.action == "none"  # 降级

# ✅ 不 Mock 内部逻辑
# 直接测类的行为，不要 mock 自己的方法

# ❌ 不要 Mock 所有东西
@patch("traffic_agent.llm.agent.LLMAgent._call_llm")
@patch("traffic_agent.llm.agent.LLMAgent._build_prompt")
@patch("traffic_agent.llm.agent.LLMAgent._parse_response")
def test_llm_agent_does_nothing(mock_parse, mock_build, mock_call):
    # 这测的是 mock，不是真实行为
    ...
```

### 测试覆盖率目标

| 模块 | 目标覆盖率 | 说明 |
|------|-----------|------|
| safety_filter | > 95% | 安全相关，必须全覆盖 |
| signal/controller | > 90% | 信号控制，关键路径 |
| llm/agent | > 80% | LLM 调用需要 mock |
| coordination/* | > 80% | 多路口协调 |
| evaluation/* | > 70% | 指标计算 |
| main.py | > 60% | 集成测试覆盖 |

---

## 4. Python 代码风格

### 命名规范

```python
# 类: PascalCase
class IntersectionState: ...

# 函数/方法: snake_case
def get_queue_length(direction: str) -> int: ...

# 常量: UPPER_SNAKE_CASE
MAX_GREEN_TIME = 90
DEFAULT_CYCLE = 120

# 私有方法: _前缀
def _validate_phase(phase: str) -> bool: ...

# 模块级函数 vs 类方法:
# 有状态 → 类方法
# 无状态 → 模块级函数
```

### 类型注解

**所有公开方法必须有类型注解。**

```python
# ❌ 没有类型注解
def get_state(intersection_id):
    ...

# ✅ 完整类型注解
def get_state(self, intersection_id: str) -> IntersectionState:
    ...

# ✅ 复杂类型用 typing
from typing import Optional

def decide(
    self,
    state: IntersectionState,
    context: Optional[dict] = None,
) -> LLMDecision:
    ...
```

### 文档字符串

**公开类和公开方法必须有 docstring。私有方法不需要。**

```python
class SafetyFilter:
    """LLM 输出安全过滤器。
    
    在 LLM 决策执行前运行，检查是否违反安全硬约束。
    如果违反，自动修正或拒绝执行。
    
    Usage:
        safety = SafetyFilter(config)
        is_safe, decision = safety.validate(llm_decision, state)
    """
    
    def validate(self, decision, state):
        """验证并修正 LLM 决策。
        
        Args:
            decision: LLM 输出的决策
            state: 当前路口状态
            
        Returns:
            (is_safe, corrected_decision) 元组
        """
        ...
```

### 错误处理

```python
# ✅ 明确的异常类型
class LLMAPIError(Exception):
    """LLM API 调用失败。"""
    pass

class SafetyViolationError(Exception):
    """安全约束违反。"""
    pass

# ✅ 捕获具体异常，不要裸 except
try:
    response = httpx.post(url, timeout=5.0)
except httpx.TimeoutException:
    logger.warning("LLM API 超时")
    return fallback.decide(state)
except httpx.HTTPStatusError as e:
    logger.error(f"LLM API 错误: {e.response.status_code}")
    return fallback.decide(state)

# ❌ 不要吞掉异常
try:
    do_something()
except:
    pass  # 灾难

# ❌ 不要捕获太宽
try:
    do_something()
except Exception:
    ...
```

---

## 5. 文件组织

### 每个文件的大小限制

| 类型 | 建议上限 | 超过时 |
|------|---------|--------|
| 模块文件 | 300 行 | 拆分子模块 |
| 单个类 | 200 行 | 拆分职责 |
| 单个函数 | 50 行 | 提取子函数 |
| 测试文件 | 500 行 | 按功能拆分 |

### import 顺序

```python
# 1. 标准库
import json
import time
from enum import Enum
from dataclasses import dataclass, field

# 2. 第三方库
import httpx

# 3. 项目内部
from traffic_agent.simulation.state import IntersectionState
from traffic_agent.llm.prompts import build_prompt
```

---

## 6. Git 规范

### Commit Message 格式

```
<type>(<scope>): <subject>

type:
  feat     新功能
  fix      修复
  docs     文档
  test     测试
  refactor 重构
  style    格式
  chore    构建/工具

scope: simulation / llm / signal / coordination / evaluation / main
```

示例：
```
feat(llm): 添加 LLM 输出安全过滤器
fix(signal): 修复黄灯时间计算错误
test(simulation): 添加 IntersectionState 单元测试
docs: 更新模块接口规范
```

### 分支规范

```
main          生产分支，不直接提交
├── feat/xxx  功能分支
├── fix/xxx   修复分支
└── docs/xxx  文档分支
```

### PR 规范

- 标题清晰：说明做了什么
- 描述包含：为什么做、怎么做的、测试情况
- 至少一个 reviewer approve
- CI 全部通过

---

## 7. 代码审查清单

提交 PR 前自查：

```markdown
## 功能
- [ ] 代码实现了设计文档描述的功能
- [ ] 边界情况已处理
- [ ] 错误处理完善

## 质量
- [ ] 没有重复代码（DRY）
- [ ] 类/函数职责单一（SRP）
- [ ] 依赖通过注入（DIP）
- [ ] 类型注解完整
- [ ] 公开 API 有 docstring

## 测试
- [ ] 新增代码有对应测试
- [ ] 测试覆盖关键路径
- [ ] 测试命名清晰
- [ ] 所有测试通过

## 安全
- [ ] LLM 输出经过安全过滤
- [ ] 没有硬编码密钥
- [ ] 没有危险的 eval/exec
```

---

## 8. 反模式警告

| 反模式 | 问题 | 正确做法 |
|--------|------|---------|
| God Class | 一个类几百行 | 拆职责 |
| 万能 if-else | `if type == "A" ... elif type == "B"` | 多态/策略模式 |
| 硬编码 | `if queue > 30` | 常量或配置 |
| 全局状态 | `global config` | 依赖注入 |
| 注释代码 | `# old_code()` | 删掉，有 git |
| 过早优化 | "以后可能需要" | 先写简单版本 |
| 复制粘贴 | Ctrl+C Ctrl+V | 提取函数 |
| 忽略异常 | `except: pass` | 至少记录日志 |
