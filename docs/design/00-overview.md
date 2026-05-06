# 第0章 核心问题与总体方案

> **一个 LLM 能不能比传统方法更好地控制交通信号灯？**

## 问题定义

要回答这个问题，系统只需要做三件事：

1. **仿真**：模拟真实的车流
2. **决策**：LLM 观察状态 → 输出信号方案
3. **评估**：LLM 方案 vs 传统方案，谁更好

## 总体架构

```
┌──────────────────────────────────────────────────┐
│                  评估层 (Evaluation)              │
│   对比指标 · 实验设计 · 可视化报告                  │
└───────────────────┬──────────────────────────────┘
                    │
┌───────────────────▼──────────────────────────────┐
│                LLM Agent 层                       │
│   Prompt · Tool Use · Memory · CoT Reasoning      │
│   GPT-4o / Claude / Qwen                        │
└───────────────────┬──────────────────────────────┘
                    │
┌───────────────────▼──────────────────────────────┐
│              仿真接口层 (Sim Bridge)              │
│   状态编码 · 动作映射 · 奖励计算                    │
│   Python (traci / CityFlow API)                  │
└───────────────────┬──────────────────────────────┘
                    │
┌───────────────────▼──────────────────────────────┐
│              交通仿真层 (Simulation)              │
│   SUMO: 车辆物理 · 信号控制 · 路由 · 碰撞          │
│   C++ 引擎，Python 通过 TraCI 控制                │
└───────────────────┬──────────────────────────────┘
                    │
┌───────────────────▼──────────────────────────────┐
│              路网层 (Road Network)                │
│   OSM 导入 · netconvert 转换 · 信号灯程序定义       │
└──────────────────────────────────────────────────┘
```

## 核心假设（聚焦）

**LLM 在异常场景下比传统方法更好。**

常规均匀车流下，自适应控制已经很有效。LLM 的真正优势在于：
- 事故/施工导致车道封闭
- 大型活动（演唱会、体育赛事）突发拥堵
- 紧急车辆需要优先通行
- 多路口协调的全局优化

评估重点放在**异常场景 vs 常常场景**的对比。

## 设计原则

1. **用成熟工具，不造轮子** — SUMO 有 20 年历史，被几千篇论文验证过
2. **LLM 是推理引擎，不是分类器** — 用 Tool Use + CoT，不用 RL
3. **评估驱动** — 一切以数据说话，LLM 方案必须在指标上胜出
4. **最小可行** — 核心代码 < 500 行，2 周出 demo
5. **先单路口后多路口** — 先验证单路口假设，再扩展协调

## 各层最佳选择

| 层 | 选择 | 理由 |
|---|------|------|
| 仿真 | SUMO | 20 年历史，社区大，文档全，C++ 引擎性能好 |
| LLM | Tool Use + CoT | 零训练，可解释，能处理异常 |
| 路网 | OSM → netconvert | 真实路网，非玩具 |
| 评估 | 标准化指标 | 平均延迟、吞吐量、排队长度、紧急响应 |

## 最小可行代码

```python
import traci
from openai import OpenAI

# 1. 启动 SUMO
traci.start(["sumo", "-c", "shenzhen.sumocfg"])

# 2. LLM 决策函数
def llm_decide(intersection_state: dict) -> int:
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": f"当前交通状态: {intersection_state}\n请选择相位(0-3)并解释原因"
        }]
    )
    return parse_phase(response)

# 3. 主循环（步长 10s，匹配 LLM 延迟）
while traci.simulation.getMinExpectedNumber() > 0:
    state = read_intersection_state("intersection_1")
    phase = llm_decide(state)
    traci.trafficlight.setPhase("intersection_1", phase)
    # 推进 10 步（10 秒），LLM 每 10 秒决策一次
    for _ in range(10):
        traci.simulationStep()

traci.close()
```

## LLM 延迟应对

LLM 响应通常 1-3 秒，不能每秒调用。策略：

| 策略 | 说明 |
|------|------|
| 步长放大 | 仿真步长 10-15 秒，匹配 LLM 延迟 |
| 高层规划 | LLM 每 60 秒做一次规划，中间用规则微调 |
| 并发调用 | 多路口并行请求（asyncio） |
| 缓存 | 相似状态复用历史决策 |

## 与现有架构的差异

现有项目走了一些弯路：

| 问题 | 现状 | 应该 |
|------|------|------|
| 仿真器 | 自研轻量仿真器 | SUMO（更真实、更标准） |
| Agent框架 | CrewAI 多Agent协调 | 简单 Tool Use 调用 |
| 路网 | 自研 grid/OSM 轻量实现 | SUMO + OSM netconvert |
| 复杂度 | 多层抽象、多模块 | 聚焦核心：仿真→决策→评估 |

**关键认知**：真正的难度不在技术栈，在于**实验设计是否严谨、评估指标是否合理、LLM prompt 是否有效**。
