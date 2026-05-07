# 第16章 安全边界设计

> **AI 可以辅助决策，但不能成为安全隐患。每一条安全规则都不能被 LLM 覆盖。**

## 核心原则

**安全约束是硬编码的，不受 LLM 控制。**

LLM 可以在安全边界内自由优化信号配时，但以下行为被系统强制禁止：
- 两个相邻方向同时绿灯
- 绿灯时间超过最大限制
- 行人过街时没有清空时间
- 紧急车辆被忽略

---

## 1. 安全层级

### 1.1 四层安全模型

```
┌─────────────────────────────────────────┐
│  Layer 4: 人工接管 (最高优先级)           │
│  交警可以随时覆盖任何 AI 决策              │
├─────────────────────────────────────────┤
│  Layer 3: 安全硬约束                      │
│  不可违反的物理和法规限制                  │
├─────────────────────────────────────────┤
│  Layer 2: 规则引擎                        │
│  经过验证的交通工程规则                    │
├─────────────────────────────────────────┤
│  Layer 1: LLM 决策 (最低优先级)           │
│  AI 优化配时，但受上层约束                 │
└─────────────────────────────────────────┘
```

### 1.2 优先级规则

```python
class SafetyLayer:
    """安全层级——从高到低。"""
    
    MANUAL_OVERRIDE = 4     # 人工接管
    HARD_CONSTRAINT = 3     # 安全硬约束
    RULE_ENGINE = 2         # 规则引擎
    LLM_DECISION = 1        # LLM 决策
    
    @staticmethod
    def resolve_conflict(
        manual: dict,
        hard: dict,
        rule: dict,
        llm: dict,
    ) -> dict:
        """
        冲突解决：高优先级覆盖低优先级。
        
        人工接管 > 安全硬约束 > 规则引擎 > LLM 决策
        """
        # 人工接管最优先
        if manual:
            return manual
        
        # 安全硬约束不可违反
        if hard:
            # LLM 决策如果违反硬约束，被拦截
            return hard
        
        # 规则引擎作为兜底
        if rule:
            return rule
        
        # LLM 决策
        return llm
```

---

## 2. 安全硬约束

### 2.1 不可违反的规则

```python
HARD_CONSTRAINTS = [
    # 信号灯冲突
    {
        "id": "NO_SIMULTANEOUS_GREEN",
        "rule": "相邻方向不能同时绿灯",
        "check": lambda state: not (
            state["ns_green"] and state["ew_green"]
        ),
        "severity": "critical",
        "action": "force_all_red",
    },
    
    # 最小绿灯时间
    {
        "id": "MIN_GREEN_TIME",
        "rule": "绿灯时间不少于 10 秒",
        "check": lambda state: state["green_duration"] >= 10,
        "severity": "critical",
        "action": "extend_to_minimum",
    },
    
    # 最大绿灯时间
    {
        "id": "MAX_GREEN_TIME",
        "rule": "绿灯时间不超过 90 秒",
        "check": lambda state: state["green_duration"] <= 90,
        "severity": "warning",
        "action": "force_phase_switch",
    },
    
    # 黄灯时间
    {
        "id": "YELLOW_TIME",
        "rule": "黄灯时间 3-5 秒",
        "check": lambda state: 3 <= state["yellow_duration"] <= 5,
        "severity": "critical",
        "action": "use_default_yellow",
    },
    
    # 全红清空
    {
        "id": "ALL_RED_CLEARANCE",
        "rule": "相位切换后必须有全红清空时间",
        "check": lambda state: state["all_red_duration"] >= 2,
        "severity": "critical",
        "action": "insert_all_red",
    },
    
    # 行人安全
    {
        "id": "PED Clearance",
        "rule": "行人过街必须有足够清空时间",
        "check": lambda state: (
            state["ped_clearance_time"] >= state["crossing_distance"] / 1.0
        ),
        "severity": "critical",
        "action": "extend_ped_clearance",
    },
    
    # 紧急车辆
    {
        "id": "EMERGENCY_PRIORITY",
        "rule": "紧急车辆必须获得优先",
        "check": lambda state: (
            not state["has_emergency"] or state["emergency_handled"]
        ),
        "severity": "critical",
        "action": "force_emergency_phase",
    },
    
    # 不能无限红灯
    {
        "id": "MAX_RED_TIME",
        "rule": "任何方向红灯不超过 120 秒",
        "check": lambda state: state["red_duration"] <= 120,
        "severity": "warning",
        "action": "force_green",
    },
]
```

### 2.2 约束检查器

