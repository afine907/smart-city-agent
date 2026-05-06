# 第4章 评估层

## 核心理念

**评估驱动开发**：一切以数据说话，LLM 方案必须在指标上胜出传统方法。

## 核心假设

> **LLM 在异常场景下比传统方法更好。**

常规均匀车流下，自适应控制已经很有效。LLM 的真正优势在于：
- 事故/施工导致车道封闭
- 大型活动突发拥堵
- 紧急车辆优先通行
- 多路口协调的全局优化

## 评估指标

| 指标 | 定义 | 为什么重要 |
|------|------|-----------|
| 平均延迟 | 每辆车从停止到通过的时间 | 核心效率指标 |
| 吞吐量 | 每分钟通过路口的车辆数 | 路口容量 |
| 排队长度 | 各方向最大排队车辆数 | 公平性 |
| 紧急车辆响应 | 紧急车辆通过时间 | 安全性 |
| LLM 延迟 | 从请求到决策的时间 | 工程可行性 |
| LLM 成本 | 每次决策的 API 费用 | 经济可行性 |

## 实验设计

### 两大场景类型

#### A. 常常场景（Baseline）

正常交通流，验证基本功能：

| 实验 | 路网 | 需求 | 目的 |
|------|------|------|------|
| A1 | shenzhen | 低 (500 veh/h) | 基本功能 |
| A2 | shenzhen | 中 (1000 veh/h) | 中等压力 |
| A3 | shenzhen | 高 (2000 veh/h) | 高压力 |

#### B. 异常场景（亮点）

这是 LLM 的真正战场：

| 实验 | 场景 | 描述 | LLM 优势 |
|------|------|------|---------|
| B1 | 突发事故 | 仿真中途某车道封闭 | LLM 能理解并重新规划 |
| B2 | 紧急车辆 | 救护车/消防车需要优先 | LLM 能识别并让行 |
| B3 | 大型活动 | 某方向突然车流激增 | LLM 能动态调整 |
| B4 | 施工绕行 | 多个路口同时受影响 | LLM 能协调多路口 |
| B5 | 潮汐流 | 早晚高峰方向切换 | LLM 能预判趋势 |

### 实验矩阵

```python
EXPERIMENTS = {
    # 常常场景
    "A1": {"network": "shenzhen", "demand": "low", "scenario": "normal"},
    "A2": {"network": "shenzhen", "demand": "medium", "scenario": "normal"},
    "A3": {"network": "shenzhen", "demand": "high", "scenario": "normal"},
    
    # 异常场景
    "B1": {"network": "shenzhen", "demand": "medium", "scenario": "accident"},
    "B2": {"network": "shenzhen", "demand": "medium", "scenario": "emergency"},
    "B3": {"network": "shenzhen", "demand": "medium", "scenario": "surge"},
    "B4": {"network": "shenzhen", "demand": "medium", "scenario": "construction"},
    "B5": {"network": "shenzhen", "demand": "medium", "scenario": "tidal"},
}
```

## 基线控制器

### 4 种基线

```python
class FixedTimeController:
    """固定时序控制（基线 1）。"""
    def decide(self, state):
        return {
            "action": "switch_phase",
            "phase": "NS_GREEN",
            "duration": 30,
            "reasoning": "固定时序",
            "confidence": 1.0,
        }

class AdaptiveController:
    """自适应控制（基线 2，最强对手）。"""
    def decide(self, state):
        ns_queue = state["north"]["queue"] + state["south"]["queue"]
        ew_queue = state["east"]["queue"] + state["west"]["queue"]
        
        if ns_queue > ew_queue:
            return {
                "action": "extend_green",
                "phase": "NS_GREEN",
                "duration": min(60, 15 + ns_queue),
                "reasoning": f"南北排队 {ns_queue} > 东西 {ew_queue}",
                "confidence": 0.9,
            }
        else:
            return {
                "action": "switch_phase",
                "phase": "EW_GREEN",
                "duration": min(60, 15 + ew_queue),
                "reasoning": f"东西排队 {ew_queue} > 南北 {ns_queue}",
                "confidence": 0.9,
            }

class LLMController:
    """LLM 控制（我们的方法）。"""
    def __init__(self, llm_client):
        self.llm = llm_client
    
    def decide(self, state):
        return self.llm.decide(SYSTEM_PROMPT, build_user_prompt(state))
```

## 异常场景注入

### B1: 突发事故

```python
def inject_accident(step: int):
    """在 step=1800 时注入事故，封闭某车道。"""
    if step == 1800:
        # 封闭北向车道
        traci.lane.setDisallowed("north_in_0", ["all"])
        traci.lane.setDisallowed("north_in_1", ["all"])
        print("ACCIDENT: North lanes closed")
    elif step == 2400:
        # 600 秒后恢复
        traci.lane.setAllowed("north_in_0", ["all"])
        traci.lane.setAllowed("north_in_1", ["all"])
        print("ACCIDENT: North lanes reopened")
```

