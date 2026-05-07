# 第9章 行人与非机动车信号设计

> **行人和非机动车不是交通的"配角"，他们是路口最脆弱的参与者。**

## 设计背景

当前信号系统只有"南北绿灯/东西绿灯"，没有行人相位。
但真实路口中：
- 行人需要专用的过街时间
- 电动自行车和行人可能同时过街（冲突）
- 宽路口需要二次过街
- 行人等待超时后会闯红灯

如果信号系统不给行人合法的过街时间，行人就会非法过街——
这不是行人的问题，是信号设计的问题。

---

## 1. 行人过街方式

### 1.1 三种过街模式

| 模式 | 描述 | 适用场景 | 信号设计 |
|------|------|---------|---------|
| **跟随机动车** | 行人和同向机动车同时绿灯 | 窄路口、低流量 | 无独立行人相位 |
| **独立行人相位** | 所有机动车红灯，行人绿灯 | 宽路口、高流量 | 全红 + 行人绿灯 |
| **分向行人相位** | 行人分方向过街 | 超宽路口、环岛 | 多个行人子相位 |

### 1.2 选择：跟随机动车 + 独立行人相位混合

**默认模式**：跟随机动车（Phase 1/3 时行人可过街）
**高流量时**：切换到独立行人相位（Phase 5）

触发条件：
- 某方向行人等待数 > 5 人
- 或行人等待时间 > 30 秒
- 或协调层指令

---

## 2. 行人信号相位设计

### 2.1 完整信号相位表

```
┌────────────────────────────────────────────────────────────────────┐
│                        信号相位定义                                 │
├──────┬──────────────┬────────────┬────────────┬────────────────────┤
│ 编号 │ 名称          │ 机动车     │ 行人       │ 持续时间           │
├──────┼──────────────┼────────────┼────────────┼────────────────────┤
│  0   │ NS_GREEN     │ 南北直行绿  │ 南北可过街  │ 30-60s (动态)      │
│  1   │ NS_YELLOW    │ 南北黄灯    │ 禁止过街    │ 3s                 │
│  2   │ ALL_RED_1    │ 全红       │ 禁止过街    │ 2s                 │
│  3   │ NS_LEFT      │ 南北左转绿  │ 禁止过街    │ 15-25s (动态)      │
│  4   │ NS_LEFT_YEL  │ 南北左转黄  │ 禁止过街    │ 3s                 │
│  5   │ ALL_RED_2    │ 全红       │ 禁止过街    │ 2s                 │
│  6   │ EW_GREEN     │ 东西直行绿  │ 东西可过街  │ 30-60s (动态)      │
│  7   │ EW_YELLOW    │ 东西黄灯    │ 禁止过街    │ 3s                 │
│  8   │ ALL_RED_3    │ 全红       │ 禁止过街    │ 2s                 │
│  9   │ EW_LEFT      │ 东西左转绿  │ 禁止过街    │ 15-25s (动态)      │
│ 10   │ EW_LEFT_YEL  │ 东西左转黄  │ 禁止过街    │ 3s                 │
│ 11   │ ALL_RED_4    │ 全红       │ 禁止过街    │ 2s                 │
│ 12   │ PED_ALL      │ 全红       │ 全向行人绿  │ 15-25s (按需)      │
│ 13   │ PED_ALL_YEL  │ 全红       │ 行人闪烁    │ 5s                 │
└──────┴──────────────┴────────────┴────────────┴────────────────────┘
```

### 2.2 行人过街时间计算

行人的过街时间不只是绿灯时间，还包括：
- **绿灯时间**：行人可以在绿灯期间开始过街
- **闪烁时间**：行人不应开始过街，但已经在过街的可以继续
- **清空时间**：行人必须在绿灯结束前到达安全岛或对岸