```python
class SafetyConstraintChecker:
    """安全约束检查器——在每次决策前和决策后运行。"""
    
    def __init__(self, constraints: list[dict]):
        self.constraints = constraints
    
    def check_before_decision(
        self,
        current_state: dict,
        proposed_decision: dict,
    ) -> tuple[bool, list[dict]]:
        """
        决策前检查：验证当前状态是否安全。
        
        返回: (是否安全, 违反的约束列表)
        """
        violations = []
        
        for constraint in self.constraints:
            try:
                if not constraint["check"](current_state):
                    violations.append(constraint)
            except Exception as e:
                # 检查逻辑本身出错，视为违反
                violations.append({
                    **constraint,
                    "error": str(e),
                })
        
        return len(violations) == 0, violations
    
    def check_after_decision(
        self,
        current_state: dict,
        decision: dict,
    ) -> tuple[bool, dict]:
        """
        决策后检查：验证决策是否会导致不安全状态。
        
        返回: (是否安全, 修正后的决策)
        """
        # 模拟决策后的状态
        simulated_state = self._simulate_decision(current_state, decision)
        
        # 检查模拟状态
        is_safe, violations = self.check_before_decision(
            simulated_state, decision
        )
        
        if not is_safe:
            # 自动修正
            decision = self._auto_correct(decision, violations)
        
        return is_safe, decision
    
    def _simulate_decision(self, state: dict, decision: dict) -> dict:
        """模拟决策后的状态。"""
        simulated = state.copy()
        
        if decision.get("action") == "switch_phase":
            simulated["ns_green"] = "NS" in decision.get("phase", "")
            simulated["ew_green"] = "EW" in decision.get("phase", "")
            simulated["green_duration"] = 0
            simulated["red_duration"] = 0
        
        elif decision.get("action") == "extend_green":
            simulated["green_duration"] += decision.get("extension", 0)
        
        return simulated
    
    def _auto_correct(
        self,
        decision: dict,
        violations: list[dict],
    ) -> dict:
        """自动修正违反约束的决策。"""
        corrected = decision.copy()
        
        for violation in violations:
            action = violation.get("action", "force_all_red")
            
            if action == "force_all_red":
                corrected = {"action": "emergency_stop", "phase": "ALL_RED"}
            
            elif action == "extend_to_minimum":
                corrected["duration"] = max(
                    corrected.get("duration", 0), 10
                )
            
            elif action == "force_phase_switch":
                corrected = {
                    "action": "switch_phase",
                    "phase": self._get_next_phase(corrected.get("phase")),
                    "reason": f"[安全约束] {violation['rule']}",
                }
        
        return corrected
```

---

## 3. LLM 输出安全过滤

### 3.1 输出验证

LLM 的输出在执行前必须经过验证：

```python
class LLMSafetyFilter:
    """LLM 输出安全过滤器。"""
    
    def __init__(self):
        self.allowed_actions = {
            "extend_green", "switch_phase", "emergency",
            "insert_phase", "none",
        }
        self.allowed_phases = set()  # 从信号方案动态加载
        self.max_duration = 90
        self.min_duration = 10
    
    def filter(self, llm_output: dict) -> dict:
        """
        过滤 LLM 输出。
        
        检查：
        1. 动作类型是否合法
        2. 相位是否在有效范围内
        3. 时长是否在合理范围内
        4. 是否违反安全约束
        """
        filtered = llm_output.copy()
        
        # 检查动作类型
        if filtered.get("action") not in self.allowed_actions:
            filtered["action"] = "none"
            filtered["reasoning"] += " [安全过滤: 非法动作]"
        
        # 检查相位
        if filtered.get("phase") not in self.allowed_phases:
            filtered["action"] = "none"
            filtered["reasoning"] += " [安全过滤: 非法相位]"
        
        # 检查时长
        duration = filtered.get("duration", 30)
        if duration < self.min_duration:
            filtered["duration"] = self.min_duration
            filtered["reasoning"] += " [安全过滤: 时长过短]"
        elif duration > self.max_duration:
            filtered["duration"] = self.max_duration
            filtered["reasoning"] += " [安全过滤: 时长过长]"
        
        return filtered
```

### 3.2 禁止 LLM 做的事

```python
LLM_FORBIDDEN = [
    "不能同时给两个垂直方向绿灯",
    "不能跳过黄灯直接切绿灯",
    "不能跳过全红清空时间",
    "不能忽略紧急车辆",
    "不能设置超过 90 秒的绿灯",
    "不能设置少于 10 秒的绿灯",
    "不能在行人过街时切换相位",
    "不能关闭信号灯（除非紧急停车）",
    "不能修改安全约束参数",
    "不能绕过降级策略",
]
```

---

## 4. 人工接管机制

### 4.1 接管权限

| 角色 | 权限 | 可操作 |
|------|------|--------|
| 普通用户 | 只读 | 查看状态 |
| 操作员 | 基本控制 | 强制相位、紧急停车 |
| 管理员 | 完全控制 | 修改配置、管理 Agent |
| 超级管理员 | 系统管理 | 修改安全约束、用户管理 |

### 4.2 接管流程

```
1. 操作员在 Dashboard 选择路口
2. 点击"手动控制"
3. 选择操作（强制相位/紧急停车）
4. 二次确认（输入原因）
5. 系统执行操作
6. LLM Agent 暂停该路口控制
7. 操作日志记录
8. 操作员点击"恢复自动"后，LLM 重新接管
```

### 4.3 接管日志

