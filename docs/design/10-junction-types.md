# 第10章 路口类型与信号配置设计

> **真实路网不是只有十字路口。每种路口类型都有独特的信号控制逻辑。**

## 设计背景

当前所有文档都假设标准十字路口（4 方向、8 灯、对称相位）。
但真实城市路网中：

- 丁字路口占比约 30-40%（比十字路口还多）
- 环形路口在欧洲城市常见，国内也在推广
- 5 路/6 路路口在老城区和广场常见
- 斜交路口（角度非 90°）导致左转冲突更复杂

**核心原则**：系统必须能处理任意拓扑的路口，而不是为每种类型写死逻辑。

---

## 1. 路口类型分类

### 1.1 六种基本路口类型

| 类型 | 方向数 | 灯头数 | 代表场景 | 信号复杂度 |
|------|--------|--------|---------|-----------|
| 十字路口 | 4 | 8 | 标准城市道路交叉 | ⭐⭐ |
| 丁字路口 | 3 | 6 | 支路汇入主路 | ⭐⭐ |
| Y 型路口 | 3 | 6 | 分叉路、高速出口 | ⭐⭐⭐ |
| 环形路口 | N 入口 | 0-2N | 欧式路口、大型转盘 | ⭐⭐⭐⭐ |
| 5 路/6 路 | 5-6 | 10-12 | 广场、老城区 | ⭐⭐⭐⭐⭐ |
| 斜交路口 | 4 | 8 | 非正交道路交叉 | ⭐⭐⭐ |

### 1.2 路口类型识别

从 OSM 数据自动识别路口类型：

```python
from enum import Enum
from dataclasses import dataclass
import math

class JunctionType(str, Enum):
    """路口类型。"""
    CROSS = "cross"          # 十字路口：4 方向，角度接近 90°
    T_JUNCTION = "t_junction"  # 丁字路口：3 方向
    Y_JUNCTION = "y_junction"  # Y 型路口：3 方向，角度非 90°
    ROUNDABOUT = "roundabout"  # 环形路口
    MULTI_WAY = "multi_way"    # 5 路及以上
    SKEW = "skew"              # 斜交路口：4 方向，角度偏离 90°


@dataclass
class JunctionGeometry:
    """路口几何信息。"""
    junction_id: str
    junction_type: JunctionType
    num_approaches: int           # 方向数
    approach_angles: list[float]  # 各方向的角度 (度，从正北顺时针)
    has_pedestrian_signals: bool  # 是否有人行信号灯
    num_vehicle_signals: int      # 车道信号灯数
    num_pedestrian_signals: int   # 人行信号灯数
    total_signals: int            # 总信号灯数
    lane_config: dict             # 各方向车道配置
    is_roundabout: bool = False
    roundabout_diameter: float = 0.0  # 环形路口直径 (m)


def identify_junction_type(intersection_data: dict) -> JunctionType:
    """
    从路网数据识别路口类型。
    
    输入：SUMO junction 数据或 OSM node 数据
    - incoming_edges: 连入的道路列表
    - angles: 各道路的进入角度
    
    识别规则：
    - 3 条道路 → 丁字或 Y 型
    - 4 条道路 → 十字或斜交
    - 5+ 条道路 → 多路
    - 有 roundabout 标记 → 环形
    """
    num_edges = len(intersection_data.get("incoming_edges", []))
    angles = intersection_data.get("angles", [])
    is_roundabout = intersection_data.get("type") == "roundabout"
    
    if is_roundabout:
        return JunctionType.ROUNDABOUT
    
    if num_edges >= 5:
        return JunctionType.MULTI_WAY
    
    if num_edges == 3:
        # 判断丁字 vs Y 型
        if len(angles) >= 3:
            angle_diffs = [
                abs(angles[i] - angles[(i+1) % 3])
                for i in range(3)
            ]
            # 如果任意两个方向夹角接近 180°，是丁字路口（T 形）
            # 如果三个方向分散，是 Y 型
            has_straight = any(abs(d - 180) < 30 for d in angle_diffs)
            if has_straight:
                return JunctionType.T_JUNCTION
            else:
                return JunctionType.Y_JUNCTION
        return JunctionType.T_JUNCTION  # 默认
    
    if num_edges == 4:
        # 判断十字 vs 斜交
        if len(angles) >= 4:
            angle_diffs = [
                abs(angles[i] - angles[(i+1) % 4])
                for i in range(4)
            ]
            # 十字路口：相邻方向夹角接近 90°
            is_cross = all(abs(d - 90) < 25 for d in angle_diffs)
            if is_cross:
                return JunctionType.CROSS
            else:
                return JunctionType.SKEW
        return JunctionType.CROSS  # 默认
    
    return JunctionType.CROSS  # 默认
```

