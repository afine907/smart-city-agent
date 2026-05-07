# 第13章 潮汐与时段设计

> **城市交通有呼吸——早高峰南→北，晚高峰北→南，深夜几乎没人。**

## 设计背景

真实城市的交通流量有明显的时间规律：
- **早高峰**（7:30-9:00）：住宅区→工作区，单向流量大
- **晚高峰**（17:30-19:00）：工作区→住宅区，反向流量大
- **平峰**（9:00-17:00）：双向流量较均衡
- **夜间**（22:00-6:00）：流量极低，可以全绿灯或黄闪

如果信号配时不随时间调整，早高峰时南→北方向的车会排长队，
而北→南方向的绿灯时间被浪费。

---

## 1. 时段划分

### 1.1 标准时段表

```python
from enum import Enum
from dataclasses import dataclass

class TimePeriod(str, Enum):
    """时段类型。"""
    EARLY_MORNING = "early_morning"   # 凌晨 0:00-6:00
    MORNING_RUSH = "morning_rush"     # 早高峰 7:30-9:00
    MIDDAY = "midday"                 # 平峰 9:00-17:00
    EVENING_RUSH = "evening_rush"     # 晚高峰 17:30-19:00
    EVENING = "evening"               # 晚间 19:00-22:00
    LATE_NIGHT = "late_night"         # 深夜 22:00-0:00


@dataclass
class TimePeriodConfig:
    """时段配置。"""
    period: TimePeriod
    start_hour: float       # 开始时间（24小时制）
    end_hour: float         # 结束时间
    
    # 流量系数（相对于基准流量的比例）
    volume_factor: float
    
    # 方向系数（>1 表示该方向流量大）
    direction_factors: dict[str, float]  # {"north": 1.5, "south": 0.7}
    
    # 信号配时调整
    cycle_time_factor: float = 1.0   # 周期系数
    green_ratio_adjust: float = 0.0  # 绿灯比例调整


# 标准时段配置
DEFAULT_PERIODS = [
    TimePeriodConfig(
        period=TimePeriod.EARLY_MORNING,
        start_hour=0.0, end_hour=6.0,
        volume_factor=0.2,
        direction_factors={"north": 1.0, "south": 1.0, "east": 1.0, "west": 1.0},
        cycle_time_factor=0.7,  # 周期缩短 30%
    ),
    TimePeriodConfig(
        period=TimePeriod.MORNING_RUSH,
        start_hour=7.5, end_hour=9.0,
        volume_factor=1.8,
        direction_factors={"north": 1.5, "south": 0.7, "east": 1.2, "west": 0.8},
        cycle_time_factor=1.2,  # 周期延长 20%
    ),
    TimePeriodConfig(
        period=TimePeriod.MIDDAY,
        start_hour=9.0, end_hour=17.0,
        volume_factor=1.0,
        direction_factors={"north": 1.0, "south": 1.0, "east": 1.0, "west": 1.0},
        cycle_time_factor=1.0,
    ),
    TimePeriodConfig(
        period=TimePeriod.EVENING_RUSH,
        start_hour=17.5, end_hour=19.0,
        volume_factor=1.8,
        direction_factors={"north": 0.7, "south": 1.5, "east": 0.8, "west": 1.2},
        cycle_time_factor=1.2,
    ),
    TimePeriodConfig(
        period=TimePeriod.EVENING,
        start_hour=19.0, end_hour=22.0,
        volume_factor=0.6,
        direction_factors={"north": 1.0, "south": 1.0, "east": 1.0, "west": 1.0},
        cycle_time_factor=0.9,
    ),
    TimePeriodConfig(
        period=TimePeriod.LATE_NIGHT,
        start_hour=22.0, end_hour=0.0,
        volume_factor=0.15,
        direction_factors={"north": 1.0, "south": 1.0, "east": 1.0, "west": 1.0},
        cycle_time_factor=0.5,
    ),
]
```

### 1.2 时段切换逻辑