```json
{
  "event": "manual_override",
  "timestamp": "2026-05-07T14:32:05+08:00",
  "operator": "张三",
  "operator_id": "op_001",
  "intersection": "intersection_001",
  "action": "force_phase",
  "phase": "EW_GREEN",
  "duration": 30,
  "reason": "东西方向救护车需要通过",
  "llm_suspended": true,
  "auto_resume_at": "2026-05-07T14:37:05+08:00"
}
```

---

## 5. 数据安全

### 5.1 数据分类

| 数据类型 | 敏感度 | 存储要求 | 保留期 |
|---------|--------|---------|--------|
| 信号灯状态 | 低 | 普通存储 | 30 天 |
| 车辆轨迹 | 高 | 加密存储 | 90 天 |
| LLM 决策日志 | 中 | 加密存储 | 1 年 |
| 操作员操作日志 | 高 | 加密+审计 | 永久 |
| 摄像头图像 | 极高 | 不存储/边缘处理 | 不保留 |
| 个人信息 | 极高 | 脱敏/不采集 | 不保留 |

### 5.2 隐私保护

```python
PRIVACY_RULES = [
    # 不存储车牌号（除非执法需要）
    "NO_LICENSE_PLATE_STORAGE",
    
    # 不采集人脸数据
    "NO_FACE_RECOGNITION",
    
    # 车辆轨迹脱敏（只保留匿名化的轨迹点）
    "ANONYMIZE_VEHICLE_TRAJECTORIES",
    
    # LLM 输入不包含个人信息
    "LLM_INPUT_NO_PII",
    
    # 数据不出境（除非用户授权）
    "DATA_RESIDENCY",
]
```

### 5.3 LLM 数据安全

```python
LLM_DATA_SECURITY = [
    # LLM 输入只包含交通数据，不包含个人数据
    "input_validation",
    
    # LLM 输出不包含敏感信息
    "output_filtering",
    
    # API 调用使用加密连接
    "encrypted_transport",
    
    # 不将原始数据发送给 LLM，只发送摘要
    "data_minimization",
    
    # 记录所有 LLM 调用，便于审计
    "audit_logging",
]
```

---

## 6. 异常检测

### 6.1 LLM 异常检测

```python
class LLMAnomalyDetector:
    """LLM 异常行为检测。"""
    
    def __init__(self):
        self.history: list[dict] = []
        self.anomaly_threshold = 3  # 连续 3 次异常触发告警
    
    def check(self, decision: dict, state: dict) -> bool:
        """
        检测 LLM 决策是否异常。
        
        异常类型：
        1. 反复切换相位（抖动）
        2. 决策与路况严重不符
        3. 置信度过低
        4. 推理过程不合理
        """
        anomalies = []
        
        # 检测相位抖动
        if self._is_phasing(decision):
            anomalies.append("phasing")
        
        # 检测决策与路况不符
        if self._is_mismatched(decision, state):
            anomalies.append("mismatched")
        
        # 检测置信度过低
        if decision.get("confidence", 0) < 0.3:
            anomalies.append("low_confidence")
        
        # 记录
        self.history.append({
            "timestamp": time.time(),
            "decision": decision,
            "anomalies": anomalies,
        })
        
        return len(anomalies) > 0
    
    def _is_phasing(self, decision: dict) -> bool:
        """检测相位抖动：短时间内反复切换。"""
        if len(self.history) < 3:
            return False
        
        recent = self.history[-3:]
        phases = [h["decision"].get("phase") for h in recent]
        
        # 如果最近 3 次决策的相位都不同
        return len(set(phases)) == 3
    
    def _is_mismatched(self, decision: dict, state: dict) -> bool:
        """检测决策与路况不符。"""
        # 如果南北排队很长，但 LLM 却给东西绿灯
        if (state.get("queue_ns", 0) > 20 and
            decision.get("phase") == "EW_GREEN"):
            return True
        
        return False
```

### 6.2 系统异常检测

```python
SYSTEM_ANOMALY_RULES = [
    {
        "name": "decision_latency_spike",
        "condition": "decision_latency > 10s",
        "action": "log_warning",
    },
    {
        "name": "consecutive_llm_failures",
        "condition": "llm_failures > 5",
        "action": "switch_to_rule_engine",
    },
    {
        "name": "unusual_traffic_pattern",
        "condition": "traffic_deviation > 3_sigma",
        "action": "alert_operator",
    },
    {
        "name": "resource_exhaustion",
        "condition": "memory > 90% or cpu > 90%",
        "action": "scale_up",
    },
]
```

---

## 7. 实现优先级

| 优先级 | 功能 | 工作量 |
|--------|------|--------|
| P0 | 安全硬约束检查器 | 1 天 |
| P0 | LLM 输出过滤器 | 0.5 天 |
| P0 | 降级策略（LLM → 规则引擎） | 1 天 |
| P1 | 人工接管机制 | 2 天 |
| P1 | 操作审计日志 | 1 天 |
| P1 | LLM 异常检测 | 1 天 |
| P2 | 数据安全（加密、脱敏） | 2 天 |
| P2 | 系统异常检测 | 1 天 |
| P3 | 渗透测试 | 3 天 |
