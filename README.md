# 🚦 LLM Traffic Controller

> **用大语言模型驱动的多Agent城市交通信号控制系统 — 支持真实 OpenStreetMap 路网**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-164%20passed-brightgreen.svg)](tests/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](Dockerfile)

```
┌─────────────────────────────────────────────────────────────────┐
│                 🚦 LLM Traffic Controller                       │
│                                                                 │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    │
│   │ 北路口  │◄──►│ 东路口  │◄──►│ 南路口  │◄──►│ 西路口  │    │
│   │ Agent   │    │ Agent   │    │ Agent   │    │ Agent   │    │
│   │ 🧠LLM   │    │ 🧠LLM   │    │ 🧠LLM   │    │ 🧠LLM   │    │
│   └────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘    │
│        │              │              │              │          │
│        └──────────────┼──────────────┼──────────────┘          │
│                       ▼                                        │
│            ┌─────────────────────┐                             │
│            │  协调层 (LLM)       │                             │
│            │  冲突检测 · 绿波协调 │                             │
│            └──────────┬──────────┘                             │
│                       │                                        │
│   ┌───────────────────▼───────────────────────────────────┐   │
│   │  📊 SSE Dashboard 实时展示推理过程                      │   │
│   │  "北方向排队23辆，延长南北绿灯15秒"                     │   │
│   └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## ✨ 为什么不一样？

| 对比项 | RL方案 | LLM方案（本项目）|
|--------|--------|-----------------|
| 训练成本 | GPU + 100K episode | **零训练** |
| 决策解释 | 黑盒 | **自然语言推理** |
| 异常处理 | 需重新训练 | **推理能力直接处理** |
| Agent协调 | 复杂奖励函数 | **自然语言对话** |
| 维护成本 | 高 | **更新 Prompt 即可** |
| 路网支持 | 固定网格 | **真实 OpenStreetMap 路网** |

## 🚀 Quick Start

```bash
# 克隆
git clone https://github.com/afine907/smart-city-agent.git
cd smart-city-agent

# 安装
pip install -e .

# 设置 API Key（支持 OpenAI 兼容 API）
export LONGCAT_API_KEY="your-api-key"
export LONGCAT_API_BASE="https://api.longcat.chat/openai"

# 运行单路口演示
python -m traffic_agent.cli run --steps 50

# 启动 SSE Dashboard
python -m traffic_agent.cli simulate --steps 200 --port 8080

# 对比 AI vs 固定配时
python -m traffic_agent.cli compare --steps 100

# 运行多场景测试
python -m traffic_agent.cli scenario morning_peak --mode compare
python -m traffic_agent.cli scenario accident --mode compare
```

### 🗺️ OpenStreetMap 路网仿真

```bash
# 运行曼哈顿时代广场路网
python -m traffic_agent.cli osm manhattan --steps 200

# 运行武汉光谷路网
python -m traffic_agent.cli osm wuhan --steps 200

# 带 Dashboard 的 OSM 仿真
python -m traffic_agent.cli simulate --preset manhattan --steps 200
```

内置两个预设路网：

| 预设 | 路口数 | 路段数 | 说明 |
|------|--------|--------|------|
| `manhattan` | 9 | 12 | 纽约时代广场 3×3 区域 |
| `wuhan` | 6 | 7 | 武汉光谷广场周边 |

```python
# Python API
from traffic_agent.simulation.osm_sim import OSMSimulation

sim = OSMSimulation.from_preset("manhattan")
sim = OSMSimulation.from_preset("wuhan")

# 从字典加载
sim = OSMSimulation.from_dict(data)

# 从 OSM API 加载（需安装 osmnx）
# sim = OSMSimulation.from_place("Wuhan, China")
```

### Docker 一键运行

```bash
docker build -t traffic-agent .
docker run -p 8080:8080 -e LONGCAT_API_KEY="your-key" traffic-agent
```

### Kubernetes 部署

```bash
# 一键部署（需要 kubectl + 集群）
export LONGCAT_API_KEY="your-key"
bash k8s/deploy.sh

# 或手动部署
kubectl apply -k k8s/

