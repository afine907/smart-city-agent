# 第11章 左转控制设计

> **左转是路口最复杂的动作——它是唯一需要穿越对向车流的转向。**

## 问题本质

左转车辆必须穿越对向直行车流，这是路口冲突的主要来源。
不同国家对左转的处理方式不同：
- **中国**：左转需要保护相位（绿灯时对向红灯）
- **美国**：允许左转（左转绿灯+对向绿灯同时亮，需让行）
- **日本**：左转优先+让行（类似中国的右转）

本项目需要同时支持多种左转控制策略。

---

## 1. 左转控制模式

### 1.1 三种模式

| 模式 | 描述 | 安全性 | 效率 | 适用场景 |
|------|------|--------|------|---------|
| **保护左转** | 专用左转相位，对向红灯 | 最高 | 中 | 高流量、多事故 |
| **许可左转** | 左转绿灯+对向绿灯同时亮 | 中 | 高 | 低流量、视野好 |
| **受控许可** | 闪烁绿灯/绿箭头切换 | 中高 | 中高 | 混合流量 |

### 1.2 模式切换条件

```python
from enum import Enum

class LeftTurnMode(str, Enum):
    PROTECTED = "protected"       # 保护左转：专用相位
    PERMISSIVE = "permissive"     # 许可左转：对向绿灯时可左转（需让行）
    CONTROLLED_PERMISSIVE = "controlled_permissive"  # 受控许可：闪烁绿灯


@dataclass
class LeftTurnPolicy:
    """左转控制策略。"""
    mode: LeftTurnMode
    
    # 触发条件
    left_turn_volume: int = 0      # 左转车辆数/小时
    opposing_volume: int = 0       # 对向直行车辆数/小时
    conflicting_pedestrians: int = 0  # 冲突行人数
    accident_history: float = 0.0  # 历史事故率
    
    # 切换阈值
    protected_threshold: int = 100   # 左转 > 100 veh/h → 保护模式
    opposing_threshold: int = 300    # 对向 > 300 veh/h → 保护模式
    ped_threshold: int = 20          # 冲突行人 > 20 → 保护模式
    
    def determine_mode(self) -> LeftTurnMode:
        """根据流量决定左转模式。"""
        # 高流量强制保护模式
        if (self.left_turn_volume > self.protected_threshold or
            self.opposing_volume > self.opposing_threshold or
            self.conflicting_pedestrians > self.ped_threshold or
            self.accident_history > 0.5):
            return LeftTurnMode.PROTECTED
        
        # 中等流量用受控许可
        if self.left_turn_volume > 50 or self.opposing_volume > 150:
            return LeftTurnMode.CONTROLLED_PERMISSIVE
        
        # 低流量许可左转
        return LeftTurnMode.PERMISSIVE
```

---

## 2. 左转冲突检测

### 2.1 冲突类型

```
冲突1: 左转 vs 对向直行（最常见）
  ← ← ← ← ←
  ─────────────→  对向直行
       ↗
     ↗ 左转车辆
   ↗

冲突2: 左转 vs 行人
  ──────→
       🚶 ← 行人在斑马线上
     ↗
   ↗ 左转车辆

冲突3: 左转 vs 非机动车
  ──────→
       🛵 ← 电动车在非机动车道
     ↗
   ↗ 左转车辆
```

### 2.2 冲突检测逻辑

