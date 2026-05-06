# 第6章 与现有工作的区别

## 与 LLM-Assisted-Light 的对比

| 维度 | LLM-Assisted-Light | 本项目 |
|------|-------------------|--------|
| 仿真器 | 自研 Aiolos → TSHub | SUMO（更标准、更真实） |
| LLM 用法 | 5 阶段工具调用 | Tool Use + CoT |
| 路网 | 简单 3/4 路口 | 真实 OSM 路网 |
| 多城市 | 无 | manhattan/wuhan/shenzhen |
| 对比基线 | RL | 固定/自适应/RL/LLM |
| 可复现性 | 依赖自研仿真器 | SUMO 标准，易复现 |

## 与现有项目的差异

### 现有架构的问题

| 问题 | 现状 | 应该 |
|------|------|------|
| 仿真器 | 自研轻量仿真器（`SimulationEngine`、`Vehicle`、`RoadNetwork`） | SUMO |
| Agent 框架 | CrewAI 多 Agent 协调（`traffic_crew.py`、`coordination.py`） | 简单 Tool Use |
| 路网 | 自研 grid + OSM 轻量实现 | SUMO + netconvert |
| 复杂度 | 多层抽象（`base_agent`、`intersection`、`crew`） | 聚焦核心 |
| 评估 | 自研 benchmark（`quality_benchmark.py`） | 标准化指标 + 统计检验 |

### 核心认知

> **真正的难度不在技术栈，在于实验设计是否严谨、评估指标是否合理、LLM prompt 是否有效。**

现有项目花了很多精力在：
- CrewAI Agent 定义和协调
- 自研仿真引擎
- Dashboard 3D 可视化
- 多层抽象

但忽略了：
- 仿真器的真实性（自研 vs SUMO）
- 评估的严谨性（统计检验、多基线对比）
- Prompt 工程的迭代

### 重新聚焦

```
之前: 复杂架构 → 仿真 → 评估
现在: 仿真 → LLM 决策 → 评估 → 迭代 prompt
```

简化架构，把精力放在：
1. **仿真真实性**：用 SUMO，不造轮子
2. **LLM 有效性**：prompt 工程、CoT 设计
3. **评估严谨性**：多基线、统计检验、消融实验

## 学术定位

### 论文标题（候选）

> "Can LLMs Control Traffic Signals Better? A Comparative Study with SUMO Simulation"

### 贡献点

1. **标准化仿真框架**：基于 SUMO 的 LLM 交通控制评估框架
2. **异常场景验证**：LLM 在事故/紧急/突增等异常场景下的优势
3. **多城市验证**：3 个城市路网的跨场景验证（深圳优先）
4. **系统性对比**：固定/自适应/RL/LLM 的全面对比 + 消融实验
5. **可解释性分析**：LLM CoT 推理过程的定性分析

### 与相关工作的区别

```
相关工作                     本项目
─────────────────────────────────────────────────
RL-based (PressLight)       → LLM-based (zero training)
自研仿真 (CityFlow)          → SUMO (standard)
单城市验证                   → 多城市 (3 cities)
单一基线                     → 多基线 (4 types)
黑盒决策                     → 可解释 (CoT reasoning)
```

## 参考文献

1. **SUMO**: Lopez, P. A., et al. "Microscopic traffic simulation using SUMO." ITSC 2018.
2. **LLM-Assisted-Light**: "LLM-Assisted-Light: Leveraging Large Language Model for Adaptive Traffic Signal Control." 2024.
3. **PressLight**: Wei, H., et al "PressLight: Learning Max Pressure Control to Coordinate Traffic Signals in Arterial Network." KDD 2019.
4. **CityFlow**: Zhang, H., et al. "CityFlow: A Multi-Agent Reinforcement Learning Environment for Large Scale City Traffic Scenario." WWW 2019.
