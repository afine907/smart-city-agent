# Code Review Report — 100轮迭代进化

**审查日期**: 2026-05-29
**审查范围**: 57个变更文件（10个新增模块、15个修改文件、15个新增测试、17个文档/配置）
**审查方法**: 双Agent并行审查（新模块 + 修改文件/测试）

---

## 🔴 Critical / High Severity (必须修复)

### BUG-1: `sse_server.py:373` — GridSimulation 启动时 AttributeError

**文件**: `src/traffic_agent/api/sse_server.py:372-373`
**严重性**: Critical

```python
if hasattr(sim, "intersections") and hasattr(sim, "segments"):
    osm_ix = sim.osm.intersections  # GridSimulation 没有 .osm 属性！
```

当 `preset=None` 时创建 `GridSimulation`，它有 `intersections` 和 `segments` 属性，但没有 `.osm` 属性。通过 Dashboard 启动本地仿真会直接崩溃。

**修复**: 添加 `hasattr(sim, "osm")` 检查。

---

### BUG-2: `control.py:156,171,175` — 后台线程状态竞态条件

**文件**: `src/traffic_agent/simulation/control.py:156,171,175`
**严重性**: High

```python
# 后台线程中（未持有 _lock）:
self._set_state(SimulationState.PAUSED)   # line 156
self._set_state(SimulationState.STOPPED)  # line 171
self._set_state(SimulationState.IDLE)     # line 175
```

`_set_state` 写入 `self.state` 并调用回调，但未持有 `_lock`。主线程的 `pause()/resume()/stop()` 也在操作状态，导致竞态条件。

**修复**: 将 `_set_state` 调用包裹在 `self._lock` 中。

---

### BUG-3: `control.py:167-168` — ZeroDivisionError

**文件**: `src/traffic_agent/simulation/control.py:167-168`
**严重性**: High

```python
if self.speed_multiplier < 1.0:
    time.sleep(0.01 / self.speed_multiplier)  # speed_multiplier=0 时崩溃
```

**修复**: 添加 `speed_multiplier > 0` 验证。

---

### BUG-4: `metrics.py:82-118` — Prometheus 输出格式不合规

**文件**: `src/traffic_agent/api/metrics.py:82-118`
**严重性**: High

- 每个 label 组合都输出 `# TYPE` 行（应每种 metric 只输出一次）
- 缺少 `# HELP` 行
- 缺少 `+Inf` histogram bucket

**修复**: 按 Prometheus exposition format 规范重构输出。

---

### BUG-5: `layered.py:91` — 缓存对象被污染

**文件**: `src/traffic_agent/optimization/layered.py:91`
**严重性**: High

```python
cached.source = "cache"  # 直接修改缓存中的对象！
```

后续所有缓存命中都会错误地报告 `source="cache"`，即使原始来源是 rule engine。

**修复**: 返回前创建浅拷贝 `copy = cached.__class__(**cached.__dict__); copy.source = "cache"`。

---

### BUG-6: `test_cli.py:139` — Windows 不兼容

**文件**: `tests/test_cli.py:139`
**严重性**: High

```python
"--output", "/dev/null",  # Windows 上不存在！
```

**修复**: 使用 `os.devnull` 或 `tmp_path` fixture。

---

## 🟡 Medium Severity (应该修复)

### BUG-7: `statistics.py:187-188` — 百分位数计算不准确

**文件**: `src/traffic_agent/optimization/statistics.py:187-188`
**严重性**: Medium

```python
p95_idx = int(len(sorted_q) * 0.95)
stats.queue_95th_percentile = sorted_q[min(p95_idx, len(sorted_q) - 1)]
```

小样本时结果系统性偏高（n=2 时返回最大值）。

**修复**: 使用 `numpy.percentile` 或文档说明是近似值。

---

### BUG-8: `statistics.py:46` — `avg_phase_duration` 从未计算

**文件**: `src/traffic_agent/optimization/statistics.py:46`
**严重性**: Medium

`TrafficStatistics.avg_phase_duration` 永远为 0.0，`StatisticsCollector` 没有 `record_phase_duration()` 方法。

