# 第15章 部署与运维设计

> **能跑 demo 和能稳定运行 7×24 小时，是两个完全不同的工程。**

## 部署目标

| 目标 | 要求 |
|------|------|
| 可用性 | 99.9%（全年停机 < 8.76 小时） |
| 延迟 | 单路口决策 < 5 秒 |
| 恢复时间 | 故障后 < 30 秒自动恢复 |
| 数据保留 | 决策日志保留 90 天 |
| 扩展性 | 支持 100+ 路口 |

---

## 1. 部署架构

### 1.1 三层架构

```
┌─────────────────────────────────────────────────────────┐
│                    接入层 (Edge)                          │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ 路口网关  │  │ 路口网关  │  │ 路口网关  │  ...       │
│  │ (每路口)  │  │ (每路口)  │  │ (每路口)  │             │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘             │
│       │             │             │                     │
└───────┼─────────────┼─────────────┼─────────────────────┘
        │             │             │
┌───────▼─────────────▼─────────────▼─────────────────────┐
│                    计算层 (Cloud)                         │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ LLM 服务  │  │ 协调服务  │  │ 数据服务  │             │
│  │ (决策)    │  │ (多路口)  │  │ (存储)    │             │
│  └──────────┘  └──────────┘  └──────────┘             │
│                                                         │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│                    展示层 (Dashboard)                     │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ Web UI   │  │ 移动端    │  │ 大屏投放  │             │
│  └──────────┘  └──────────┘  └──────────┘             │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 1.2 路口网关

每个路口部署一个轻量级网关，负责：
- 从 SUMO/信号控制器采集数据
- 调用 LLM 服务获取决策
- 将决策下发到信号控制器
- 本地缓存（LLM 不可用时降级）

```python
@dataclass
class IntersectionGateway:
    """路口网关——部署在路口附近。"""
    gateway_id: str
    intersection_id: str
    
    # 连接
    sumo_host: str            # SUMO/信号控制器地址
    llm_service_url: str      # LLM 服务地址
    
    # 本地缓存
    local_cache_size: int = 100  # 缓存最近 100 个决策
    fallback_mode: str = "rule_engine"  # 降级模式
    
    # 心跳
    heartbeat_interval: float = 10.0  # 心跳间隔 (s)
    health_check_timeout: float = 5.0  # 健康检查超时 (s)
```

---

## 2. 容器化部署

### 2.1 Docker Compose（开发/测试）

```yaml
# docker-compose.yml
version: '3.8'

services:
  # SUMO 仿真器
  sumo:
    image: eclipse-sumo/sumo:1.19.0
    volumes:
      - ./networks:/sumo/networks
    ports:
      - "8813:8813"  # TraCI 端口

  # LLM 决策服务
  llm-service:
    build: ./src/traffic_agent/llm
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - MODEL=gpt-4o
      - MAX_RETRIES=3
    ports:
      - "8080:8080"
    depends_on:
      - redis

  # 协调服务
  coordinator:
    build: ./src/traffic_agent/coordination
    ports:
      - "8081:8081"
    depends_on:
      - llm-service
      - redis

  # Redis (缓存 + 消息队列)
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data

  # PostgreSQL (持久化)
  postgres:
    image: postgres:16-alpine
    environment:
      - POSTGRES_DB=traffic
      - POSTGRES_USER=traffic
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - pg-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  # Dashboard
  dashboard:
    build: ./dashboard
    ports:
      - "3000:3000"
    depends_on:
      - coordinator

volumes:
  redis-data:
  pg-data:
```

### 2.2 Kubernetes（生产）

```yaml
# k8s/llm-service.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: llm-service
  template:
    metadata:
      labels:
        app: llm-service
    spec:
      containers:
      - name: llm-service
        image: traffic-agent/llm-service:latest
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: api-keys
              key: openai-key
        ports:
        - containerPort: 8080
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: llm-service
spec:
  selector:
    app: llm-service
  ports:
  - port: 8080
    targetPort: 8080
  type: ClusterIP