```python
def get_current_period(hour: float, minute: float) -> TimePeriodConfig:
    """获取当前时段配置。"""
    time_decimal = hour + minute / 60.0
    
    for period in DEFAULT_PERIODS:
        if period.start_hour <= time_decimal < period.end_hour:
            return period
    
    return DEFAULT_PERIODS[0]  # 默认凌晨


def get_period_transition(
    current_period: TimePeriodConfig,
    next_period: TimePeriodConfig,
    transition_duration: float = 300.0,  # 5 分钟过渡
) -> dict:
    """
    计算时段切换的过渡参数。
    
    不是瞬间切换，而是渐变过渡。
    """
    return {
        "from_period": current_period.period.value,
        "to_period": next_period.period.value,
        "transition_duration": transition_duration,
        "description": f"从 {current_period.period.value} 过渡到 {next_period.period.value}，渐变 {transition_duration/60:.0f} 分钟",
    }
```

---

## 2. 潮汐方向检测

### 2.1 什么是潮汐

潮汐（Tidal Flow）：交通流在不同时段有明显的方向性差异。

```
早高峰（7:30-9:00）：
  住宅区 ─────→ → → → → → 工作区
  南 (大量车流) ──→ 北 (少量车流)

晚高峰（17:30-19:00）：
  工作区 ← ← ← ← ← ← 住宅区
  北 (大量车流) ←── 南 (少量车流)
```

### 2.2 潮汐检测

```python
@dataclass
class TidalFlowState:
    """潮汐状态。"""
    dominant_direction: str     # 主方向（流量大的方向）
    tidal_ratio: float          # 潮汐比（主方向/反方向）
    confidence: float           # 置信度
    detection_method: str       # "time_based" | "real_time" | "historical"
    
    @property
    def is_tidal(self) -> bool:
        """是否处于潮汐状态。"""
        return self.tidal_ratio > 1.5 and self.confidence > 0.7


class TidalFlowDetector:
    """潮汐检测器。"""
    
    def detect(
        self,
        hour: float,
        real_time_data: dict = None,
        historical_data: dict = None,
    ) -> TidalFlowState:
        """
        检测潮汐方向。
        
        三种检测方式：
        1. 基于时间：使用预设时段表
        2. 基于实时数据：检测实际流量方向
        3. 基于历史数据：学习历史规律
        """
        # 方式1: 基于时间
        period = get_current_period(hour, 0)
        time_based_direction = self._get_dominant_from_period(period)
        
        # 方式2: 基于实时数据（如果有）
        if real_time_data:
            rt_direction = self._get_dominant_from_realtime(real_time_data)
            rt_ratio = self._calculate_tidal_ratio(real_time_data)
        else:
            rt_direction = time_based_direction
            rt_ratio = 1.0
        
        # 方式3: 基于历史数据（如果有）
        if historical_data:
            hist_direction = self._get_dominant_from_history(historical_data, hour)
        else:
            hist_direction = time_based_direction
        
        # 综合判断
        final_direction = self._consensus(
            time_based_direction, rt_direction, hist_direction
        )
        
        return TidalFlowState(
            dominant_direction=final_direction,
            tidal_ratio=rt_ratio,
            confidence=0.8 if real_time_data else 0.5,
            detection_method="real_time" if real_time_data else "time_based",
        )
    
    def _get_dominant_from_period(self, period: TimePeriodConfig) -> str:
        """从时段配置获取主方向。"""
        factors = period.direction_factors
        return max(factors, key=factors.get)
    
    def _get_dominant_from_realtime(self, data: dict) -> str:
        """从实时数据获取主方向。"""
        directions = {"north": 0, "south": 0, "east": 0, "west": 0}
        for vehicle in data.get("vehicles", []):
            direction = vehicle.get("direction", "")
            if direction in directions:
                directions[direction] += 1
        return max(directions, key=directions.get)
    
    def _consensus(self, *directions) -> str:
        """多数投票。"""
        from collections import Counter
        counter = Counter(directions)
        return counter.most_common(1)[0][0]
```