```python
def calculate_pedestrian_phase_time(
    crosswalk_width: float,       # 斑马线宽度 (m)
    crossing_distance: float,     # 过街距离 (m)
    pedestrian_speed: float = 1.2, # 行人速度 (m/s)，取保守值
    flashing_speed: float = 1.0,  # 闪烁时行人速度 (m/s)，老年人减速
) -> dict:
    """
    计算行人过街各阶段时间。
    
    规范要求：
    - 绿灯 = 过街距离 / 行人速度
    - 闪烁 = 最小 7 秒（提醒行人不要开始过街）
    - 清空 = 过街距离 / 闪烁速度（给已经在过街的行人时间）
    """
    green_time = crossing_distance / pedestrian_speed
    flashing_time = max(7.0, crossing_distance * 0.3)  # 至少 7 秒
    clearance_time = crossing_distance / flashing_speed
    
    return {
        "green": green_time,
        "flashing": flashing_time,
        "clearance": clearance_time,
        "total": green_time + flashing_time + clearance_time,
    }
```

### 2.3 二次过街

宽路口（超过 30 米）的行人可能一次过不完，需要**安全岛**二次过街：

```
┌──────────────────────────────────────────────┐
│                    北                         │
│  ┌─────┐                                    │
│  │     │  ← 安全岛 (refuge island)          │
│  │  🚶 │  ← 行人第一段过街                    │
│  │     │                                    │
│  └─────┘                                    │
│  ═══════════════════════════════  ← 车道      │
│  ┌─────┐                                    │
│  │     │                                    │
│  │  🚶 │  ← 行人第二段过街                    │
│  │     │                                    │
│  └─────┘                                    │
│                    南                         │
└──────────────────────────────────────────────┘
```

**二次过街策略**：
1. Phase 0 (NS_GREEN)：行人过第一段到安全岛
2. Phase 6 (EW_GREEN)：安全岛上的行人过第二段
3. 如果安全岛容量不足，使用独立行人相位 (Phase 12)

```python
@dataclass
class CrosswalkDesign:
    """斑马线设计。"""
    crosswalk_id: str
    direction: str           # "north_south" 或 "east_west"
    total_distance: float    # 总过街距离 (m)
    has_refuge_island: bool  # 是否有安全岛
    refuge_width: float      # 安全岛宽度 (m)，如有
    num_segments: int        # 过街段数（1=无安全岛，2=有安全岛）
    
    def get_phase_requirements(self) -> dict:
        """获取各相位的行人时间需求。"""
        if not self.has_refuge_island:
            # 一次性过街
            seg_dist = self.total_distance
            return {
                "green": seg_dist / 1.2,
                "flashing": max(7.0, seg_dist * 0.3),
                "clearance": seg_dist / 1.0,
            }
        else:
            # 二次过街
            seg_dist = (self.total_distance - self.refuge_width) / 2
            return {
                "segment_1_green": seg_dist / 1.2,
                "segment_1_flashing": max(7.0, seg_dist * 0.3),
                "segment_2_green": seg_dist / 1.2,
                "segment_2_flashing": max(7.0, seg_dist * 0.3),
            }
```

---

## 3. 行人请求机制

### 3.1 检测方式

| 方式 | 描述 | 准确性 | 成本 |
|------|------|--------|------|
| **按钮触发** | 行人按下过街按钮 | 高 | 低（硬件按钮） |
| **视频检测** | 摄像头检测等待行人 | 中 | 高（AI 推理） |
| **雷达检测** | 毫米波雷达检测 | 高 | 中 |
| **固定周期** | 每个周期都给行人相位 | 低 | 零 |

### 3.2 选择：按钮触发 + 视频检测混合

```
默认：按钮触发（低流量时）
高峰：视频检测自动触发（高流量时，按钮可能排队）
```

### 3.3 行人请求数据结构

```python
@dataclass
class PedestrianRequest:
    """行人过街请求。"""
    crosswalk_id: str        # 哪个斑马线
    direction: str           # "north" | "south" | "east" | "west"
    request_time: float      # 请求时间
    source: str              # "button" | "camera" | "radar"
    wait_time: float = 0.0   # 已等待时间
    count: int = 1           # 检测到的行人数
    
    @property
    def urgency(self) -> float:
        """紧急程度：0.0-1.0。"""
        # 等待时间越长越紧急
        time_factor = min(1.0, self.wait_time / 60.0)
        # 人数越多越紧急
        count_factor = min(1.0, self.count / 10.0)
        return (time_factor * 0.6 + count_factor * 0.4)
```

