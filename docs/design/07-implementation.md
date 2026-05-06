# 第7章 实施计划

## 总时间线：2 周出 Demo

```
Week 1: 深圳路网 + 仿真 + LLM 核心
├── Day 1-2: SUMO 环境 + 深圳路网准备
├── Day 3:   Sim Bridge + 指标采集
├── Day 4-5: LLM 决策 + 单路口 demo

Week 2: 评估 + 异常场景
├── Day 6:   基线控制器
├── Day 7-8: 异常场景注入 + 评估框架
├── Day 9:   运行实验 + 统计分析
└── Day 10:  整理 + 演示
```

## 阶段 1：SUMO + 深圳路网 (Day 1-2)

### Day 1: SUMO 环境

- [ ] 安装 SUMO (`apt install sumo sumo-tools`)
- [ ] 验证 TraCI Python 接口
- [ ] 用 SUMO 自带示例跑通基本流程

```bash
# 验收命令
sumo --version
python -c "import traci; print('TraCI OK')"
```

### Day 2: 深圳路网

- [ ] 下载深圳西丽留仙洞 OSM 数据
- [ ] netconvert 转换为 SUMO 路网
- [ ] 用 NETEDIT 修复路网问题
- [ ] 生成 3 种需求水平的路由
- [ ] 验证路网可运行

```bash
# 验收命令
python validate_shenzhen.py
# 应输出: Traffic lights: N, Edges: M, Vehicles remaining: K
```

**备选方案**：如果 OSM 数据质量太差，先用 SUMO 自带的十字路口示例，把 LLM 决策流程跑通，再换真实路网。

## 阶段 2：Sim Bridge (Day 3)

### 任务

- [ ] 实现 `read_intersection_state()` — 从 SUMO 读取路口状态
- [ ] 实现 `apply_decision()` — 将 LLM 决策应用到 SUMO
- [ ] 实现 `collect_metrics()` — 采集评估指标
- [ ] 单元测试

### 验收标准

```python
# 能跑通就算完成
state = read_intersection_state("tl_1")
assert "north" in state
assert "queue" in state["north"]

# 指标采集
metrics = collect_metrics()
assert "avg_wait" in metrics
assert "throughput" in metrics
```

## 阶段 3：LLM 决策 (Day 4-5)

### Day 4: LLM 客户端 + Prompt

- [ ] 实现 OpenAI 客户端（支持 GPT-4o）
- [ ] 设计 System Prompt（交通工程背景）
- [ ] 实现 ResponseParser（JSON 解析 + 验证）
- [ ] 实现降级策略（LLM 失败 → 规则回退）

### Day 5: 端到端 Demo

- [ ] 实现主循环（SUMO + LLM 决策）
- [ ] 处理 LLM 延迟（步长 10 秒）
- [ ] 单路口端到端 demo
- [ ] 基本的推理过程日志

### 验收标准

```python
# 单路口 LLM 控制 demo
controller = LLMController(OpenAIClient("gpt-4o"))
run_simulation("networks/shenzhen/shenzhen_medium.sumocfg", controller, steps=600)

# 输出：
# Step 0: NS_GREEN 30s (reasoning: 南北车多)
# Step 30: EW_GREEN 25s (reasoning: 东西车增长)
# ...
```

## 阶段 4：基线控制器 (Day 6)

### 任务

- [ ] 实现 FixedTimeController
- [ ] 实现 AdaptiveController
- [ ] 统一控制器接口
- [ ] 验证所有控制器可运行

### 验收标准

```python
for ctrl in [FixedTime(), Adaptive(), LLMController()]:
    metrics = run_experiment(config, ctrl)
    print(f"{ctrl.__class__.__name__}: avg_wait={metrics['avg_wait']:.1f}")
```

## 阶段 5：异常场景 + 评估 (Day 7-8)

### Day 7: 异常场景注入

- [ ] 实现事故场景（车道封闭）
- [ ] 实现紧急车辆场景
- [ ] 实现车流突增场景
- [ ] 验证场景注入可触发

### Day 8: 评估框架

- [ ] 实现 ExperimentRunner
- [ ] 实现统计检验（t-test + Cohen's d）
- [ ] 实现报告生成
- [ ] 跑一遍完整实验流程

### 验收标准

```python
runner = ExperimentRunner(
    scenarios=["normal", "accident", "emergency", "surge"],
    controllers={"fixed": FixedTime(), "adaptive": Adaptive(), "llm": LLMController()},
)
df = runner.run_all()
print(df.pivot_table(index="scenario", columns="controller", values="avg_wait"))
```

## 阶段 6：运行实验 (Day 9)

### 任务

- [ ] 运行所有实验（5 次取平均）
- [ ] 统计检验
- [ ] 分析结果
- [ ] 记录失败案例

### 验收标准

- p-value < 0.05（至少在异常场景下）
- 有明确的 LLM 优势场景和劣势场景
- 有消融实验结果

## 阶段 7：整理 + 演示 (Day 10)

### 任务

- [ ] 整理代码结构
- [ ] 写 README
- [ ] 录制演示视频（可选）
- [ ] 准备演示脚本

### 演示脚本

```bash
# 1. 正常场景
python -m traffic_agent run --network shenzhen --controller llm --scenario normal

# 2. 事故场景（LLM 优势）
python -m traffic_agent run --network shenzhen --controller llm --scenario accident

# 3. 对比报告
python -m traffic_agent evaluate --output report.html
```

## 风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| 深圳 OSM 数据质量差 | 中 | 高 | 先用 SUMO 示例路网 |
| SUMO 安装问题 | 低 | 高 | Docker 方案 |
| LLM 响应慢 | 中 | 中 | 步长 10s + 缓存 |
| LLM 效果不好 | 中 | 高 | 迭代 prompt + 规则约束 |
| 统计不显著 | 低 | 高 | 增加实验次数 + 聚焦异常场景 |
| 2 周时间不够 | 中 | 中 | 先做单路口，多路口后续 |

## 完成后的下一步

1. **扩展城市**：武汉、曼哈顿路网
2. **多路口协调**：路口间协调通信
3. **RL 基线**：训练一个 RL agent 作为更强基线
4. **论文写作**：整理实验结果，撰写论文
5. **开源发布**：整理代码，写 README，发布到 GitHub
