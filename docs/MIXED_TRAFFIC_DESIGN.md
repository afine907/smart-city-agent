# 🚦 混行交通与路口复杂度设计文档

> **从 Demo 到真实场景：让仿真引擎逼近现实路口**

## 设计目标

本项目的核心价值不是"能跑通"，而是**能逼近真实路口的复杂度**。
如果仿真引擎只模拟汽车直行 + 固定信号灯，那和一个 CSS 动画没有本质区别。

本设计覆盖以下维度：
1. 混行交通参与者
2. 信号相位设计
3. 路口几何与车道功能
4. 车辆行为模型
5. 交通需求模型（时间维度）
6. 交通事件与异常

---

## 1. 混行交通参与者

### 1.1 车辆类型定义

真实路口的交通流不是单一的"汽车"，而是多种交通参与者混行。

| 类型 | 枚举值 | 默认占比 | 正常速度 | 信号遵守 | 特殊行为 |
|------|--------|---------|---------|---------|---------|
| 🚗 汽车 | `car` | 55% | 50 km/h | ✅ 始终遵守 | — |
| 🚌 公交车 | `bus` | 5% | 40 km/h | ✅ 始终遵守 | 体积大、加速慢、进站停靠 |
| 🛵 电动自行车 | `e_bike` | 25% | 22.5 km/h | ⚠️ 15% 违规 | 穿插机动车道、不走非机动车道 |
| 🚲 自行车 | `bicycle` | 10% | 15 km/h | ⚠️ 5% 违规 | 可能闯红灯 |
| 🚶 行人 | `pedestrian` | 5% | 5 km/h | ⚠️ 10% 违规 | 横穿马路、闯红灯、犹豫行为 |
| 🚑 紧急车辆 | `emergency` | 按需 | 60 km/h | ❌ 可闯红灯 | 永远优先、其他车辆让行 |

### 1.2 物理属性

每种类型有独立的物理属性，影响仿真行为：

```python
VEHICLE_TYPES = {
    "car":       {"length": 4.5m, "width": 1.8m, "accel": 2.5, "decel": 4.5, "space": 7.5m},
    "bus":       {"length": 12m,  "width": 2.5m, "accel": 1.5, "decel": 3.5, "space": 15m},
    "e_bike":    {"length": 1.8m, "width": 0.6m, "accel": 2.0, "decel": 5.0, "space": 2.5m},
    "bicycle":   {"length": 1.7m, "width": 0.5m, "accel": 1.0, "decel": 4.0, "space": 2.2m},
    "pedestrian":{"length": 0.5m, "width": 0.5m, "accel": 0.5, "decel": 3.0, "space": 0.8m},
    "emergency": {"length": 5.5m, "width": 2.2m, "accel": 3.0, "decel": 5.0, "space": 9.0m},
}
```

其中 `space` 是在排队时占用的纵向空间（车身长度 + 安全间距），直接影响排队长度计算。

### 1.3 信号遵守模型

不同类型对信号灯的遵守程度不同，这是混行交通的核心复杂度之一：

- **汽车/公交**：始终遵守信号灯（`respects_signal=True`）
- **电动自行车**：15% 概率无视信号灯（`violation_rate=0.15`）
- **自行车**：5% 概率无视信号灯
- **行人**：10% 概率闯红灯（`jaywalking_rate=0.10`）
- **紧急车辆**：始终无视信号灯（`has_priority=True`）

违规率可通过 `SimulationConfig` 配置，适应不同城市/路口的实际违规水平。

### 1.4 混行比例配置

