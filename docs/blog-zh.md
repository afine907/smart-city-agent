# 用 LLM 多 Agent 控制城市交通信号灯：从零到一的架构设计与实战

> 我做了一个项目：用大语言模型驱动多 Agent 协调控制城市交通信号灯。不是 demo，不是玩具，是能跑真实 OpenStreetMap 路网的完整系统。

## 为什么要做这个？

现有交通信号控制系统（SCATS、SCOOT、InSync）有一个共同问题：**它们是规则驱动的，不是智能驱动的。**

- SCATS：根据检测器数据调整绿信比，本质上是 PID 控制器
- SCOOT：实时自适应，但依赖固定规则树
- 这些系统在"正常交通"下表现不错，但面对**突发事件、异常车流、紧急车辆**时，反应迟钝

LLM 的优势在于**推理能力**——它能理解"现在是周五晚高峰 + 附近有演唱会散场 + 有救护车需要通过"这种复合场景，然后做出协调决策。

## 架构设计

```
┌─────────────────────────────────────────────────┐
│              LLM Traffic Controller              │
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Intersection│  │ Intersection│  │ Intersection│  │
│  │ Agent (A) │  │ Agent (B) │  │ Agent (C) │      │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘      │
│        │              │              │            │
│        └──────────────┼──────────────┘            │
│                       │                          │
│              ┌────────▼────────┐                 │
│              │  Coordinator    │                 │
│              │  (Conflict      │                 │
│              │   Resolution)   │                 │
│              └─────────────────┘                 │
│                                                  │
├─────────────────────────────────────────────────┤
│              3-Layer Degradation                  │
│                                                  │
│  Layer 1: Rule Engine (0ms)                      │
│    ↓ LLM unavailable?                            │
│  Layer 2: Cache Hit (<1ms)                       │
│    ↓ Cache miss?                                 │
│  Layer 3: LLM API (100-500ms)                    │
│                                                  │
└─────────────────────────────────────────────────┘
```

### 核心组件

**1. Intersection Agent（路口 Agent）**

每个路口一个独立 Agent，负责：
- 观察当前交通状态（队列长度、等待时间、紧急车辆）
- 调用 LLM 推理最优信号相位
- 执行信号变更

**2. Coordinator（协调器）**

多 Agent 协调的关键：
- 检测相邻路口的信号冲突
- 当两个相邻路口同时给同一方向绿灯时，触发协调
- 使用优先级仲裁（紧急车辆 > 队列长度 > 等待时间）

**3. 3 层降级机制**

这是生产化的关键。LLM API 不可能 100% 可用，所以：
- **Layer 1**：规则引擎（0ms 延迟）— 固定配时方案
- **Layer 2**：缓存命中（<1ms）— 历史最优决策复用
- **Layer 3**：LLM API（100-500ms）— 真正的 AI 推理

## 实现细节

### OpenStreetMap 路网集成

支持从真实 OSM 数据加载路网：

```python
# 从预设加载
sim = OSMSimulation.from_preset("shenzhen")  # 深圳留仙洞

# 从 OSM API 加载
sim = OSMSimulation.from_place("Manhattan, New York")

# 从 GeoJSON 加载
sim = OSMSimulation.from_dict(geojson_data)
```

**Dijkstra 最短路径路由**：车辆自动生成目的地，沿最短路径行驶。

### Dashboard 实时可视化

基于 SSE（Server-Sent Events）的实时 Dashboard：
- SVG 动态拓扑渲染（支持任意 OSM 路网）
- 实时事件流（thinking/decision/conflict/coordination）
- 性能指标面板（事件数、决策数、冲突数、平均延迟）

### Benchmark 结果

在真实路网上对比三种策略：

**深圳留仙洞（9 路口）：**

| 策略 | 平均等待 | P95 等待 | 吞吐量 |
|------|---------|---------|--------|
| Fixed Timing | 2.9s | 6.4s | 3.65 |
| Adaptive Rules | 9.0s | 20.5s | 5.20 |
| Random | 6.4s | 15.7s | 0.84 |

**纽约曼哈顿（9 路口）：**

| 策略 | 平均等待 | P95 等待 | 吞吐量 |
|------|---------|---------|--------|
| Fixed Timing | 31.9s | 94.9s | 3.21 |
| Adaptive Rules | 31.1s | 129.1s | 5.60 |
| Random | 31.1s | 92.6s | 0.84 |

**关键发现：**
- Adaptive Rules 的吞吐量比 Fixed 高 42-75%，但 P95 等待时间也更高
- 这说明**自适应策略以牺牲部分车辆的等待时间为代价，换取整体吞吐量提升**
- LLM 策略的优势在于**处理异常场景**（紧急车辆、事故、特殊事件），这在正常 benchmark 中体现不出来

## 技术栈

- **Python 3.10+** — 全 Python 实现
- **FastAPI + SSE** — 实时事件流
- **Dijkstra 路由** — 最短路径算法
- **OpenStreetMap** — 真实路网数据
- **Kubernetes** — 生产部署
- **167 个测试** — 完整测试覆盖

## 开源地址

**GitHub**: https://github.com/afine907/smart-city-agent

**Star ⭐ 支持一下！**

## 下一步

1. 接入真实 LLM API，跑完整的 LLM vs 规则对比
2. 支持更多城市路网
3. 推理质量评分（量化 LLM 决策质量）
4. 实时 Dashboard GIF 展示

---

*如果你对 AI + 交通感兴趣，欢迎 Star、Fork、提 Issue！*