### 3.4 LLM 的行人决策

LLM Agent 需要根据行人请求决定是否切换到行人相位：

```python
PED_PROMPT_ADDON = """
## 行人过街信息
当前行人请求：
{pedestrian_requests}

行人过街规则：
1. 有行人请求时，应在当前相位结束后切换到行人相位
2. 行人等待超过 30 秒，应立即切换（即使会打断绿波）
3. 行人等待超过 60 秒，强制切换（防止闯红灯）
4. 高峰时段（7:30-9:00, 17:30-19:00）自动给行人相位
5. 老人/儿童较多的区域（学校、医院），增加行人相位时间

行人相位决策：
- 行人请求 urgent > 0.7：立即切换到 PED_ALL
- 行人请求 urgent > 0.4：当前相位结束后切换
- 行人请求 urgent < 0.4：等下一个周期
"""
```

---

## 4. 非机动车信号设计

### 4.1 电动自行车行为

电动自行车在真实路口的行为非常复杂：

| 行为 | 描述 | 频率 | 信号设计应对 |
|------|------|------|------------|
| **走非机动车道** | 正常行为 | 70% | 无需特殊处理 |
| **穿插机动车道** | 从非机动车道切入机动车道 | 15% | 绿灯尾部预留安全间隔 |
| **闯红灯** | 红灯时直接通过 | 10% | 缩短全红时间 |
| **逆行** | 逆向行驶 | 5% | 检测并警告 |
| **抢左转** | 左转时抢在机动车前面 | 常见 | 左转相位前加清空时间 |

### 4.2 非机动车道建模

```python
@dataclass
class NonMotorizedLane:
    """非机动车道。"""
    lane_id: str
    direction: str           # "north" | "south" | "east" | "west"
    side: str                # "left" | "right" — 在机动车道的哪一侧
    width: float             # 车道宽度 (m)
    has_separation: bool     # 是否有物理隔离（护栏/绿化带）
    connected_to_crosswalk: bool  # 是否连接到斑马线
    
    # 容量
    max_ebikes: int = 20     # 最大电动车数
    max_bicycles: int = 15   # 最大自行车数
```

### 4.3 非机动车过街

非机动车通常和行人一起过街，但速度更快：

```python
@dataclass
class NonMotorizedCrossing:
    """非机动车过街。"""
    crossing_id: str
    direction: str
    
    # 非机动车过街有两种方式：
    # 1. 走斑马线（和行人一起）
    # 2. 走独立的非机动车信号灯
    
    mode: str  # "shared_crosswalk" | "dedicated_signal"
    
    # 信号
    has_dedicated_signal: bool = False  # 是否有独立信号灯
    signal_head: str = ""               # 信号灯头 ID
    
    # 时间
    crossing_time: float = 0.0  # 计算得出
```

### 4.4 非机动车与行人冲突

当非机动车和行人共享过街通道时，会产生冲突：

```
行人 → → → → →
     ╲
      ╲  ← 非机动车（速度更快，穿插行人）
       → → → → →
```

**解决方案**：
1. **时空分离**：非机动车和行人不同时间过街
2. **空间分离**：非机动车走独立信号灯
3. **混合管理**：LLM 根据流量决定是否分离

```python
def decide_non_motorized_phase(
    ped_count: int,
    ebike_count: int,
    current_phase_duration: float,
) -> dict:
    """决定非机动车过街策略。"""
    
    total = ped_count + ebike_count
    
    if total == 0:
        return {"action": "none"}
    
    # 如果电动车多于行人，考虑分离
    if ebike_count > ped_count * 2 and ebike_count > 5:
        return {
            "action": "separate_phases",
            "reason": f"电动车 {ebike_count} 辆 >> 行人 {ped_count} 人，建议分离过街",
            "ebike_phase_first": True,  # 电动车先过，行人后过
        }
    
    # 如果行人多，混合过街但加长清空时间
    if ped_count > 5:
        return {
            "action": "extended_clearance",
            "reason": f"行人 {ped_count} 人较多，延长清空时间",
            "clearance_extension": 5.0,  # 额外 5 秒清空
        }
    
    # 默认混合过街
    return {"action": "shared_crosswalk"}
```

