# 第12章 公交优先设计

> **一辆公交车载 50 人，一辆私家车载 1.5 人。信号灯面前，公交车应该被优先对待。**

## 设计背景

公交优先（Transit Signal Priority, TSP）是智能交通系统的核心功能之一。
一辆满载的公交车相当于 30-40 辆私家车的客运量。
如果信号灯能让公交车少等 10 秒，50 个乘客就节省了 500 秒（8.3 分钟）。

---

## 1. 公交优先策略

### 1.1 三种策略

| 策略 | 描述 | 响应时间 | 对其他车辆影响 |
|------|------|---------|-------------|
| **绿灯延长** | 当前是绿灯时，延长几秒让公交通过 | 低 | 小（只延长） |
| **红灯早断** | 当前是红灯时，提前切换到绿灯 | 中 | 中（提前切换） |
| **插入公交相位** | 在现有相位序列中插入公交专用相位 | 高 | 大（额外相位） |

### 1.2 策略选择

```python
from enum import Enum

class TransitPriorityStrategy(str, Enum):
    EXTEND_GREEN = "extend_green"         # 绿灯延长
    EARLY_GREEN = "early_green"           # 红灯早断
    INSERT_TRANSIT_PHASE = "insert_transit"  # 插入公交相位
    PASSIVE_PRIORITY = "passive_priority"  # 被动优先（固定配时优化）


def choose_transit_strategy(
    current_phase: str,
    transit_approach: str,
    transit_distance: float,       # 公交距离路口的距离 (m)
    transit_speed: float,          # 公交速度 (m/s)
    phase_remaining: float,        # 当前相位剩余时间 (s)
    green_remaining: float,        # 绿灯剩余时间 (s),
    queue_length: int,             # 排队长度
) -> TransitPriorityStrategy:
    """
    选择公交优先策略。
    
    决策逻辑：
    1. 如果公交方向当前是绿灯 → 延长绿灯
    2. 如果公交方向当前是红灯，但绿灯快到了 → 红灯早断
    3. 如果公交方向当前是红灯，绿灯还很远 → 插入公交相位
    """
    time_to_arrival = transit_distance / max(transit_speed, 1.0)
    
    # 公交方向是绿灯
    if is_green_for_approach(current_phase, transit_approach):
        if green_remaining < time_to_arrival + 5:
            # 绿灯不够公交通过，需要延长
            return TransitPriorityStrategy.EXTEND_GREEN
        else:
            # 绿灯足够，不需要干预
            return TransitPriorityStrategy.PASSIVE_PRIORITY
    
    # 公交方向是红灯
    else:
        time_until_green = calculate_time_until_green(
            current_phase, transit_approach
        )
        
        # 红灯快结束了，提前切绿灯
        if time_until_green < time_to_arrival + 10:
            return TransitPriorityStrategy.EARLY_GREEN
        
        # 红灯还很久，插入公交相位
        if time_until_green > time_to_arrival + 30:
            return TransitPriorityStrategy.INSERT_TRANSIT_PHASE
        
        # 中等情况，红灯早断
        return TransitPriorityStrategy.EARLY_GREEN
```

---

## 2. 公交检测

### 2.1 检测方式

| 方式 | 数据源 | 延迟 | 精度 | 成本 |
|------|--------|------|------|------|
| **AVL/GPS** | 公交调度系统 | 低 | 高 | 低（已有系统） |
| **RFID** | 路侧读卡器 | 极低 | 极高 | 中 |
| **视频检测** | 路口摄像头 | 中 | 中 | 高 |
| **地磁检测** | 埋设传感器 | 低 | 高 | 高 |
| **V2X** | 车路协同 | 极低 | 极高 | 很高 |

### 2.2 推荐方案：AVL/GPS 为主

大多数城市公交系统已有 GPS 定位和调度系统。
利用现有数据，不需要额外硬件。