### B2: 紧急车辆

```python
def inject_emergency(step: int):
    """在 step=1200 时注入紧急车辆。"""
    if step == 1200:
        # 添加救护车，从北到南
        traci.vehicle.add("ambulance_1", route="north_south", type="emergency")
        traci.vehicle.setSpeedMode("ambulance_1", 0)  # 无限制
        traci.vehicle.setSpeed("ambulance_1", 30)  # 30 m/s
        print("EMERGENCY: Ambulance injected")
```

### B3: 大型活动（车流突增）

```python
def inject_surge(step: int):
    """在 step=1800 时注入车流突增。"""
    if step == 1800:
        # 东向车流增加 3 倍
        for _ in range(100):
            traci.vehicle.add(f"surge_{_}", route="east_west", depart=step)
        print("SURGE: East flow tripled")
```

## 消融实验

验证 LLM 各组件的贡献：

| 实验 | 变化 | 目的 |
|------|------|------|
| C1 | LLM 无 CoT（直接输出相位） | CoT 推理的价值 |
| C2 | 小模型（GPT-4o-mini vs GPT-4o） | 模型大小的影响 |
| C3 | 简化 prompt（去掉工程背景） | Prompt 质量的影响 |
| C4 | 无缓存 | 缓存的价值 |
| C5 | 规则约束 LLM（只允许安全动作） | 安全约束的影响 |

```python
ABLATION_CONFIGS = {
    "C1": {"cot": False, "model": "gpt-4o"},
    "C2": {"cot": True, "model": "gpt-4o-mini"},
    "C3": {"cot": True, "model": "gpt-4o", "prompt": "simple"},
    "C4": {"cot": True, "model": "gpt-4o", "cache": False},
    "C5": {"cot": True, "model": "gpt-4o", "safe_constraints": True},
}
```

## 统计检验

```python
from scipy import stats
import numpy as np

def statistical_test(fixed_results: list, llm_results: list) -> dict:
    """进行统计显著性检验。"""
    # 配对 t 检验
    t_stat, p_value = stats.ttest_rel(fixed_results, llm_results)
    
    # Cohen's d（效应大小）
    diff = np.mean(fixed_results) - np.mean(llm_results)
    pooled_std = np.sqrt(
        (np.std(fixed_results)**2 + np.std(llm_results)**2) / 2
    )
    cohens_d = diff / pooled_std if pooled_std > 0 else 0
    
    return {
        "t_statistic": t_stat,
        "p_value": p_value,
        "cohens_d": cohens_d,
        "significant": p_value < 0.05,
        "effect_size": "large" if cohens_d > 0.8 else "medium" if cohens_d > 0.5 else "small",
    }

# 每个实验跑 5 次，取平均和标准差
RUNS_PER_EXPERIMENT = 5
```

## 结果可视化

```python
def generate_report(results_df):
    """生成对比报告。"""
    report = results_df.pivot_table(
        index=["scenario"],
        columns="controller",
        values=["avg_wait", "max_queue", "total_throughput"],
    )
    
    # 计算改进百分比
    for scenario in report.index:
        fixed_wait = report.loc[scenario, ("avg_wait", "fixed")]
        llm_wait = report.loc[scenario, ("avg_wait", "llm")]
        improvement = (fixed_wait - llm_wait) / fixed_wait * 100
        print(f"{scenario}: LLM improves {improvement:.1f}%")
    
    return report
```

### 预期结果模式

```
场景        固定时序  自适应  LLM     LLM 改进
─────────────────────────────────────────────
正常低需求   25s     20s    19s     24%  (小幅)
正常中需求   45s     35s    30s     33%  (中等)
正常高需求   80s     55s    48s     40%  (明显)
事故场景     120s    90s    65s     46%  (LLM 优势)
紧急车辆     45s     30s    15s     67%  (LLM 优势)
车流突增     95s     70s    50s     47%  (LLM 优势)
```

**关键发现预期**：LLM 在异常场景下的优势远大于常常场景。

## 失败案例分析

必须记录 LLM 表现不好的场景：

| 失败类型 | 表现 | 原因 | 应对 |
|----------|------|------|------|
| 简单均匀流 | LLM ≈ 自适应 | 没有推理空间 | 规则接管 |
| LLM 幻觉 | 输出非法相位 | 模型错误 | 解析器拦截 |
| LLM 延迟高 | 决策滞后 | API 慢 | 缓存 + 规则降级 |
| 过度保守 | 不敢切相位 | Prompt 偏保守 | 调整 prompt |