**修复**: 添加 `record_phase_duration()` 方法或删除该字段。

---

### BUG-9: `auth.py:92-116` — 限流器竞态条件

**文件**: `src/traffic_agent/api/auth.py:92-116`
**严重性**: Medium

`check_rate_limit` 读取、过滤、检查、追加操作非原子，并发请求可能超过限制。

**修复**: 使用 `threading.Lock` 保护。

---

### BUG-10: `persistence.py:79` — 每次插入都 commit

**文件**: `src/traffic_agent/visualization/persistence.py:79`
**严重性**: Medium

```python
self.conn.commit()  # 每次 store_event 都 commit，性能瓶颈
```

**修复**: 使用 `PRAGMA journal_mode=WAL` 或批量 commit。

---

### BUG-11: `persistence.py:28-30` — SQLite 连接泄漏

**文件**: `src/traffic_agent/visualization/persistence.py:28-30`
**严重性**: Medium

`_create_tables()` 失败时连接不会关闭。

**修复**: 添加 try/except 关闭连接。

---

### BUG-12: `logging_config.py:45` — 无日志轮转

**文件**: `src/traffic_agent/logging_config.py:45`
**严重性**: Medium

```python
file_handler = logging.FileHandler(log_file, encoding="utf-8")  # 无大小限制
```

**修复**: 使用 `RotatingFileHandler`。

---

### BUG-13: `metrics.py:49` — Histogram 无限增长

**文件**: `src/traffic_agent/api/metrics.py:49`
**严重性**: Medium

```python
self._histograms[key].append(value)  # 无上限
```

长时间运行会导致内存泄漏。

**修复**: 使用 T-digest 或滑动窗口。

---

### BUG-14: `control.py:172` — `raise e` 丢失 traceback

**文件**: `src/traffic_agent/simulation/control.py:172`
**严重性**: Low-Medium

```python
raise e  # 应该用 bare `raise`
```

**修复**: 改为 `raise`。

---

### BUG-15: `traffic_crew.py:121-123` — 工具切片错误

**文件**: `src/traffic_agent/crew/traffic_crew.py:121-123`
**严重性**: Medium

```python
self.coordinator_tools = all_tools[:3]  # 注释说应该包含 check_conflicts，但索引4被排除
```

**修复**: 按名称或正确索引分配工具。

---

### BUG-16: `sse_server.py:531` — 使用废弃 API

**文件**: `src/traffic_agent/api/sse_server.py:531`
**严重性**: Medium

```python
loop = asyncio.get_event_loop()  # Python 3.10+ 已废弃
```

**修复**: 改为 `asyncio.get_running_loop()`。

---

### BUG-17: `client.py:108-112` — 每次调用创建新 client

**文件**: `src/traffic_agent/llm/client.py:108-112`
**严重性**: Medium

```python
client = openai.OpenAI(...)  # 每次 chat() 都创建新实例
```

**修复**: 在 `__init__` 中创建一次并复用。

---

### BUG-18: `client.py:49` — 每次 LLMConfig 都加载 .env

**文件**: `src/traffic_agent/llm/client.py:49`
**严重性**: Low-Medium

```python
def __post_init__(self):
    load_env()  # 每次实例化都解析 .env 文件
```

**修复**: 使用模块级标志只加载一次。

---

## 🟢 Low Severity (建议修复)

### BUG-19: `auth.py:61` — 使用 MD5 生成 key ID

**文件**: `src/traffic_agent/api/auth.py:61`
**严重性**: Low

虽然不是安全用途，但可能无法通过安全审计。

**修复**: 改用 `hashlib.sha256` 或 `secrets.token_hex(4)`。

---

### BUG-20: `metrics.py:131` — Label 值未转义

**文件**: `src/traffic_agent/api/metrics.py:131`
**严重性**: Low