```python
@dataclass
class TransitVehicle:
    """公交车辆。"""
    vehicle_id: str
    route_id: str              # 线路编号
    direction: str             # 行驶方向
    speed: float               # 当前速度 (m/s)
    distance_to_intersection: float  # 距路口距离 (m)
    occupancy: int             # 载客数
    capacity: int              # 车辆容量
    is_emergency: bool         # 是否是急救/消防
    
    # 时刻表信息
    scheduled_arrival: float   # 计划到达时间
    actual_arrival: float      # 实际到达时间（预测）
    is_late: bool              # 是否晚点
    delay_minutes: float       # 晚点分钟数
    
    @property
    def priority_score(self) -> float:
        """
        公交优先级评分。
        
        考虑因素：
        1. 晚点程度（越晚越优先）
        2. 载客量（越满越优先）
        3. 是否紧急车辆
        """
        score = 0.0
        
        # 晚点因素（晚点 > 5 分钟开始加分）
        if self.is_late:
            score += min(1.0, self.delay_minutes / 10.0) * 0.5
        
        # 载客量因素
        occupancy_ratio = self.occupancy / max(self.capacity, 1)
        score += occupancy_ratio * 0.3
        
        # 紧急车辆
        if self.is_emergency:
            score += 1.0
        
        return min(1.0, score)


@dataclass
class TransitDetection:
    """公交检测器。"""
    
    def detect_transit_vehicles(
        self,
        approach: str,
        detection_range: float = 200.0,  # 检测范围 200 米
    ) -> list[TransitVehicle]:
        """
        检测接近路口的公交车辆。
        
        数据源：公交调度系统的 GPS 数据
        """
        # 从公交调度 API 获取附近公交
        transit_vehicles = fetch_transit_gps(approach, detection_range)
        
        return [
            tv for tv in transit_vehicles
            if tv.distance_to_intersection <= detection_range
        ]
    
    def detect_bus_stops(
        self,
        intersection_id: str,
        stop_range: float = 100.0,
    ) -> list[dict]:
        """
        检测路口附近的公交站台。
        
        公交站台在路口上游时，公交停靠会影响路口通行。
        """
        stops = fetch_bus_stops(intersection_id)
        return [s for s in stops if s["distance"] <= stop_range]
```

---

## 3. 公交优先信号控制

### 3.1 绿灯延长

```python
def extend_green_for_transit(
    current_phase: str,
    green_elapsed: float,
    green_max: float,
    transit_distance: float,
    transit_speed: float,
) -> dict:
    """
    为公交延长绿灯。
    
    延长时间 = max(0, 公交到达时间 - 绿灯剩余时间 + 安全余量)
    """
    time_to_arrival = transit_distance / max(transit_speed, 1.0)
    green_remaining = green_max - green_elapsed
    safety_margin = 5.0  # 安全余量 5 秒
    
    if time_to_arrival > green_remaining:
        # 需要延长
        extend_time = time_to_arrival - green_remaining + safety_margin
        extend_time = min(extend_time, 20.0)  # 最多延长 20 秒
        
        return {
            "action": "extend_green",
            "phase": current_phase,
            "extension": extend_time,
            "reason": f"公交 {transit_distance:.0f}m 处，预计 {time_to_arrival:.0f}s 到达，延长绿灯 {extend_time:.0f}s",
        }
    
    return {"action": "none"}
```

### 3.2 红灯早断

```python
def early_green_for_transit(
    current_phase: str,
    phase_remaining: float,
    transit_distance: float,
    transit_speed: float,
) -> dict:
    """
    为公交提前切换到绿灯。
    
    原理：缩短当前红灯的剩余时间，让公交方向提前获得绿灯。
    """
    time_to_arrival = transit_distance / max(transit_speed, 1.0)
    
    # 公交到达前需要绿灯
    # 所以当前相位需要在 time_to_arrival 秒内结束
    if phase_remaining > time_to_arrival:
        # 需要提前结束当前相位
        cut_time = phase_remaining - time_to_arrival + 5.0  # 5 秒安全余量
        cut_time = min(cut_time, phase_remaining * 0.5)  # 最多缩短 50%
        
        return {
            "action": "early_green",
            "cut_duration": cut_time,
            "reason": f"公交 {transit_distance:.0f}m 处，提前 {cut_time:.0f}s 切换相位",
        }
    
    return {"action": "none"}
```

### 3.3 插入公交相位

```python
def insert_transit_phase(
    current_phase: str,
    transit_approach: str,
    phase_remaining: float,
    transit_queue: int,
) -> dict:
    """
    插入公交专用相位。
    
    在当前相位结束后，插入一个短的公交相位，
    让公交和同向车辆优先通过。
    """
    # 插入条件：公交排队 >= 3 辆，或有高优先级公交
    if transit_queue < 3:
        return {"action": "none"}
    
    return {
        "action": "insert_phase",
        "phase_name": f"TRANSIT_{transit_approach.upper()}",
        "duration": min(20, 10 + transit_queue * 2),  # 10-20 秒
        "reason": f"公交方向排队 {transit_queue} 辆，插入公交优先相位",
    }
```

---

## 4. 公交站台与路口协调

### 4.1 站台位置分类

```
上游站台（路口前）：              下游站台（路口后）：
                                  
  🚌 ← 公交停靠                  ──────→  🚌 ← 公交停靠
  │                              │
  ↓                              ↓
  🚦 路口                        🚦 路口
```

### 4.2 上游站台影响

公交在上游站台停靠后，需要重新加速进入路口：
- 公交出站后速度低（0-20 km/h）
- 需要更多绿灯时间通过路口
- 可能和后方车辆产生速度差