---

## 5. 行人闯红灯模型

### 5.1 为什么行人会闯红灯

行人闯红灯不是"素质问题"，是信号设计问题：

| 原因 | 占比 | 信号设计应对 |
|------|------|------------|
| 等待时间太长 | 40% | 缩短行人等待周期 |
| 没有合法过街机会 | 25% | 增加行人相位 |
| 看别人闯跟着闯 | 20% | 群体效应建模 |
| 绿灯时间不够过街 | 10% | 延长绿灯/增加清空 |
| 注意力不集中 | 5% | 警示装置 |

### 5.2 闯红灯概率模型

```python
def jaywalking_probability(
    wait_time: float,          # 已等待时间 (s)
    ped_count: int,            # 周围行人数
    signal_remaining: float,   # 红灯剩余时间 (s)
    crossing_distance: float,  # 过街距离 (m)
    has_refuge: bool,          # 是否有安全岛
) -> float:
    """
    计算行人闯红灯概率。
    
    基于以下因素：
    1. 等待时间越长，越可能闯红灯
    2. 周围人越多，群体效应越强
    3. 红灯剩余时间越短，越可能等待
    4. 过街距离越短，越容易闯
    """
    # 等待时间因素（30 秒后概率显著上升）
    wait_factor = min(1.0, max(0, (wait_time - 15) / 45))
    
    # 群体效应（3人以上开始有群体效应）
    group_factor = min(1.0, max(0, (ped_count - 2) / 8))
    
    # 红灯剩余时间因素（剩余 < 10 秒时更愿意等）
    remaining_factor = max(0, 1.0 - signal_remaining / 20.0)
    
    # 过街距离因素（距离短更容易闯）
    distance_factor = max(0, 1.0 - crossing_distance / 30.0)
    
    # 安全岛因素（有安全岛更容易闯，因为只需过一半）
    refuge_factor = 0.2 if has_refuge else 0.0
    
    # 综合概率
    prob = (
        wait_factor * 0.35 +
        group_factor * 0.25 +
        remaining_factor * 0.15 +
        distance_factor * 0.15 +
        refuge_factor * 0.10
    )
    
    return min(1.0, max(0.0, prob))
```

### 5.3 信号设计对闯红灯的抑制

好的信号设计应该让行人**不需要**闯红灯：

```python
def signal_design_score(
    ped_phase_frequency: float,  # 行人相位频率（次/小时）
    avg_wait: float,             # 平均等待时间 (s)
    crossing_time: float,        # 过街时间 (s)
    has_refuge: bool,            # 是否有安全岛
) -> float:
    """
    评估信号设计对行人友好的程度。
    返回 0.0-1.0，越高越好。
    """
    # 行人相位频率（每小时至少 4 次）
    freq_score = min(1.0, ped_phase_frequency / 4.0)
    
    # 平均等待时间（< 30 秒为好）
    wait_score = max(0, 1.0 - avg_wait / 60.0)
    
    # 过街时间充足性（绿灯 > 过街时间 × 1.2）
    time_score = 1.0 if crossing_time * 1.2 < 30 else 0.5
    
    # 安全岛
    refuge_score = 1.0 if has_refuge else 0.7
    
    return (freq_score * 0.3 + wait_score * 0.3 +
            time_score * 0.2 + refuge_score * 0.2)
```

---

## 6. 行人安全间隔设计

### 6.1 问题：绿灯尾部的安全风险

当南北绿灯即将结束时，行人可能还在过街。
此时如果东西方向开始绿灯，转弯车辆会和行人冲突。

```
时间线：
  NS_GREEN (剩余 3s)  │  ALL_RED (2s)  │  EW_GREEN
  行人还在过街 ←──────│                │  车辆启动
                      │  清空时间       │
```

### 6.2 安全间隔设计