```python
@dataclass
class LeftTurnConflict:
    """左转冲突。"""
    conflict_id: str
    conflict_type: str       # "opposing_vehicle" | "pedestrian" | "non_motorized"
    left_turn_vehicle_id: str
    conflicting_id: str      # 冲突对象 ID
    distance: float          # 距离 (m)
    time_to_conflict: float  # 到冲突点的时间 (s)
    severity: float          # 0.0-1.0


class LeftTurnConflictDetector:
    """左转冲突检测器。"""
    
    def detect(
        self,
        left_turn_vehicles: list[dict],
        opposing_vehicles: list[dict],
        pedestrians: list[dict],
        non_motorized: list[dict],
    ) -> list[LeftTurnConflict]:
        conflicts = []
        
        for lt in left_turn_vehicles:
            # 检测对向直行冲突
            for opp in opposing_vehicles:
                if self._will_conflict(lt, opp):
                    conflicts.append(LeftTurnConflict(
                        conflict_id=f"lt_opp_{lt['id']}_{opp['id']}",
                        conflict_type="opposing_vehicle",
                        left_turn_vehicle_id=lt["id"],
                        conflicting_id=opp["id"],
                        distance=self._distance(lt, opp),
                        time_to_conflict=self._time_to_conflict(lt, opp),
                        severity=self._severity(lt, opp),
                    ))
            
            # 检测行人冲突
            for ped in pedestrians:
                if self._ped_will_conflict(lt, ped):
                    conflicts.append(LeftTurnConflict(
                        conflict_id=f"lt_ped_{lt['id']}_{ped['id']}",
                        conflict_type="pedestrian",
                        left_turn_vehicle_id=lt["id"],
                        conflicting_id=ped["id"],
                        distance=self._distance(lt, ped),
                        time_to_conflict=self._time_to_conflict(lt, ped),
                        severity=0.8,  # 行人冲突严重性高
                    ))
            
            # 检测非机动车冲突
            for nm in non_motorized:
                if self._nm_will_conflict(lt, nm):
                    conflicts.append(LeftTurnConflict(
                        conflict_id=f"lt_nm_{lt['id']}_{nm['id']}",
                        conflict_type="non_motorized",
                        left_turn_vehicle_id=lt["id"],
                        conflicting_id=nm["id"],
                        distance=self._distance(lt, nm),
                        time_to_conflict=self._time_to_conflict(lt, nm),
                        severity=0.7,
                    ))
        
        return conflicts
    
    def _will_conflict(self, lt: dict, opp: dict) -> bool:
        """判断左转车辆和对向直行是否会冲突。"""
        # 简化判断：如果对向车辆在接近且左转车辆正在转弯
        if lt.get("is_turning") and opp.get("speed", 0) > 5:
            dist = self._distance(lt, opp)
            if dist < 50:  # 50 米内
                return True
        return False
    
    def _ped_will_conflict(self, lt: dict, ped: dict) -> bool:
        """判断左转车辆和行人是否会冲突。"""
        # 行人在斑马线上且左转车辆正在转弯
        if lt.get("is_turning") and ped.get("is_crossing"):
            dist = self._distance(lt, ped)
            if dist < 20:  # 20 米内
                return True
        return False
    
    def _nm_will_conflict(self, lt: dict, nm: dict) -> bool:
        """判断左转车辆和非机动车是否会冲突。"""
        if lt.get("is_turning") and nm.get("speed", 0) > 2:
            dist = self._distance(lt, nm)
            if dist < 25:  # 25 米内
                return True
        return False
```

---

## 3. 左转信号设计

### 3.1 保护左转相位

```python
PROTECTED_LEFT_TURN_PHASES = [
    # 阶段1: 南北直行
    {"name": "NS_STRAIGHT", "vehicle_ns_straight": True, "ped_ns": True},
    # 阶段2: 南北左转（对向红灯）
    {"name": "NS_LEFT", "vehicle_ns_left": True, "opposing_red": True},
    # 阶段3: 东西直行
    {"name": "EW_STRAIGHT", "vehicle_ew_straight": True, "ped_ew": True},
    # 阶段4: 东西左转（对向红灯）
    {"name": "EW_LEFT", "vehicle_ew_left": True, "opposing_red": True},
]
```

### 3.2 许可左转（无专用相位）

```python
PERMISSIVE_LEFT_TURN = {
    "description": "对向绿灯时，左转车辆可左转，但需让行对向直行",
    "signal": "左转绿灯与对向直行绿灯同时亮",
    "yield_rule": "左转车辆必须让行对向直行和过街行人",
    "detection": "需要检测对向是否有车",
    "advantage": "不需要专用相位，效率高",
    "disadvantage": "冲突风险高，需要驾驶员判断",
}
```