---

## 2. 各路口类型的信号灯配置

### 2.1 十字路口（Cross Junction）

```
        N (2灯)
        │
  W(2灯)─┼─ E(2灯)
        │
        S (2灯)

总计: 4方向 × 2灯/方向 = 8灯
├── 车道信号灯: 4 个 (每个方向 1 个)
└── 人行信号灯: 4 个 (每个方向 1 个)
```

**标准相位设计（第 9 章已定义）**：

| 相位 | 车道灯 | 人行灯 | 持续时间 |
|------|--------|--------|---------|
| NS_GREEN | 南北绿 | 南北行人可过街 | 30-60s |
| NS_YELLOW | 南北黄 | 禁止 | 3s |
| ALL_RED_1 | 全红 | 禁止 | 2s |
| NS_LEFT | 南北左转绿 | 禁止 | 15-25s |
| NS_LEFT_YEL | 南北左转黄 | 禁止 | 3s |
| ALL_RED_2 | 全红 | 禁止 | 2s |
| EW_GREEN | 东西绿 | 东西行人可过街 | 30-60s |
| EW_YELLOW | 东西黄 | 禁止 | 3s |
| ALL_RED_3 | 全红 | 禁止 | 2s |
| EW_LEFT | 东西左转绿 | 禁止 | 15-25s |
| EW_LEFT_YEL | 东西左转黄 | 禁止 | 3s |
| ALL_RED_4 | 全红 | 禁止 | 2s |
| PED_ALL | 全红 | 全向行人绿 | 15-25s |
| PED_ALL_YEL | 全红 | 行人闪烁 | 5s |

---

### 2.2 丁字路口（T-Junction）

```
        N (2灯)
        │
        ┼─ E (2灯)
        │
        S (2灯)

总计: 3方向 × 2灯/方向 = 6灯
├── 车道信号灯: 3 个
└── 人行信号灯: 3 个
```

**丁字路口的关键区别**：
- 没有西方向，南北方向不需要等东西对向
- 左转逻辑不同：从 N 左转到 E 不需要让对向（因为没有对向）
- 可以有更短的周期（少一个方向的竞争）

**相位设计**：

| 相位 | 车道灯 | 人行灯 | 持续时间 | 说明 |
|------|--------|--------|---------|------|
| N_GREEN | 北绿 | 北行人可过街 | 30-50s | 北方向直行+右转 |
| N_YELLOW | 北黄 | 禁止 | 3s | |
| ALL_RED_1 | 全红 | 禁止 | 2s | |
| N_LEFT | 北左转绿 | 禁止 | 15-20s | 北→东左转（无对向冲突） |
| N_LEFT_YEL | 北左转黄 | 禁止 | 3s | |
| ALL_RED_2 | 全红 | 禁止 | 2s | |
| EW_GREEN | 东西绿 | 东西行人可过街 | 30-50s | 东+南方向 |
| EW_YELLOW | 东西黄 | 禁止 | 3s | |
| ALL_RED_3 | 全红 | 禁止 | 2s | |
| PED_N | 全红 | 北行人绿 | 10-15s | 北方向过街 |
| PED_EW | 全红 | 东西行人绿 | 10-15s | 东+南方向过街 |

**相位数**：11 个（比十字路口少 3 个）

```python
T_JUNCTION_PHASES = [
    {"name": "N_GREEN",      "vehicle": [0],           "pedestrian": [0],     "min": 30, "max": 50},
    {"name": "N_YELLOW",     "vehicle": [],            "pedestrian": [],      "fixed": 3},
    {"name": "ALL_RED_1",    "vehicle": [],            "pedestrian": [],      "fixed": 2},
    {"name": "N_LEFT",       "vehicle": [0],           "pedestrian": [],      "min": 15, "max": 20, "movement": "left"},
    {"name": "N_LEFT_YEL",   "vehicle": [],            "pedestrian": [],      "fixed": 3},
    {"name": "ALL_RED_2",    "vehicle": [],            "pedestrian": [],      "fixed": 2},
    {"name": "EW_GREEN",     "vehicle": [1, 2],        "pedestrian": [1, 2],  "min": 30, "max": 50},
    {"name": "EW_YELLOW",    "vehicle": [],            "pedestrian": [],      "fixed": 3},
    {"name": "ALL_RED_3",    "vehicle": [],            "pedestrian": [],      "fixed": 2},
    {"name": "PED_N",        "vehicle": [],            "pedestrian": [0],     "min": 10, "max": 15},
    {"name": "PED_EW",       "vehicle": [],            "pedestrian": [1, 2],  "min": 10, "max": 15},
]
# approach 编号: 0=北, 1=东, 2=南 (无西方向)
```

