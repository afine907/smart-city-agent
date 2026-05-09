# Smart City Agent

> **用 CrewAI 多 Agent + LLM 让红绿灯更智慧，让城市交通更人性化**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-267%20passed-brightgreen.svg)](tests/)

---

我们尝试引入 LLM 辅助红绿灯变得更加智慧聪明。每个路口有一个 Agent 负责观察和决策，多个 Agent 通过协调机制配合工作，让城市的交通更加人性化。

---

## 多 Agent 架构

基于 [CrewAI](https://github.com/crewAIInc/crewAI) 框架，每个路口由一个独立的 Agent 控制，多个 Agent 协同工作：

```
┌─────────────────────────────────────────────────────────────────┐
│                    CrewAI Multi-Agent System                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    │
│   │  Agent: 北路口 │    │  Agent: 东路口 │    │  Agent: 南路口 │    │
│   │  观察路况      │    │  观察路况      │    │  观察路况      │    │
│   │  LLM 推理决策  │    │  LLM 推理决策  │    │  LLM 推理决策  │    │
│   └───────┬──────┘    └───────┬──────┘    └───────┬──────┘    │
│           │                   │                   │            │
│           │    ┌──────────────┴──────────────┐    │            │
│           │    │                             │    │            │
│           ▼    ▼                             ▼    ▼            │
│   ┌───────────────────────────────────────────────────────┐   │
│   │              ConflictDetector                         │   │
│   │  检测相邻路口的相位冲突                                 │   │
│   └───────────────────────────┬───────────────────────────┘   │
│                               │                               │
│                               ▼                               │
│   ┌───────────────────────────────────────────────────────┐   │
│   │              Coordinator Agent                         │   │
│   │  收集各路口决策 → LLM 推理协调 → 输出最终方案           │   │
│   └───────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**协调流程：**

1. 每个 Intersection Agent 观察路况，独立做出信号灯决策
2. ConflictDetector 检测相邻路口的相位冲突
3. Coordinator Agent 通过 LLM 推理协调冲突（紧急优先、排队优先）
4. 执行协调后的最终决策

---

## Quick Start

```bash
# 克隆 + 安装
git clone https://github.com/afine907/smart-city-agent.git
cd smart-city-agent
pip install -e .

# 单路口仿真（规则引擎）
python -m traffic_agent.cli run --steps 200

# 多 Agent 仿真（CrewAI）
python -m traffic_agent.cli run --steps 200 --multi-agent

# 基准对比
python -m traffic_agent.cli benchmark --steps 300 --scenario morning_peak
```

---

## Benchmark 结果

早高峰场景（3x3 路口网格）：

| 指标 | 固定配时 | 规则引擎 | 改进 |
|------|---------|---------|------|
| 平均等待 (s) | 24.8 | 22.6 | **-8.8%** |
| 吞吐量 (/s) | 2.44 | 2.39 | -2.2% |

事故场景：

| 指标 | 固定配时 | 规则引擎 | 改进 |
|------|---------|---------|------|
| 平均等待 (s) | 22.0 | 23.3 | -5.9% |
| 吞吐量 (/s) | 1.60 | 1.79 | **+11.7%** |

---

## 内置场景

| 场景 | 说明 |
|------|------|
| `morning_peak` | 早高峰，南北方向重 |
| `evening_peak` | 晚高峰，东西方向重 |
| `normal` | 平峰，各方向均衡 |
| `pedestrian_heavy` | 行人高峰 |
| `accident` | 事故，救护车频繁 |
| `bicycle_rush` | 非机动车高峰 |

```bash
python -m traffic_agent.cli run --scenario morning_peak --steps 300
python -m traffic_agent.cli scenarios
```

---

## 项目结构

```
src/traffic_agent/
├── simulation/
│   ├── signal_controller.py   # 信号控制器 + 基线配时
│   ├── detector.py            # 检测器模型 + 趋势分析
│   ├── scenarios.py           # 交通场景定义
│   ├── sim_loop.py            # 仿真主循环
│   └── grid.py                # 3×3 网格仿真 (CrewAI)
├── crew/
│   ├── traffic_crew.py        # CrewAI 多 Agent 编排
│   └── coordination.py        # 冲突检测 + 绿波协调 + 优先级解决
├── tools/
│   └── traffic_tools.py       # CrewAI @tool 工具 (6 个)
├── llm/
│   ├── client.py              # LLM 客户端
│   ├── parser.py              # 决策解析
│   └── prompts.py             # Prompt 模板
├── optimization/
│   ├── rule_engine.py         # 规则引擎
│   ├── layered.py             # 3 级决策管道
│   └── cache.py               # 决策缓存
├── comparison/
│   └── benchmark.py           # 基准对比
└── cli.py                     # CLI 入口
```

---

## 测试

```bash
# 运行全部测试（267 个）
python -m pytest tests/ -v

# CrewAI 多 Agent 测试
python -m pytest tests/test_crew.py -v

# 信号控制器测试
python -m pytest tests/test_signal_controller.py -v

# 规则引擎测试
python -m pytest tests/test_timing_rules.py -v
```

---

## LLM 配置

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_API_BASE="https://api.openai.com/v1"
```

---

## License

MIT License - 详见 [LICENSE](LICENSE)
