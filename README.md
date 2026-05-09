# LLM Traffic Timing Assistant

> **用大语言模型微调红绿灯读秒 — 每次只调 ±10s，累计提升路口效率 15-25%**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-248%20passed-brightgreen.svg)](tests/)

## 项目定位

不是重新发明红绿灯，而是给已有的红绿灯装一个 **AI 微调层**。

基于路口检测器的实时数据（车辆、行人、非机动车），LLM 用自然语言推理来微调读秒时间。每次调整都有完整的推理日志，可供交通工程师分析和优化。

```
基线配时: NS 绿灯 60s | EW 绿灯 90s | 黄灯 3s
                    │
        ┌───────────▼───────────┐
        │    检测器数据感知      │
        │  车辆排队 · 行人等待   │
        │  非机动车 · 流量趋势   │
        └───────────┬───────────┘
                    │
        ┌───────────▼───────────┐
        │    3 级决策管道        │
        │  L1: 规则引擎 (免费)   │
        │  L2: 决策缓存 (免费)   │
        │  L3: LLM 推理 (付费)   │
        └───────────┬───────────┘
                    │
        ┌───────────▼───────────┐
        │    安全约束夹紧        │
        │  ±10s · 最小15s · 最大90s │
        └───────────┬───────────┘
                    │
            最终配时 ± 推理说明
```

## Quick Start

```bash
# 克隆 + 安装
git clone https://github.com/afine907/smart-city-agent.git
cd smart-city-agent
pip install -e .

# 运行仿真（无需 LLM，规则引擎驱动）
python -m traffic_agent.cli run --steps 200

# 运行仿真（带 LLM 微调）
export LONGCAT_API_KEY="your-api-key"
export LONGCAT_API_BASE="https://api.longcat.chat/openai"
python -m traffic_agent.cli run --steps 200 --llm

# 运行基准对比：固定 vs 规则 vs LLM
python -m traffic_agent.cli benchmark --steps 500

# 查看可用场景
python -m traffic_agent.cli scenarios
```

## 决策管道

三层降级，最大化免费决策比例：

| 层级 | 成本 | 延迟 | 适用场景 |
|------|------|------|----------|
| L1 规则引擎 | 免费 | <1ms | 低流量、高排队、行人等待等明确模式 |
| L2 决策缓存 | 免费 | <1ms | 相似交通状态复用历史决策 |
| L3 LLM 推理 | ~$0.001/次 | ~1s | 复杂场景，需要语义推理 |

实测：约 70%+ 决策由规则引擎和缓存处理，LLM 调用率 < 30%。

## 仿真场景

内置 6 个预设场景：

| 场景 | 说明 | 特点 |
|------|------|------|
| `morning_peak` | 早高峰 | 南北方向重，渐起 → 峰值 → 消退 |
| `evening_peak` | 晚高峰 | 东西方向重 |
| `normal` | 平峰 | 各方向均衡 |
| `pedestrian_heavy` | 行人高峰 | 行人过街需求大 |
| `accident` | 事故 | 救护车频繁，拥堵加剧 |
| `bicycle_rush` | 非机动车高峰 | 早晚高峰自行车潮 |

```bash
# 指定场景运行
python -m traffic_agent.cli run --scenario morning_peak --steps 300

# 指定路口类型
python -m traffic_agent.cli run --type tjunction --steps 200

# 导出决策日志
python -m traffic_agent.cli run --steps 200 --export log.json
```

## 路口类型

| 类型 | 相位方案 | 默认配时 |
|------|----------|----------|
| 十字路口 (`crossroad`) | NS → 黄灯 → 全红 → EW → 黄灯 → 全红 | NS: 60s, EW: 90s |
| 丁字路口 (`tjunction`) | NS → 黄灯 → 全红 → EW → 黄灯 | NS: 45s, EW: 35s |

## Benchmark

```bash
# 运行 3 策略对比
python -m traffic_agent.cli benchmark --steps 500 --scenario morning_peak

# 输出示例:
# ======================================================================
#   Timing Adjustment Benchmark
#   Intersection: crossroad | Scenario: morning_peak
# ======================================================================
#
#   Metric                      fixed         rule      pipeline
#   ---------------------------------------------------------
#   Avg Wait (s)                25.30         18.20         15.80
#   Throughput (/s)              0.42          0.55          0.61
#   ...
#
#   Improvements (vs fixed):
#     rule_avg_wait: +28.1%
#     pipeline_avg_wait: +37.5%
```

## Python API

```python
from traffic_agent.simulation.sim_loop import TimingSimulation
from traffic_agent.optimization.layered import TimingDecisionPipeline
from traffic_agent.scenarios import create_scenario
from traffic_agent.scenarios.runner import ScenarioRunner

# 方式 1: 直接运行仿真
sim = TimingSimulation(
    intersection_type="crossroad",
    scenario_name="morning_peak",
    pipeline=None,  # None = 固定配时
    seed=42,
)
report = sim.run(steps=500)
print(f"平均等待: {report.avg_wait_time:.1f}s, 吞吐量: {report.throughput:.3f}/s")

# 方式 2: 使用 ScenarioRunner 对比
scenario = create_scenario("morning_peak")
runner = ScenarioRunner(scenario)
fixed = runner.run_fixed()
rule = runner.run_rule()

# 方式 3: 导出决策日志
sim.export_log("decision_log.json")
```

## 项目结构

```
src/traffic_agent/
├── simulation/
│   ├── signal_controller.py   # 信号控制器 + 基线配时 + ±10s 调整
│   ├── detector.py            # 检测器模型 + 趋势分析
│   ├── scenarios.py           # 交通场景定义（6 个预设）
│   ├── sim_loop.py            # 仿真主循环
│   ├── engine.py              # 基础仿真数据结构
│   ├── grid.py                # 3×3 网格仿真
│   └── osm*.py                # OpenStreetMap 路网仿真
├── llm/
│   ├── client.py              # LLM 客户端（OpenAI 兼容）
│   ├── parser.py              # TimingAdjustment 解析 + 验证
│   └── prompts.py             # LLM Prompt 模板
├── optimization/
│   ├── rule_engine.py         # 规则引擎（6 条规则）
│   ├── layered.py             # 3 级决策管道
│   ├── cache.py               # LRU + TTL 决策缓存
│   └── cost_tracker.py        # LLM 调用成本追踪
├── scenarios/
│   ├── presets.py             # 多场景配置（4 个旧预设）
│   └── runner.py              # 场景运行器
├── comparison/
│   └── benchmark.py           # 基准对比框架
├── visualization/             # SSE 事件 + Dashboard
├── api/                       # FastAPI SSE 服务器
└── cli.py                     # CLI 入口
```

## 测试

```bash
# 运行全部测试（248 个）
python -m pytest tests/ -v

# 运行新模块测试
python -m pytest tests/test_signal_controller.py tests/test_detector.py tests/test_timing_rules.py tests/test_sim_loop.py -v

# 覆盖率
python -m pytest tests/ --cov=traffic_agent
```

## LLM 配置

支持 OpenAI 兼容 API（LongCat、OpenAI、Azure 等）：

```bash
# 环境变量
export OPENAI_API_KEY="your-key"
export OPENAI_API_BASE="https://api.openai.com/v1"

# 或使用 LongCat
export LONGCAT_API_KEY="your-key"
export LONGCAT_API_BASE="https://api.longcat.chat/openai"
```

LLM 客户端会自动加载项目根目录的 `.env` 文件。

## License

MIT License