---

### 2.3 Y 型路口（Y-Junction）

```
      N (2灯)
       ╲
        ╲
         ╲
    E(2灯)─┼─ S(2灯)

总计: 3方向 × 2灯/方向 = 6灯
├── 车道信号灯: 3 个
└── 人行信号灯: 3 个
```

**Y 型路口的关键区别**：
- 三个方向的角度不是 90°/180°，而是约 120°
- 左转冲突更复杂：N→S 的左转和 E→S 的左转可能同时发生
- 视距受限：斜角导致驾驶员视野受限

**相位设计**：类似丁字路口，但需要额外注意斜交左转冲突。

---

### 2.4 环形路口（Roundabout）

```
            入口1
             │
      ┌──────┼──────┐
      │    ╭───╮    │
入口4 ─┤   │     │   ├─ 入口2
      │    ╰───╯    │
      └──────┼──────┘
             │
            入口3

环形路口信号灯:
├── 无信号环形: 0 个灯 (环内让行)
├── 信号控制环形: 每个入口 1-2 个灯
└── 典型: 4入口 × 2灯 = 8灯 (环内+入口)
```

**环形路口的两种控制方式**：

| 方式 | 描述 | 适用场景 |
|------|------|---------|
| **无信号环形** | 环内车辆优先，入口车辆让行 | 低流量（< 1000 veh/h） |
| **信号控制环形** | 入口信号灯控制进入节奏 | 高流量（> 1000 veh/h） |

**信号控制环形的相位设计**：

```python
ROUNDABOUT_PHASES = [
    # 每次只放一个入口进环
    {"name": "ENTRY_1",  "entry": 1,  "duration": [15, 25]},
    {"name": "ENTRY_2",  "entry": 2,  "duration": [15, 25]},
    {"name": "ENTRY_3",  "entry": 3,  "duration": [15, 25]},
    {"name": "ENTRY_4",  "entry": 4,  "duration": [15, 25]},
    # 可选：行人相位
    {"name": "PED_CROSS", "pedestrian": True, "duration": [10, 15]},
]
```

**环形路口的特殊规则**：
- 环内车辆永远优先（不需要信号）
- 入口信号控制进入流量，防止环内拥堵
- 多个入口同时绿灯时，需要检测环内是否有足够空间
- 行人在环外的人行道过街，不在环内

---

### 2.5 5 路/6 路路口（Multi-Way Junction）

```
      N
     ╱│╲
    ╱ │ ╲
  NW ─┼─ NE
    ╲ │ ╱
     ╲│╱
      S
      │
     SW

5-6 个方向，10-12 个信号灯
```

**多路路口的关键挑战**：
- 相位数爆炸：N 个方向最多需要 N 个独立相位
- 协调困难：每个方向都可能和其他方向冲突
- 行人过街复杂：需要多个斑马线，可能需要分段

**相位设计原则**：

```python
def generate_multi_way_phases(num_approaches: int) -> list[dict]:
    """
    为多路路口生成相位方案。
    
    策略：对向放行（类似十字路口的扩展）
    - 优先放行对向方向（如果存在）
    - 其次放行相邻方向
    - 每个相位最多同时放行 2 个方向
    """
    phases = []
    
    # 找对向方向对
    pairs = find_opposing_pairs(num_approaches)
    
    for pair in pairs:
        phases.append({
            "name": f"PHASE_{pair[0]}_{pair[1]}",
            "vehicle": pair,
            "min": 20,
            "max": 40,
        })
        phases.append({
            "name": f"PHASE_{pair[0]}_{pair[1]}_YELLOW",
            "vehicle": [],
            "fixed": 3,
        })
        phases.append({
            "name": f"ALL_RED_{len(phases)}",
            "vehicle": [],
            "fixed": 2,
        })
    
    return phases
```

---

### 2.6 斜交路口（Skew Junction）

```
      N
       ╲
        ╲
  W ─────╳───── E    ← 角度不是 90°
        ╱
       ╱
      S

4 方向，但角度偏离 90°
```