---

## 3. 潮汐信号调整

### 3.1 潮汐配时方案

```python
@dataclass
class TidalSignalPlan:
    """潮汐信号方案。"""
    
    # 基准配时
    base_cycle: float = 90.0           # 基准周期 (s)
    base_green_ratio: float = 0.45     # 基准绿灯比例
    
    # 潮汐调整
    dominant_extension: float = 15.0   # 主方向额外绿灯 (s)
    recessive_reduction: float = 10.0  # 反方向减少绿灯 (s)
    
    # 过渡期
    transition_duration: float = 300.0  # 过渡期 (s)
    
    def calculate_for_period(
        self,
        period: TimePeriodConfig,
        tidal: TidalFlowState,
    ) -> dict:
        """计算某个时段的配时。"""
        cycle = self.base_cycle * period.cycle_time_factor
        
        if tidal.is_tidal:
            # 潮汐模式：主方向多给绿灯
            dominant_green = (
                cycle * self.base_green_ratio +
                self.dominant_extension * tidal.tidal_ratio
            )
            recessive_green = (
                cycle * self.base_green_ratio -
                self.recessive_reduction
            )
        else:
            # 均衡模式：平均分配
            dominant_green = cycle * self.base_green_ratio
            recessive_green = cycle * self.base_green_ratio
        
        return {
            "cycle_time": cycle,
            "dominant_direction": tidal.dominant_direction,
            "dominant_green": dominant_green,
            "recessive_green": recessive_green,
            "yellow": 3.0,
            "all_red": 2.0,
        }
```

### 3.2 可变车道

在严重潮汐的路段，可以设置可变车道：

```
早高峰（南→北为主）：
  ← 北行 ← 北行 ← 北行 ← 北行 ←  （4 车道北行）
  → 南行 →                              （1 车道南行）

晚高峰（北→南为主）：
  ← 北行 ←                              （1 车道北行）
  → 南行 → 南行 → 南行 → 南行 →        （4 车道南行）
```

可变车道需要：
- 车道指示器（箭头灯）
- 物理隔离（可移动护栏）
- 信号控制（与路口信号协调）

```python
@dataclass
class VariableLane:
    """可变车道。"""
    lane_id: str
    position: int            # 车道位置
    current_direction: str   # 当前方向
    is_variable: bool = True
    
    def switch_direction(self, new_direction: str) -> dict:
        """切换车道方向。"""
        # 需要清空车道上的车辆
        return {
            "action": "switch_lane_direction",
            "from": self.current_direction,
            "to": new_direction,
            "clearance_time": 15.0,  # 清空时间 15 秒
            "warning_flash": True,   # 闪烁警告
        }
```

---

## 4. LLM 的时段感知

### 4.1 增强版 Prompt

```python
TIME_OF_DAY_PROMPT = """
## 时段与潮汐信息
当前时段：{current_period}
时段特征：{period_description}
流量系数：{volume_factor}x
潮汐方向：{tidal_direction}
潮汐比：{tidal_ratio}

## 时段特殊规则
{period_specific_rules}

## 建议
- 当前是 {current_period}，主方向 {tidal_direction} 流量较大
- 建议给 {tidal_direction} 方向更多绿灯时间
- 流量系数 {volume_factor}x，周期应相应调整
"""

PERIOD_RULES = {
    TimePeriod.EARLY_MORNING: """
- 深夜时段，流量极低
- 可以使用短周期或黄闪模式
- 优先保证行人安全（如有行人）
- 如果连续 3 个周期无车，切换到黄闪
""",
    TimePeriod.MORNING_RUSH: """
- 早高峰时段
- 住宅区→工作区方向流量大
- 适当延长周期（+20%）
- 主方向绿灯比例增加到 55-60%
- 紧急车辆较多（救护车、消防车）
""",
    TimePeriod.MIDDAY: """
- 平峰时段
- 双向流量较均衡
- 标准周期和配时
- 公交优先效果最好（流量适中）
""",
    TimePeriod.EVENING_RUSH: """
- 晚高峰时段
- 工作区→住宅区方向流量大（与早高峰相反）
- 适当延长周期（+20%）
- 注意行人过街需求增加（下班回家）
""",
    TimePeriod.EVENING: """
- 晚间时段
- 流量逐渐降低
- 可以适当缩短周期
- 注意夜行人安全
""",
    TimePeriod.LATE_NIGHT: """
- 深夜时段
- 流量极低
- 建议黄闪模式或全绿灯
- 如果有行人按钮请求，临时给绿灯
""",
}
```