```python
# 中国城市路口典型配置
config = SimulationConfig(
    car_ratio=0.55,      # 汽车
    bus_ratio=0.05,      # 公交
    e_bike_ratio=0.25,   # 电动自行车
    bicycle_ratio=0.10,  # 自行车
    pedestrian_ratio=0.05, # 行人
)

# 深圳留仙洞（电动车密集）
config = SimulationConfig(
    car_ratio=0.30,
    e_bike_ratio=0.50,
    pedestrian_ratio=0.10,
    bicycle_ratio=0.05,
    bus_ratio=0.05,
)

# 美国郊区（几乎纯汽车）
config = SimulationConfig(
    car_ratio=1.0,
    bus_ratio=0.0, e_bike_ratio=0.0,
    bicycle_ratio=0.0, pedestrian_ratio=0.0,
)
```

比例之和必须为 1.0，紧急车辆通过 `emergency_rate` 单独控制。

---

## 2. 信号相位设计

### 2.1 当前设计（Phase 3）

目前的信号灯只有 4 个相位：

```
NS_GREEN → NS_YELLOW → ALL_RED_1 → EW_GREEN → EW_YELLOW → ALL_RED_2
```

这是最简单的两相位控制，只区分南北和东西方向。

### 2.2 目标设计：多相位信号

真实路口至少需要以下相位：

```
┌──────────────────────────────────────────────────────────────────┐
│                     完整信号相位设计                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Phase 1: NS 直行 (NS_GREEN)                                    │
│  ├─ 南北方向直行车辆通行                                          │
│  └─ 东西方向红灯                                                │
│                                                                  │
│  Phase 2: NS 左转 (NS_LEFT)                                     │
│  ├─ 南北方向左转车辆通行（保护左转）                              │
│  ├─ 对向直行红灯                                                │
│  └─ 行人红灯                                                    │
│                                                                  │
│  Phase 3: EW 直行 (EW_GREEN)                                    │
│  ├─ 东西方向直行车辆通行                                          │
│  └─ 南北方向红灯                                                │
│                                                                  │
│  Phase 4: EW 左转 (EW_LEFT)                                     │
│  ├─ 东西方向左转车辆通行（保护左转）                              │
│  ├─ 对向直行红灯                                                │
│  └─ 行人红灯                                                    │
│                                                                  │
│  Phase 5: 行人过街 (PEDESTRIAN)                                  │
│  ├─ 所有方向机动车红灯                                           │
│  └─ 行人绿灯（全向过街或分向过街）                                │
│                                                                  │
│  每个相位之间有黄灯 + 全红过渡                                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 2.3 感应式信号（Adaptive Signal）

LLM Agent 不应该只做"延长绿灯/切换相位"这种简单决策。真实世界的感应式信号会：

1. **检测排队长度** → 排队长的方向优先
2. **检测行人按钮** → 有人按了过街按钮才给行人相位
3. **检测公交到达** → 公交快到路口时延长绿灯（公交优先）
4. **潮汐车道** → 早高峰南北多就多给南北绿灯

这些都需要 LLM 在 prompt 中获得足够的信息来决策。

### 2.4 信号相位数据结构

```python
@dataclass
class SignalPhase:
    """A single signal phase."""
    name: str                    # e.g., "NS_LEFT"
    duration: float              # seconds
    green_approaches: list[int]  # which approaches get green
    allowed_movements: list[str] # ["straight", "left", "right", "u_turn"]
    pedestrian_phase: bool       # is this a pedestrian-dedicated phase?
    min_duration: float = 10.0   # minimum green time
    max_duration: float = 60.0   # maximum green time

@dataclass
class SignalPlan:
    """Complete signal plan for an intersection."""
    phases: list[SignalPhase]
    pedestrian_request: bool     # pedestrian button pressed?
    current_phase_index: int = 0
