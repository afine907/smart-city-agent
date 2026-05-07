# 设计文档索引

> **核心问题：一个 LLM 能不能比传统方法更好地控制交通信号灯？**

## 文档结构

| 章节 | 文件 | 内容 |
|------|------|------|
| 第0章 | [00-overview.md](00-overview.md) | 核心问题、总体架构、设计原则 |
| 第1章 | [01-simulation.md](01-simulation.md) | SUMO 仿真层、TraCI 接口、Sim Bridge |
| 第2章 | [02-llm-agent.md](02-llm-agent.md) | LLM Agent 层、Prompt 设计、CoT、降级策略 |
| 第3章 | [03-road-network.md](03-road-network.md) | OSM → SUMO 路网、3 个预设城市 |
| 第4章 | [04-evaluation.md](04-evaluation.md) | 评估指标、基线对比、实验设计、统计检验 |
| 第5章 | [05-architecture.md](05-architecture.md) | 完整项目结构、核心模块、数据流 |
| 第6章 | [06-comparison.md](06-comparison.md) | 与现有工作的区别、学术定位 |
| 第7章 | [07-implementation.md](07-implementation.md) | 2 周实施计划、验收标准、风险应对 |
| **第8章** | **[08-multi-intersection-coordination.md](08-multi-intersection-coordination.md)** | **多路口协调：绿波、冲突检测、Agent 通信** |
| **第9章** | **[09-pedestrian-signal.md](09-pedestrian-signal.md)** | **行人与非机动车信号：过街相位、二次过街** |
| **第10章** | **[10-junction-types.md](10-junction-types.md)** | **路口类型：十字/丁字/Y型/环形/多路/斜交** |
| **第11章** | **[11-left-turn-control.md](11-left-turn-control.md)** | **左转控制：保护/许可/受控许可、冲突检测** |
| **第12章** | **[12-transit-priority.md](12-transit-priority.md)** | **公交优先：检测、信号策略、站台协调** |
| **第13章** | **[13-tidal-flow.md](13-tidal-flow.md)** | **潮汐与时段：时段划分、潮汐检测、配时调整** |
| **第14章** | **[14-dashboard.md](14-dashboard.md)** | **Dashboard 产品设计：信息架构、交互、可视化** |
| **第15章** | **[15-deployment.md](15-deployment.md)** | **部署与运维：容器化、监控、灰度、故障恢复** |
| **第16章** | **[16-safety.md](16-safety.md)** | **安全边界：硬约束、人工接管、数据安全** |

另有独立设计文档：
- [../../MIXED_TRAFFIC_DESIGN.md](../../MIXED_TRAFFIC_DESIGN.md) — 混行交通详细设计（6种交通参与者、物理属性、信号遵守模型）

## 最佳技术栈

```
仿真: SUMO (C++ 引擎, Python TraCI)
LLM:  GPT-4o / Qwen (Tool Use + CoT)
路网: OSM → netconvert → .net.xml
评估: pandas + scipy (统计检验)
```

## 关键认知

> **真正的难度不在技术栈，在于实验设计是否严谨、评估指标是否合理、LLM prompt 是否有效。**

## 城市优先级

1. **shenzhen** — 深圳西丽留仙洞（老板上班的地方），优先级最高
2. **wuhan** — 武汉光谷
3. **manhattan** — 纽约时代广场

先在深圳跑通全流程，再扩展其他城市。