```python
@dataclass
class BusStopImpact:
    """公交站台对路口的影响。"""
    stop_id: str
    distance_to_intersection: float  # 距路口距离 (m)
    is_upstream: bool               # 是否在上游
    
    # 站台参数
    dwell_time: float = 15.0        # 停靠时间 (s)
    acceleration_time: float = 8.0  # 出站加速时间 (s)
    
    def get_green_extension(self) -> float:
        """需要额外的绿灯时间。"""
        if not self.is_upstream:
            return 0.0
        # 公交出站后需要额外时间通过路口
        return self.acceleration_time + 3.0  # 加速时间 + 安全余量
```

### 4.3 港湾式站台

```
普通站台（占用车道）：          港湾式站台（不占用车道）：
                                
  ═══════════════             ═══════════════
  ║ 🚌 ║ 直行车 ║             ║  直行   ║
  ═══════════════             ═══╗    ╔═══
                                ║ 🚌 ║  ← 港湾
                                ═══╝    ╚═══
```

港湾式站台对路口通行的影响更小，公交停靠时不占用直行车道。

---

## 5. 公交优先与行人优先冲突

### 5.1 冲突场景

| 场景 | 公交需求 | 行人需求 | 冲突 |
|------|---------|---------|------|
| 公交同向有行人过街 | 公交通过 | 行人过街 | 可能冲突 |
| 公交转弯有行人过街 | 公交转弯 | 行人过街 | 必然冲突 |
| 公交优先 vs 行人等待超时 | 公交延迟 | 行人强制过街 | 优先级冲突 |

### 5.2 优先级规则

```python
def resolve_transit_pedestrian_conflict(
    transit_priority: float,      # 公交优先级 (0-1)
    ped_wait_time: float,         # 行人等待时间 (s)
    ped_count: int,               # 行人数
    transit_occupancy: int,       # 公交载客数
) -> str:
    """
    解决公交优先和行人优先的冲突。
    
    优先级规则：
    1. 行人等待 > 60 秒：行人优先（防止闯红灯）
    2. 公交载客 > 30 且行人等待 < 30 秒：公交优先
    3. 其他情况：行人优先（安全第一）
    """
    if ped_wait_time > 60:
        return "pedestrian_priority"  # 行人等待太久
    
    if transit_occupancy > 30 and ped_wait_time < 30:
        return "transit_priority"  # 大客流公交优先
    
    return "pedestrian_priority"  # 默认行人优先
```

---

## 6. LLM 的公交优先决策

```python
TRANSIT_PRIORITY_PROMPT = """
## 公交优先信息
接近路口的公交：
{transit_vehicles}

公交站台：
{bus_stops}

当前信号状态：{current_phase}

## 公交优先规则
1. **晚点公交优先**: 晚点 > 5 分钟的公交优先通过
2. **大载客优先**: 载客 > 30 人的公交优先
3. **绿灯延长**: 公交方向绿灯快结束时，延长绿灯
4. **红灯早断**: 公交方向红灯时，提前切绿灯
5. **站台协调**: 上游站台刚出站的公交，给予额外绿灯时间
6. **公交转弯**: 公交转弯时，延长清空时间（公交车身长）

## 冲突处理
- 公交优先 vs 行人等待超时 → 行人优先
- 公交优先 vs 绿波 → 公交优先（乘客多）
- 多辆公交同时到达 → 按优先级评分排序

## 输出格式
{{
    "transit_priority_decision": "extend" | "early_green" | "insert_phase" | "none",
    "priority_vehicle": "<公交ID>",
    "duration": <秒数>,
    "reasoning": "<决策理由>"
}}
"""
```

---

## 7. 公交优先评估指标

| 指标 | 定义 | 目标 |
|------|------|------|
| 公交平均延误 | 公交通过路口的平均额外等待时间 | < 10 秒 |
| 公交准点率 | 公交按时刻表到达的比例 | > 90% |
| 公交乘客总延误 | 所有公交乘客的总等待时间节省 | > 500 人·秒/小时 |
| 公交优先成功率 | 实际获得优先的公交比例 | > 80% |
| 对社会车辆影响 | 社会车辆额外等待时间 | < 5 秒 |
| 公交与行人冲突 | 公交优先导致的行人冲突次数 | 0 |

---

## 8. 实现优先级

| 优先级 | 功能 | 工作量 |
|--------|------|--------|
| P0 | 公交检测（GPS 数据接入） | 1 天 |
| P0 | 绿灯延长策略 | 0.5 天 |
| P1 | 红灯早断策略 | 0.5 天 |
| P1 | 公交优先级评分 | 0.5 天 |
| P1 | 公交优先与行人冲突处理 | 0.5 天 |
| P2 | 插入公交相位 | 1 天 |
| P2 | 公交站台协调 | 1 天 |
| P3 | V2X 公交检测（未来） | - |