```

---

## 3. 路口几何与车道功能

### 3.1 问题：当前没有区分直行和左转

现在的仿真中，所有车辆从一个 approach 进来，不区分它是要直行还是左转。
这导致：
- 没有左转冲突
- 没有右转与行人的冲突
- 没有掉头
- LLM 看不到"直行 vs 左转"的比例，无法做出合理的相位决策

### 3.2 目标：车道级建模

```
                    ┌─────────────────────┐
                    │      北 approach     │
                    │  ┌───┬───┬───┬───┐  │
                    │  │左转│直行│直行│右转│  │
                    │  └───┴───┴───┴───┘  │
                    └──────────┬──────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
    ┌────┴────┐           ┌────┴────┐           ┌────┴────┐
    │西 approach│          │  路口   │          │东 approach│
    │左│直│直│右│          │         │          │左│直│直│右│
    └────┬────┘           └────┬────┘           └────┬────┘
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │      南 approach     │
                    │  ┌───┬───┬───┬───┐  │
                    │  │右转│直行│直行│左转│  │
                    │  └───┬───┴───┴───┘  │
                    └─────────────────────┘
```

### 3.3 车道功能定义

```python
@dataclass
class Lane:
    """A single lane at an approach."""
    lane_type: str     # "left_turn" | "straight" | "right_turn" | "u_turn" | "bus_lane" | "bike_lane"
    direction: int     # 0=N, 1=E, 2=S, 3=W (which approach)
    position: int      # lane index within the approach (0=leftmost)
    shared: bool = False  # shared with other movements?

@dataclass
class Approach:
    """An approach to an intersection."""
    direction: int             # 0=N, 1=E, 2=S, 3=W
    lanes: list[Lane]
    has_bike_lane: bool = False
    has_bus_stop: bool = False  # bus stop near this approach?
    crosswalk: bool = False     # pedestrian crosswalk?
```

### 3.4 左转冲突

左转车辆在没有保护左转相位时，需要让对向直行车辆先走（"让行规则"）。

```
左转冲突示意：

    ↑ 直行     ↓ 对向直行
    │           │
    │     ◄─────┤  ← 左转车辆（需要让行对向直行）
    │           │
```

仿真中需要检测：
1. 左转车辆到达路口
2. 对向有直行车辆接近
3. 左转车辆必须等待（除非有保护左转相位）

### 3.5 右转与行人冲突

右转车辆在红灯时可以右转（中国规则），但需要让行过街行人：

```
行人过街 ← ← ← ← ← ← ←
                │
                ▼ 右转车辆（需要让行行人）
```

---

## 4. 车辆行为模型

### 4.1 当前模型的问题

当前的车辆行为：
- 所有车以固定速度行驶
- 到路口停车，绿灯直接通过
- 没有加减速过程
- 没有跟车模型
- 没有变道

### 4.2 目标：跟车模型（Car-Following）

真实的车辆行为应该遵循跟车模型，最基本的如 **IDM（Intelligent Driver Model）**：

```python
def idm_acceleration(v, v0, s, dv, a=1.0, b=1.5, s0=2.0, T=1.5):
    """
    IDM acceleration function.
    
    v:   current speed
    v0:  desired speed
    s:   gap to leader
    dv:  speed difference to leader (v - v_leader)
    a:   maximum acceleration
    b:   comfortable deceleration
    s0:  minimum gap
    T:   safe time headway
    """
    s_star = s0 + v * T + v * dv / (2 * np.sqrt(a * b))
    accel = a * (1 - (v / v0)**4 - (s_star / s)**2)
    return accel
```

这会自然产生：
- 起步延迟（前车启动后后车逐步加速）
- 减速波（红灯前的减速传递）
- 排队增长/消散

### 4.3 目标：变道模型

多车道道路上，车辆需要变道：
- 电动自行车从非机动车道穿插到机动车道
- 公交出站后并入主车道
- 车辆为了左转提前变到左转道

### 4.4 行人行为模型

行人的行为比车辆复杂得多：
- **过街决策**：看到绿灯还剩几秒，决定冲还是等
- **犹豫行为**：走到一半红灯亮了，是跑过去还是退回来
- **群体效应**：一群人在等红灯，只要有一个人走了其他人跟着走
- **手机依赖**：低头看手机导致反应延迟

---

## 5. 交通需求模型

### 5.1 问题：当前是固定流量

现在的车辆生成是 `arrival_rate * dt` 的泊松过程，所有方向均匀分布。
真实世界的流量是：
- 早高峰 7:30-9:00 南→北多
- 晚高峰 17:30-19:00 北→南多
- 周末完全不同的模式
- 节假日、学校放学、大型活动

### 5.2 目标：时间变流量

```python
@dataclass
class TrafficDemandProfile:
    """Time-varying traffic demand."""
    name: str
    time_slots: list[TimeSlot]