**斜交路口的特殊问题**：
- 左转路径更长（角度导致转弯半径变大）
- 对向直行的视距受限
- 行人过街距离不等（斜角导致某些方向更长）

**处理方式**：复用十字路口的相位设计，但调整：
- 左转时间增加（转弯路径更长）
- 清空时间增加（视距受限）
- 行人过街时间根据实际距离计算

---

## 3. 信号灯硬件抽象

### 3.1 统一信号灯模型

不管什么路口类型，信号灯都可以抽象为统一模型：

```python
@dataclass
class SignalHead:
    """单个信号灯头。"""
    signal_id: str
    signal_type: str        # "vehicle" | "pedestrian" | "bicycle"
    approach: int           # 所在方向编号
    position: str           # "left" | "center" | "right" | "far_side"
    controlled_movements: list[str]  # 控制的转向 ["straight", "left", "right"]
    
    # 当前状态
    current_state: str = "red"  # "red" | "yellow" | "green" | "flashing"


@dataclass
class SignalPlan:
    """路口信号方案——与路口类型无关。"""
    junction_id: str
    junction_type: JunctionType
    signal_heads: list[SignalHead]
    phases: list[dict]
    
    # 路口几何
    approaches: list[int]       # 有效方向编号列表
    num_phases: int
    
    @property
    def num_vehicle_signals(self) -> int:
        return sum(1 for s in self.signal_heads if s.signal_type == "vehicle")
    
    @property
    def num_pedestrian_signals(self) -> int:
        return sum(1 for s in self.signal_heads if s.signal_type == "pedestrian")
    
    @property
    def total_signals(self) -> int:
        return len(self.signal_heads)
```

### 3.2 从 SUMO 自动生成信号方案

```python
import traci

def auto_generate_signal_plan(tl_id: str) -> SignalPlan:
    """
    从 SUMO 信号灯自动提取信号方案。
    
    SUMO 的信号灯程序已经定义了相位和灯头映射，
    我们只需要解析并转换为统一格式。
    """
    # 获取信号灯程序
    programs = traci.trafficlight.getAllProgramLogics(tl_id)
    program = programs[0]
    
    # 获取控制的车道
    controlled_lanes = traci.trafficlight.getControlledLanes(tl_id)
    
    # 获取信号灯类型定义
    type_id = traci.trafficlight.getTypeID(tl_id)
    
    # 解析相位
    phases = []
    for i, phase in enumerate(program.phases):
        phases.append({
            "index": i,
            "duration": phase.duration,
            "state": phase.state,  # "GGGrrr" 格式的灯状态
            "min_duration": phase.minDuration if hasattr(phase, 'minDuration') else None,
            "max_duration": phase.maxDuration if hasattr(phase, 'maxDuration') else None,
        })
    
    # 识别路口方向
    approaches = identify_approaches(controlled_lanes)
    
    # 生成信号灯头
    signal_heads = generate_signal_heads(tl_id, controlled_lanes, approaches)
    
    return SignalPlan(
        junction_id=tl_id,
        junction_type=identify_junction_type_from_sumo(tl_id),
        signal_heads=signal_heads,
        phases=phases,
        approaches=approaches,
        num_phases=len(phases),
    )
```

---

## 4. LLM Agent 的路口类型感知

### 4.1 核心问题

LLM Agent 需要知道自己控制的是什么类型的路口，因为：
- 不同路口类型的相位数不同
- 左转冲突规则不同
- 可用的决策空间不同
- 邻居数量和协调方式不同

### 4.2 增强版 Prompt

```python
JUNCTION_TYPE_PROMPT = """
## 路口类型信息
你正在控制的路口类型：{junction_type}
- 方向数：{num_approaches}
- 车道信号灯：{num_vehicle_signals} 个
- 人行信号灯：{num_pedestrian_signals} 个
- 总信号灯：{total_signals} 个
- 相位数：{num_phases}

有效方向：{valid_directions}

## 路口类型特殊规则
{junction_specific_rules}
"""

JUNCTION_RULES = {
    JunctionType.CROSS: """
- 标准十字路口，4 方向对称
- 南北方向和东西方向交替放行
- 左转需要保护相位（对向直行红灯时左转）
- 行人和同向机动车同时过街
""",
    JunctionType.T_JUNCTION: """
- 丁字路口，只有 {valid_directions} 三个方向
- 没有 {missing_direction} 方向，不需要考虑该方向的车流
- 左转冲突较少（因为缺少对向）
- 可以使用更短的信号周期
- 行人只有 {ped_directions} 三个方向的斑马线
""",
    JunctionType.Y_JUNCTION: """
- Y 型路口，三个方向斜交
- 角度不是 90°，左转路径更长
- 视距受限，需要更长的清空时间
- 行人过街距离不等
""",
    JunctionType.ROUNDABOUT: """
- 环形路口，环内车辆优先
- 入口信号灯控制进入节奏
- 每次只放一个入口进环
- 行人在环外过街，不在环内
""",
    JunctionType.MULTI_WAY: """
- {num_approaches} 路路口，相位数较多
- 对向方向优先同时放行
- 每个相位最多同时放行 2 个方向
- 协调难度较高，需要更多 LLM 推理
""",
    JunctionType.SKEW: """
- 斜交路口，角度偏离 90°
- 左转路径更长，需要更多时间
- 清空时间需要增加
- 行人过街距离不等
""",
}
```