### 3.3 受控许可左转

```python
CONTROLLED_PERMISSIVE = {
    "description": "绿灯期间先给直行，左转在绿灯末尾闪烁绿灯时才可左转",
    "signal_sequence": [
        "绿灯（仅直行，左转等待）",
        "绿灯闪烁（左转可开始，对向仍在绿灯）",
        "黄灯（清空）",
        "红灯",
    ],
    "advantage": "平衡安全和效率",
    "disadvantage": "需要精确的闪烁时间控制",
}
```

### 3.4 绿箭头/红箭头

```python
ARROW_SIGNAL = {
    "绿箭头": "允许指定方向转向（无需让行）",
    "红箭头": "禁止指定方向转向",
    "闪烁绿箭头": "允许转向但需让行（受控许可）",
    "黄箭头": "即将变红，准备停车",
}
```

---

## 4. 左转排队管理

### 4.1 左转专用道

```
直行道 ─────────────→
左转道 ← ← ← ← ← ←  ← 左转专用车道（有左转等待区）
右转道 ─────────────→
```

### 4.2 左转排队溢出

当左转专用车道排满时，左转车辆会占用直行车道：

```python
@dataclass
class LeftTurnQueueStatus:
    """左转排队状态。"""
    approach: str             # 方向
    left_lane_queue: int      # 左转车道排队数
    left_lane_capacity: int   # 左转车道容量
    overflow_queue: int       # 溢出到直行车道的车辆数
    
    @property
    def is_overflowing(self) -> bool:
        return self.left_lane_queue >= self.left_lane_capacity
    
    @property
    def overflow_severity(self) -> float:
        """溢出严重程度。"""
        if not self.is_overflowing:
            return 0.0
        return min(1.0, self.overflow_queue / 5.0)  # 5辆车溢出为最严重


def handle_left_turn_overflow(
    status: LeftTurnQueueStatus,
    current_phase: str,
) -> dict:
    """处理左转排队溢出。"""
    if not status.is_overflowing:
        return {"action": "none"}
    
    # 溢出严重时，强制给左转相位
    if status.overflow_severity > 0.7:
        return {
            "action": "force_left_turn_phase",
            "reason": f"左转排队溢出 {status.overflow_queue} 辆，强制给左转相位",
            "duration": min(25, 15 + status.overflow_queue * 2),
        }
    
    # 中等溢出，延长左转相位
    if status.overflow_severity > 0.3:
        return {
            "action": "extend_left_turn",
            "reason": f"左转排队溢出 {status.overflow_queue} 辆，延长左转相位",
            "extension": 10,
        }
    
    return {"action": "none"}
```

---

## 5. LLM 的左转决策

```python
LEFT_TURN_PROMPT = """
## 左转控制信息
当前左转模式：{left_turn_mode}
左转排队：{left_turn_queue}
对向直行排队：{opposing_queue}

## 左转决策规则
1. **保护模式**: 左转车辆多（>10辆）或对向流量大（>300 veh/h）时，
   使用保护左转相位（对向红灯，左转安全通过）
2. **许可模式**: 左转车辆少（<10辆）时，许可左转（对向绿灯时左转，需让行）
3. **受控许可**: 中等流量时，绿灯末尾闪烁允许左转
4. **排队溢出**: 左转车道排满时，强制给左转相位
5. **行人冲突**: 有行人过街时，左转必须让行

## 输出格式
{{
    "left_turn_decision": "protected" | "permissive" | "extend" | "force",
    "reasoning": "<决策理由>",
    "duration": <秒数>,
    "yield_to": ["opposing_vehicle", "pedestrian"]  // 需要让行的对象
}}
"""
```

---

## 6. 与现有设计的衔接

第 9 章（行人信号设计）已经定义了 NS_LEFT / EW_LEFT 相位。
本章补充的是：
- 左转模式的动态切换逻辑（保护/许可/受控许可）
- 左转冲突检测规则
- 左转排队溢出处理
- 左转与行人/非机动车的冲突检测