@dataclass
class TimeSlot:
    """Traffic demand for a specific time window."""
    start_hour: float       # 0.0-24.0
    end_hour: float
    # Per-direction arrival rates (vehicles/second)
    rate_north: float
    rate_south: float
    rate_east: float
    rate_west: float
    # Vehicle mix ratios for this time slot
    mix_ratios: dict        # VehicleType -> ratio
```

### 5.3 预设场景

| 场景 | 特点 | LLM 需要应对的挑战 |
|------|------|-------------------|
| 早高峰 | 南→北潮汐，电动车多 | 识别潮汐方向，延长南→北绿灯 |
| 晚高峰 | 北→南潮汐，公交密集 | 公交优先，协调绿波 |
| 学校放学 | 行人激增，非机动车多 | 延长行人过街相位，注意二次过街 |
| 施工占道 | 车道变窄，通行能力下降 | 重新分配绿灯时间，引导分流 |
| 大型活动 | 突发大量人流和车流 | 紧急协调，可能需要交警介入 |

---

## 6. 交通事件与异常

### 6.1 事件类型

| 事件 | 影响 | LLM 应对 |
|------|------|---------|
| 🚑 紧急车辆通过 | 优先通行、其他方向红灯 | 立即切换相位 |
| 🚧 施工占道 | 车道变窄、通行能力下降 | 调整配时、提示分流 |
| 🚗 交通事故 | 道路部分或全部封闭 | 重新规划路由、延长绕行方向绿灯 |
| 🅿️ 违章停车 | 占用一条车道 | 识别并调整配时 |
| 🌧️ 恶劣天气 | 全体减速、刹车距离增加 | 延长黄灯时间、增加全红时间 |
| 🎉 大型活动 | 突发大量交通需求 | 协调多路口、开启特殊配时方案 |

### 6.2 事件触发机制

```python
@dataclass
class TrafficEvent:
    """A traffic event that affects the road network."""
    event_type: str      # "accident" | "construction" | "emergency" | "weather" | "event"
    location: str        # intersection_id or road segment id
    start_time: float
    duration: float      # seconds
    affected_lanes: list[int]  # which lanes are blocked
    severity: float      # 0.0-1.0 (0=minor, 1=critical)
    description: str     # human-readable description for LLM
```

---

## 7. Agent 感知信息设计

LLM Agent 需要足够的信息来做合理决策。以下是 Agent 每个决策周期应该看到的信息：

### 7.1 当前信息 vs 目标信息

| 信息维度 | 当前有 | 目标应有 |
|---------|--------|---------|
| 各方向排队长度 | ✅ | ✅ |
| 各方向等待时间 | ✅ | ✅ |
| 当前信号相位 | ✅ | ✅ |
| 紧急车辆 | ✅ | ✅ |
| 车辆类型构成 | ✅ 新增 | ✅ |
| **行人过街请求** | ❌ | ✅ |
| **左转排队长度** | ❌ | ✅ |
| **对向直行流量** | ❌ | ✅（左转决策需要） |
| **公交接近信号** | ❌ | ✅（公交优先） |
| **历史趋势** | ❌ | ✅（潮汐识别） |
| **事件通知** | ❌ | ✅（事故/施工） |
| **天气状况** | ❌ | ✅（影响速度） |
| **时段信息** | ❌ | ✅（高峰/平峰） |

### 7.2 LLM Prompt 信息模板（目标版本）

```
路口: ix_1_1 | 时间: 08:35:22 | 时段: 早高峰