如果 label 值包含 `"` 或 `\`，输出会格式错误。

**修复**: 转义特殊字符。

---

### BUG-21: `persistence.py:122` — 排序不稳定

**文件**: `src/traffic_agent/visualization/persistence.py:122`
**严重性**: Low

```python
query += " ORDER BY timestamp DESC LIMIT ?"
```

相同 timestamp 的事件顺序不确定。

**修复**: 改为 `ORDER BY timestamp DESC, id DESC`。

---

### BUG-22: `rule_only.py:34` — `free_rate` 硬编码

**文件**: `src/traffic_agent/optimization/rule_only.py:34`
**严重性**: Low

```python
"free_rate": 1.0,  # 永远是 1.0，语义不清晰
```

---

### BUG-23: `strategies.py:19` — adjustment 无验证

**文件**: `src/traffic_agent/optimization/strategies.py:19`
**严重性**: Low

注释说 `±10s max`，但无代码验证。

---

### INCONSISTENCY-1: `cache.py:64` — 类型标注不准确

**文件**: `src/traffic_agent/optimization/cache.py:64`
**严重性**: Low

缓存返回类型标注为 `TimingAdjustment`，但 `traffic_crew.py` 存储的是 `TrafficDecision`。

---

### INCONSISTENCY-2: `runner.py:10` — 不必要的耦合

**文件**: `src/traffic_agent/scenarios/runner.py:10`
**严重性**: Low

从 `benchmark.py` 导入 `SimulationReport`，应直接从 `sim_loop.py` 导入。

---

### INCONSISTENCY-3: `grid.py:210-214` — 访问私有属性

**文件**: `src/traffic_agent/simulation/grid.py:210-214`
**严重性**: Low

直接操作 `SignalController` 的私有属性，应提供公共方法。

---

## 🧪 测试质量问题

### TEST-1: `test_layered.py` — 缓存路径未真正测试

测试数据触发了 rule engine，缓存命中路径从未被执行。

### TEST-2: `test_layered.py` — 缺少 LLM mock

如果规则未命中，会尝试真实 LLM API 调用。

### TEST-3: `test_control.py` — 依赖 `time.sleep` 的不稳定测试

固定 sleep 在慢 CI 上可能导致 flaky。

### TEST-4: `test_metrics.py` — 全局状态泄漏

测试之间共享全局 `MetricsCollector`，无重置。

### TEST-5: `test_api.py` — 全局状态未完全重置

缺少 `_sim_state`, `_network_topology`, `_crew`, `_sim` 的重置。

### TEST-6: `test_logging.py` — 修改 root logger

影响测试进程中所有其他 logger。

---

## 📊 覆盖率缺口

| 缺口 | 描述 |
|------|------|
| SSE 流式端点 | `/api/events/stream` 和 `/api/crewai/stream` 未测试 |
| 缓存 TTL 过期 | 无测试验证缓存条目在 TTL 后过期 |
| LLM 错误处理 | `client.py` 的异常回退路径未测试 |
| 零步仿真 | 无测试 `steps=0` 的边界情况 |
| 多智能体模式 | CLI `--multi-agent` 未测试 |
| 信号决策验证 | `_validate_signal_decision` 未测试 |

---

## ✅ 修复优先级建议

### P0 — 立即修复（影响功能）
1. BUG-1: `sse_server.py` GridSimulation AttributeError
2. BUG-5: `layered.py` 缓存对象污染
3. BUG-6: `test_cli.py` Windows 不兼容

### P1 — 尽快修复（影响稳定性）
4. BUG-2: `control.py` 状态竞态条件
5. BUG-3: `control.py` ZeroDivisionError
6. BUG-4: `metrics.py` Prometheus 格式不合规
7. BUG-15: `traffic_crew.py` 工具切片错误

### P2 — 计划修复（影响性能/可维护性）
8. BUG-7~18: 其他 Medium severity 问题
9. TEST-1~6: 测试质量问题
10. 覆盖率缺口补充

---

## 📝 总结

本次 100 轮迭代进化在**功能丰富度**和**测试数量**上取得了显著进展（267→416 测试），但在**代码健壮性**和**并发安全**方面存在需要修复的问题。主要风险集中在：

1. **API 服务器**的 GridSimulation 启动路径有崩溃 bug
2. **仿真控制器**的多线程状态管理有竞态条件
3. **Prometheus 指标**输出格式不合规
4. **缓存层**会污染返回对象

建议按 P0→P1→P2 优先级依次修复，预计需要 15-20 个额外 commit。