---

## 5. 特殊时段

### 5.1 节假日

```python
HOLIDAY_ADJUSTMENTS = {
    "春节": {"volume_factor": 0.3, "note": "城市空城"},
    "国庆": {"volume_factor": 0.5, "note": "部分区域拥堵"},
    "工作日": {"volume_factor": 1.0, "note": "正常"},
    "周末": {"volume_factor": 0.7, "note": "无早高峰"},
}
```

### 5.2 特殊事件

```python
@dataclass
class SpecialEvent:
    """特殊事件（演唱会、球赛、大型活动）。"""
    event_id: str
    event_type: str        # "concert" | "sports" | "exhibition" | "protest"
    location: str          # 路口 ID
    start_time: float
    end_time: float
    expected_attendance: int
    
    # 对交通的影响
    affected_intersections: list[str]
    pre_event_surge: float   # 活动前 1 小时流量倍数
    post_event_surge: float  # 活动后 1 小时流量倍数
    
    def get_signal_adjustment(self) -> dict:
        """活动期间的信号调整。"""
        return {
            "extend_cycle": True,
            "cycle_extension": 15,  # 周期延长 15 秒
            "pedestrian_priority": True,  # 行人优先
            "special_phases": [
                {"name": "EVENT_CLEAR", "duration": 30, "direction": "away_from_venue"},
            ],
        }
```

---

## 6. 潮汐数据学习

### 6.1 从历史数据学习潮汐模式

```python
class TidalFlowLearner:
    """从历史数据学习潮汐规律。"""
    
    def __init__(self):
        self.history: list[dict] = []  # 历史流量数据
    
    def record(self, timestamp: float, flow_data: dict):
        """记录流量数据。"""
        self.history.append({
            "timestamp": timestamp,
            "hour": (timestamp / 3600) % 24,
            "flow": flow_data,
        })
    
    def learn_pattern(self) -> dict:
        """学习潮汐模式。"""
        from collections import defaultdict
        import statistics
        
        hourly_flows = defaultdict(lambda: {"north": [], "south": [], "east": [], "west": []})
        
        for record in self.history:
            hour = int(record["hour"])
            for direction, count in record["flow"].items():
                hourly_flows[hour][direction].append(count)
        
        patterns = {}
        for hour, directions in hourly_flows.items():
            avg_flows = {
                d: statistics.mean(values) if values else 0
                for d, values in directions.items()
            }
            dominant = max(avg_flows, key=avg_flows.get)
            ratio = avg_flows[dominant] / max(min(avg_flows.values()), 1)
            
            patterns[hour] = {
                "dominant_direction": dominant,
                "tidal_ratio": ratio,
                "is_tidal": ratio > 1.5,
            }
        
        return patterns
```

---

## 7. 实现优先级

| 优先级 | 功能 | 工作量 |
|--------|------|--------|
| P0 | 基于时间的时段切换 | 0.5 天 |
| P0 | 潮汐方向检测（时间+实时） | 1 天 |
| P0 | 潮汐配时调整（主方向延长绿灯） | 0.5 天 |
| P1 | 时段切换渐变过渡 | 0.5 天 |
| P1 | LLM prompt 时段感知 | 0.5 天 |
| P2 | 历史数据学习潮汐模式 | 2 天 |
| P2 | 特殊事件处理 | 1 天 |
| P3 | 可变车道控制 | 3 天 |