## 各方向交通流
方向 | 直行排队 | 左转排队 | 行人等待 | 车辆类型构成
北   | 12辆     | 3辆      | 5人     | 汽车8, 电自5, 行人2
南   | 18辆     | 2辆      | 3人     | 汽车10, 电自8, 公交2
东   | 4辆      | 1辆      | 0人     | 汽车3, 电自1
西   | 6辆      | 0辆      | 2人     | 汽车4, 电自2

## 信号状态
当前相位: NS_LEFT（南北左转保护）已持续 12s/20s
下一相位: EW_GREEN

## 特殊事件
⚠️ 南方向 50m 处有公交车即将进站

## 建议
- 南方向排队最长（18辆 + 公交即将到站），考虑延长当前相位
- 北方向左转有 3 辆车，但当前相位已包含左转
- 东/西方向车流较少，可适当缩短其绿灯时间
```

---

## 8. 实现优先级

### Phase 3.x：混行交通 ✅（已完成）
- [x] 6 种交通参与者类型
- [x] 类型专属速度和物理属性
- [x] 信号遵守率差异化
- [x] LLM prompt 混行意识

### Phase 4.x：信号相位升级
- [ ] 多相位信号系统（直行/左转/行人）
- [ ] 行人过街请求机制
- [ ] 左转保护相位
- [ ] 感应式信号（基于排队长度动态调整）
- [ ] 公交优先信号

### Phase 5.x：路口几何
- [ ] 车道级建模（左转道/直行道/右转道）
- [ ] 左转冲突检测
- [ ] 右转与行人冲突
- [ ] 非机动车道建模
- [ ] 港湾式公交站台

### Phase 6.x：交通需求
- [ ] 时间变流量（早晚高峰潮汐）
- [ ] 多场景预设（早高峰/晚高峰/学校/活动）
- [ ] 车辆路径规划（OD 矩阵）
- [ ] 天气影响模型

### Phase 7.x：事件与异常
- [ ] 事故模拟
- [ ] 施工占道
- [ ] 恶劣天气
- [ ] 大型活动突发流量
- [ ] Agent 异常响应能力评估

---

## 9. 与现有系统的兼容性

### 9.1 向后兼容

- `SimulationConfig` 新增参数都有默认值，不影响现有用法
- `Vehicle` 的 `vehicle_type` 默认为 `CAR`，现有代码无需改动
- `IntersectionState.to_text()` 在没有 type breakdown 时正常工作
- LLM prompt 增加混行信息但不改变输出格式

### 9.2 渐进式增强

设计遵循"先能跑，再跑好"的原则：
1. 先加类型 → 再加行为 → 再加冲突
2. 先加相位 → 再加感应 → 再加协调
3. 先加直行 → 再加左转 → 再加行人

每个阶段独立可用，不需要全部实现才有价值。

---

## 附录：与 SUMO 的对比

| 维度 | 本项目（自研引擎） | SUMO |
|------|-------------------|------|
| 部署 | 零依赖，pip install | 需要 Java/Python + 配置文件 |
| 速度 | 轻量，实时 | 较重，离线仿真为主 |
| 精度 | 够用级，可定制 | 高精度，工业级 |
| 混行 | 自定义类型系统 | 内置行人/自行车支持 |
| 路网 | OSM 导入 | OSM/SUMO 格式 |
| 优势 | 灵活、LLM 友好 | 精确、生态成熟 |

**定位差异**：本项目不是要替代 SUMO，而是做一个 **LLM Agent 友好的轻量仿真器**。
SUMO 的精度是为交通工程设计的，我们的精度是为 LLM 决策设计的——
LLM 需要的是"足够真实的路况描述"，而不是"毫米级的物理仿真"。