### 4.3 Agent 决策空间适配

```python
class JunctionAwareAgent:
    """路口类型感知的 Agent。"""
    
    def __init__(self, signal_plan: SignalPlan, llm_client):
        self.signal_plan = signal_plan
        self.llm = llm_client
        self.junction_type = signal_plan.junction_type
        
        # 根据路口类型调整决策空间
        self.valid_phases = self._get_valid_phases()
        self.valid_movements = self._get_valid_movements()
    
    def _get_valid_phases(self) -> list[str]:
        """获取当前路口类型的有效相位列表。"""
        return [p["name"] for p in self.signal_plan.phases]
    
    def _get_valid_movements(self) -> list[str]:
        """获取当前路口类型的有效转向。"""
        movements = ["straight"]
        if self.junction_type != JunctionType.ROUNDABOUT:
            movements.extend(["left", "right"])
        return movements
    
    def decide(self, state: dict) -> dict:
        """基于路口类型做决策。"""
        # 构建带路口类型信息的 prompt
        prompt = self._build_prompt(state)
        
        # LLM 决策
        decision = self.llm.decide(prompt)
        
        # 验证决策合法性（相位必须是当前路口的有效相位）
        if decision["phase"] not in self.valid_phases:
            decision = self._fallback_to_valid_phase(decision)
        
        return decision
    
    def _build_prompt(self, state: dict) -> str:
        """构建包含路口类型信息的 prompt。"""
        junction_info = JUNCTION_TYPE_PROMPT.format(
            junction_type=self.junction_type.value,
            num_approaches=self.signal_plan.num_phases,
            num_vehicle_signals=self.signal_plan.num_vehicle_signals,
            num_pedestrian_signals=self.signal_plan.num_pedestrian_signals,
            total_signals=self.signal_plan.total_signals,
            num_phases=len(self.signal_plan.phases),
            valid_directions=", ".join(
                str(a) for a in self.signal_plan.approaches
            ),
            junction_specific_rules=JUNCTION_RULES.get(
                self.junction_type, ""
            ).format(
                valid_directions=", ".join(
                    str(a) for a in self.signal_plan.approaches
                ),
                missing_direction=self._get_missing_direction(),
                ped_directions=", ".join(
                    str(a) for a in self.signal_plan.approaches
                ),
            ),
        )
        
        return f"""{junction_info}

## 当前路况
{state_to_text(state)}

## 决策
"""
    
    def _get_missing_direction(self) -> str:
        """获取缺失的方向（丁字路口用）。"""
        all_dirs = {0: "北", 1: "东", 2: "南", 3: "西"}
        present = set(self.signal_plan.approaches)
        missing = set(range(4)) - present
        return "、".join(all_dirs.get(d, str(d)) for d in missing)
```

---

## 5. 路口类型对协调的影响

### 5.1 邻居定义的变化

```python
def get_junction_neighbors(
    junction_id: str,
    junction_type: JunctionType,
    road_network: dict,
) -> list[str]:
    """
    根据路口类型获取邻居。
    
    十字路口：4 个邻居（每个方向一个）
    丁字路口：3 个邻居
    环形路口：环上相邻的入口
    多路路口：最多 N 个邻居
    """
    neighbors = road_network.get(junction_id, {}).get("neighbors", [])
    
    if junction_type == JunctionType.ROUNDABOUT:
        # 环形路口的邻居是环上相邻的入口
        # 而不是物理上最近的路口
        neighbors = get_roundabout_neighbors(junction_id, road_network)
    
    return neighbors


def get_roundabout_neighbors(
    roundabout_id: str,
    road_network: dict,
) -> list[str]:
    """获取环形路口的环上邻居。"""
    # 环形路口的"邻居"是环上相邻的入口
    # 这些入口之间有环内道路连接
    entries = road_network.get(roundabout_id, {}).get("entries", [])
    return entries
```