```

---

## 3. 监控告警

### 3.1 监控指标

| 类别 | 指标 | 告警阈值 |
|------|------|---------|
| **系统** | CPU 使用率 | > 80% |
| **系统** | 内存使用率 | > 85% |
| **系统** | 磁盘使用率 | > 90% |
| **系统** | 网络延迟 | > 100ms |
| **LLM** | API 延迟 | > 5s |
| **LLM** | 成功率 | < 95% |
| **LLM** | 降级频率 | > 3 次/小时 |
| **交通** | 排队长度 | > 30 辆 |
| **交通** | 平均延误 | > 60s |
| **交通** | 事件检测 | 实时 |

### 3.2 Prometheus + Grafana

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'llm-service'
    static_configs:
      - targets: ['llm-service:8080']
    metrics_path: /metrics

  - job_name: 'coordinator'
    static_configs:
      - targets: ['coordinator:8081']
    metrics_path: /metrics

  - job_name: 'gateway'
    static_configs:
      - targets: ['gateway:9090']
    metrics_path: /metrics
```

### 3.3 告警规则

```yaml
# alerts.yml
groups:
  - name: traffic-agent
    rules:
      - alert: LLMServiceDown
        expr: up{job="llm-service"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "LLM 服务不可用"

      - alert: LLMHighLatency
        expr: llm_request_duration_seconds{quantile="0.99"} > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "LLM 延迟过高"

      - alert: LLMHighFailureRate
        expr: rate(llm_requests_total{status="error"}[5m]) / rate(llm_requests_total[5m]) > 0.05
        for: 5m
        labels:
          severity: error
        annotations:
          summary: "LLM 失败率过高"

      - alert: IntersectionQueueTooLong
        expr: intersection_queue_length > 30
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "路口排队过长"

      - alert: AgentOffline
        expr: agent_heartbeat_last_seen_seconds > 30
        for: 1m
        labels:
          severity: error
        annotations:
          summary: "Agent 离线"
```

---

## 4. 日志与审计

### 4.1 日志分级

| 级别 | 内容 | 保留期 | 用途 |
|------|------|--------|------|
| DEBUG | 详细调试信息 | 7 天 | 开发调试 |
| INFO | 正常运行日志 | 30 天 | 运维分析 |
| WARN | 异常但可恢复 | 90 天 | 问题排查 |
| ERROR | 错误需处理 | 1 年 | 事故追溯 |
| AUDIT | 关键操作记录 | 永久 | 合规审计 |

### 4.2 审计日志格式

```json
{
  "timestamp": "2026-05-07T14:32:05+08:00",
  "level": "AUDIT",
  "source": "intersection_001",
  "event": "signal_decision",
  "details": {
    "phase": "NS_GREEN",
    "duration": 35,
    "reasoning": "南北方向排队较长...",
    "confidence": 0.85,
    "method": "llm",
    "override": false
  },
  "metrics": {
    "queue_ns": 15,
    "queue_ew": 3,
    "total_vehicles": 42
  },
  "operator": null,
  "trace_id": "abc-123-def-456"
}
```

### 4.3 决策追溯

每个 LLM 决策都可以追溯：
- 输入（路口状态、邻居状态、时段信息）
- 推理过程（CoT）
- 输出（相位、时长、置信度）
- 执行结果（实际效果）
- 对比（如果用规则引擎会怎样）

---

## 5. 灰度发布

### 5.1 灰度策略

```
阶段1: 仿真环境测试 (100%)
  ↓
阶段2: 单路口灰度 (1 个路口)
  ↓
阶段3: 片区灰度 (10 个路口)
  ↓
阶段4: 全城上线 (所有路口)
```

### 5.2 流量切换