# 查看状态
kubectl -n traffic-agent get pods
kubectl -n traffic-agent port-forward svc/traffic-agent 8080:80
```

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                    TrafficControlCrew                         │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  CoordinationCrew                                       │ │
│  │  • MessageBus — Agent 间消息传递                         │ │
│  │  • ConflictDetector — 冲突检测（相位不一致、绿灯过长）   │ │
│  │  • LLM 协调 — 自然语言协商达成共识                      │ │
│  └─────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Agent（每个路口一个）                                   │ │
│  │  • 观察 → LLM 推理 → 决策                               │ │
│  │  • 支持缓存 + 规则引擎降级                              │ │
│  └─────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  决策管道（三层降级）                                    │ │
│  │  Layer 1: 规则引擎 (FREE) → 常规状态                    │ │
│  │  Layer 2: 决策缓存 (FREE) → 相似路况                    │ │
│  │  Layer 3: LLM 推理 (PAID) → 复杂决策                    │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                    仿真引擎                                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  GridSimulation    │  OSMSimulation                     │ │
│  │  • 3×3 固定网格    │  • 真实 OpenStreetMap 路网          │ │
│  │  • 等长道路        │  • Dijkstra 最短路径路由            │ │
│  │                    │  • 可变车道/限速                    │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## 📊 仿真场景

内置 4 个预设场景：

| 场景 | 说明 | 特点 |
|------|------|------|
| `morning_peak` | 早高峰 | 南北方向重，渐起→峰值→消退 |
| `normal` | 平峰 | 各方向均衡 |
| `accident` | 事故 | 救护车频繁，拥堵加剧 |
| `evening_peak` | 晚高峰 | 东西方向重 |

```bash
# 运行事故场景对比
python -m traffic_agent.cli scenario accident --mode compare

# 只跑 LLM 模式
python -m traffic_agent.cli scenario morning_peak --mode llm
```

## 💰 成本优化

三层决策管道自动选择最经济的决策方式：

```
决策路由:
  简单路况 → 规则引擎 (FREE, <1ms)
  相似路况 → 决策缓存 (FREE, <1ms)
  复杂路况 → 快速 LLM  ($0.001/次)
  协调决策 → 智能 LLM  ($0.01/次)

实测: 9 路口 × 300 步 ≈ 70%+ 免费决策
```

## 🧠 SSE Dashboard

实时展示每个 Agent 的推理过程：

```bash
# 启动 Dashboard（3×3 网格）
python -m traffic_agent.cli simulate --port 8080

# 启动 Dashboard（OSM 路网）
python -m traffic_agent.cli simulate --preset manhattan --port 8080

# 浏览器打开 http://localhost:8080
```

Dashboard 提供：
- 实时路况地图（支持 3×3 网格和 OSM 路网）
- Agent 推理过程流式展示
- 决策时间线
- 性能指标（等待时间、排队长度、吞吐量）

## 📁 项目结构

```
smart-city-agent/
├── src/traffic_agent/
│   ├── agents/              # Agent 基类 + 接口
│   ├── crew/                # CrewAI 编排 + 协调
│   ├── simulation/          # 仿真引擎
│   │   ├── engine.py        #   核心仿真数据结构
│   │   ├── grid.py          #   3×3 网格仿真
│   │   ├── osm.py           #   OpenStreetMap 路网加载
│   │   ├── osm_sim.py       #   OSM 路网仿真
│   │   └── router.py        #   Dijkstra 最短路径路由
│   ├── llm/                 # LLM 客户端 + 解析器
│   ├── optimization/        # 成本优化（缓存 + 规则 + 分层）
│   ├── comparison/          # 对比实验框架
│   ├── scenarios/           # 多场景预设
│   ├── visualization/       # SSE 事件 + Dashboard
│   ├── tools/               # Agent 工具（观察、通信、紧急）
│   └── cli.py               # CLI 入口
├── k8s/                    # Kubernetes 部署
├── tests/                   # 164 个测试
├── docs/                    # 设计文档
├── examples/                # 示例脚本
├── Dockerfile               # 容器化
└── docker-compose.yml       # 一键部署
```

## 🧪 测试

```bash
# 运行全部测试
python -m pytest tests/ -v

# 运行特定模块
python -m pytest tests/test_osm.py -v       # OSM 集成
python -m pytest tests/test_router.py -v    # 路由器
python -m pytest tests/test_grid.py -v      # 网格仿真
python -m pytest tests/test_scenarios.py -v # 场景测试
```

## 📝 License

MIT License