### 5.2 绿波计算的变化

丁字路口和环形路口的绿波计算不同于十字路口：

```python
def calculate_green_wave_for_junction_type(
    junction_type: JunctionType,
    intersections: list[str],
    distances: dict,
) -> GreenWavePlan:
    """根据路口类型调整绿波计算。"""
    
    if junction_type == JunctionType.T_JUNCTION:
        # 丁字路口：只有 2 个方向可能有绿波
        # （主路方向，不是支路方向）
        main_road_intersections = filter_main_road(intersections)
        return calculate_green_wave(main_road_intersections, distances)
    
    elif junction_type == JunctionType.ROUNDABOUT:
        # 环形路口：不参与传统绿波
        # 环内车流是连续的，不需要相位差
        return GreenWavePlan(
            corridor="roundabout",
            intersections=[roundabout_id],
            direction="circulatory",
            design_speed=8.33,  # 环内限速 30 km/h
            cycle_time=0,  # 无周期
            offsets={},
        )
    
    else:
        # 十字路口/斜交：标准绿波
        return calculate_green_wave(intersections, distances)
```

---

## 6. 从 OSM/SUMO 自动适配

### 6.1 自动检测流程

```
OSM 数据
  ↓
netconvert 转换
  ↓
SUMO .net.xml (包含 junction 信息)
  ↓
自动检测路口类型
  ↓
生成对应的信号方案
  ↓
LLM Agent 自动适配
```

### 6.2 关键代码

```python
def auto_adapt_from_sumo(net_xml: str) -> dict[str, SignalPlan]:
    """
    从 SUMO 路网文件自动检测所有路口类型并生成信号方案。
    
    返回: {junction_id: SignalPlan}
    """
    import xml.etree.ElementTree as ET
    
    tree = ET.parse(net_xml)
    root = tree.getroot()
    
    signal_plans = {}
    
    for junction in root.findall(".//junction"):
        junction_id = junction.get("id")
        junction_type_raw = junction.get("type", "priority")
        
        # 获取连接的道路
        inc_lanes = junction.get("incLanes", "").split()
        int_lanes = junction.get("intLanes", "").split()
        
        # 计算方向和角度
        num_approaches = len(set(
            lane.split("_")[0] for lane in inc_lanes if lane
        ))
        
        # 识别路口类型
        if junction_type_raw == "roundabout":
            j_type = JunctionType.ROUNDABOUT
        elif num_approaches == 3:
            j_type = JunctionType.T_JUNCTION  # 简化：3路默认丁字
        elif num_approaches >= 5:
            j_type = JunctionType.MULTI_WAY
        else:
            j_type = JunctionType.CROSS
        
        # 生成信号方案
        tl_id = junction.get("tl")
        if tl_id:
            signal_plans[junction_id] = auto_generate_signal_plan(tl_id)
        else:
            # 无信号路口（环形或优先权路口）
            signal_plans[junction_id] = generate_priority_plan(junction_id, j_type)
    
    return signal_plans
```

---

## 7. 测试矩阵

| 路口类型 | 测试场景 | 验证点 |
|---------|---------|--------|
| 十字路口 | 标准 4 相位 | 相位切换、行人过街、左转冲突 |
| 丁字路口 | 3 方向不对称 | 缺失方向处理、相位数减少 |
| Y 型路口 | 斜交角度 | 左转时间增加、清空时间 |
| 环形路口 | 信号控制 | 入口轮流放行、环内优先 |
| 5 路路口 | 多方向 | 对向放行、相位数 |
| 斜交路口 | 非 90° | 视距、清空时间 |

---

## 8. 实现优先级

| 优先级 | 功能 | 工作量 |
|--------|------|--------|
| P0 | 十字路口 + 丁字路口自动识别 | 1 天 |
| P0 | 丁字路口相位设计 | 0.5 天 |
| P0 | LLM prompt 路口类型适配 | 0.5 天 |
| P1 | Y 型 + 斜交路口 | 1 天 |
| P1 | 环形路口（信号控制版） | 2 天 |
| P2 | 5 路/6 路多路口 | 1 天 |
| P2 | 从 SUMO 自动检测路口类型 | 1 天 |
| P3 | 路口类型切换的降级策略 | 0.5 天 |