```python
@dataclass
class GradualRollout:
    """灰度发布配置。"""
    rollout_id: str
    phase: int                  # 当前阶段
    total_phases: int = 4
    
    # 流量比例
    llm_percentage: float = 0.0  # LLM 控制的路口比例
    rule_percentage: float = 1.0  # 规则引擎控制的比例
    
    # 切换条件
    min_success_rate: float = 0.95  # 最低成功率
    min_uptime: float = 3600.0      # 最低运行时间 (s)
    max_error_rate: float = 0.05    # 最高错误率
    
    def should_advance(self, metrics: dict) -> bool:
        """是否应该进入下一阶段。"""
        return (
            metrics.get("success_rate", 0) >= self.min_success_rate and
            metrics.get("uptime", 0) >= self.min_uptime and
            metrics.get("error_rate", 1) <= self.max_error_rate
        )
    
    def advance(self):
        """进入下一阶段。"""
        if self.phase < self.total_phases:
            self.phase += 1
            self.llm_percentage = self.phase / self.total_phases
            self.rule_percentage = 1.0 - self.llm_percentage
```

---

## 6. 故障恢复

### 6.1 降级策略

| 故障 | 降级方案 | 恢复时间 |
|------|---------|---------|
| LLM API 不可用 | 本地规则引擎 | < 5 秒 |
| LLM 响应超时 | 缓存决策复用 | < 3 秒 |
| 协调服务不可用 | 各路口独立决策 | < 10 秒 |
| 数据库不可用 | Redis 缓存 | < 1 秒 |
| 路口网关离线 | 信号控制器本地模式 | 立即 |
| 全系统崩溃 | 固定配时模式 | 立即 |

### 6.2 自动恢复

```python
class AutoRecovery:
    """自动恢复机制。"""
    
    def __init__(self):
        self.health_checks: dict[str, float] = {}
        self.recovery_strategies: dict[str, callable] = {
            "llm_timeout": self._recover_llm_timeout,
            "llm_failure": self._recover_llm_failure,
            "coordinator_down": self._recover_coordinator,
            "gateway_offline": self._recover_gateway,
        }
    
    def check_and_recover(self, service: str, status: dict):
        """检查服务状态并自动恢复。"""
        if status.get("healthy"):
            self.health_checks[service] = time.time()
            return
        
        last_healthy = self.health_checks.get(service, 0)
        unhealthy_duration = time.time() - last_healthy
        
        if unhealthy_duration > 30:  # 不健康超过 30 秒
            strategy = self.recovery_strategies.get(service)
            if strategy:
                strategy(unhealthy_duration)
    
    def _recover_llm_timeout(self, duration: float):
        """LLM 超时恢复。"""
        # 1. 切换到缓存决策
        # 2. 如果缓存也没有，用规则引擎
        # 3. 每 30 秒重试 LLM
        pass
    
    def _recover_llm_failure(self, duration: float):
        """LLM 失败恢复。"""
        # 1. 降级到规则引擎
        # 2. 记录失败原因
        # 3. 通知运维
        pass
    
    def _recover_coordinator(self, duration: float):
        """协调服务恢复。"""
        # 1. 各路口独立决策
        # 2. 禁用绿波
        # 3. 等待协调服务恢复后重新同步
        pass
```

### 6.3 数据备份

| 数据 | 备份频率 | 保留期 | 备份方式 |
|------|---------|--------|---------|
| 配置 | 每次修改 | 永久 | Git |
| 决策日志 | 每小时 | 90 天 | 增量备份 |
| 交通数据 | 每天 | 30 天 | 全量备份 |
| 数据库 | 每天 | 7 天 | 快照 |

---

## 7. 实现优先级

| 优先级 | 功能 | 工作量 |
|--------|------|--------|
| P0 | Docker Compose 开发环境 | 1 天 |
| P0 | 基本健康检查 | 0.5 天 |
| P0 | 降级策略（LLM → 规则引擎） | 1 天 |
| P1 | Kubernetes 部署配置 | 2 天 |
| P1 | Prometheus + Grafana 监控 | 2 天 |
| P1 | 日志收集（ELK/Loki） | 2 天 |
| P2 | 灰度发布机制 | 2 天 |
| P2 | 自动恢复 | 1 天 |
| P2 | 数据备份 | 1 天 |
| P3 | 性能测试 | 2 天 |