```python
@dataclass
class SafetyInterval:
    """行人安全间隔。"""
    
    # 全红清空时间（行人完全通过所需时间）
    all_red_clearance: float = 3.0  # 秒
    
    # 行人绿灯闪烁开始时间
    flashing_start: float = 7.0  # 绿灯结束前 7 秒开始闪烁
    
    # 行人清空时间（闪烁结束后）
    pedestrian_clearance: float = 5.0  # 秒
    
    # 左转车辆让行行人的时间
    left_turn_yield_time: float = 3.0  # 秒
    
    def get_total_clearance(self, crossing_distance: float) -> float:
        """计算总清空时间。"""
        # 清空时间 = 过街距离 / 行人速度
        ped_clearance = crossing_distance / 1.0  # 取保守速度 1.0 m/s
        return max(self.all_red_clearance, ped_clearance)
```

### 6.3 右转车辆让行行人

在中国，右转车辆在红灯时可以右转，但必须让行过街行人：

```python
def right_turn_yield_check(
    has_pedestrian: bool,
    ped_position: float,  # 行人在斑马线上的位置 (m)
    vehicle_speed: float,  # 车辆速度 (m/s)
    crossing_distance: float,
) -> bool:
    """
    判断右转车辆是否需要让行行人。
    
    规则：如果行人已经在过街（位置 > 0），车辆必须让行。
    """
    if not has_pedestrian:
        return False
    
    # 行人已经进入斑马线
    if ped_position > 0 and ped_position < crossing_distance:
        return True
    
    return False
```

---

## 7. Agent 的行人感知

LLM Agent 每个决策周期需要看到行人和非机动车信息：

```python
@dataclass
class PedestrianState:
    """路口行人状态。"""
    
    # 各方向等待行人
    waiting_north: int = 0
    waiting_south: int = 0
    waiting_east: int = 0
    waiting_west: int = 0
    
    # 行人等待时间
    wait_time_north: float = 0.0
    wait_time_south: float = 0.0
    wait_time_east: float = 0.0
    wait_time_west: float = 0.0
    
    # 行人请求
    requests: list[PedestrianRequest] = field(default_factory=list)
    
    # 非机动车
    ebike_waiting: int = 0
    bicycle_waiting: int = 0
    
    # 过街中的行人
    crossing_north_south: int = 0
    crossing_east_west: int = 0
    
    def to_text(self) -> str:
        """格式化为 LLM 可读文本。"""
        parts = []
        
        # 等待行人
        total_waiting = (self.waiting_north + self.waiting_south +
                        self.waiting_east + self.waiting_west)
        if total_waiting > 0:
            parts.append(f"等待过街行人: 北{self.waiting_north} 南{self.waiting_south} "
                        f"东{self.waiting_east} 西{self.waiting_west}")
            
            # 等待时间
            max_wait = max(self.wait_time_north, self.wait_time_south,
                          self.wait_time_east, self.wait_time_west)
            if max_wait > 30:
                parts.append(f"⚠️ 行人最长等待 {max_wait:.0f}s，应立即给行人相位")
        
        # 非机动车
        total_nm = self.ebike_waiting + self.bicycle_waiting
        if total_nm > 0:
            parts.append(f"非机动车等待: 电动车{self.ebike_waiting} 自行车{self.bicycle_waiting}")
        
        # 过街中
        total_crossing = self.crossing_north_south + self.crossing_east_west
        if total_crossing > 0:
            parts.append(f"正在过街: {total_crossing} 人")
        
        return "\n".join(parts) if parts else "无行人/非机动车"
```

---

## 8. 实现优先级

| 优先级 | 功能 | 依赖 |
|--------|------|------|
| P0 | 行人跟随机动车过街（Phase 0/6 时可过街） | 无 |
| P0 | 行人请求机制（按钮/检测） | 硬件或模拟 |
| P0 | 行人等待超时强制切换 | 信号控制器 |
| P1 | 独立行人相位（Phase 12） | P0 |
| P1 | 二次过街（安全岛） | 路口几何 |
| P1 | 行人安全间隔（全红清空） | P0 |
| P2 | 非机动车独立信号 | P1 |
| P2 | 闯红灯概率模型 | P0 |
| P2 | 右转让行行人 | P1 |
| P3 | 行人检测（视频/雷达） | 硬件 |
