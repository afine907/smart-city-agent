# 第1章 仿真层：SUMO

## 为什么用 SUMO？

### 不要自己写仿真器

自己写仿真器 = 同时发明物理学和城市规划。

现有项目自研了 `SimulationEngine`、`Vehicle`、`RoadNetwork` 等组件，但：
- 车辆跟驰模型（Krauss）不标准
- 变道模型缺失
- 没有碰撞检测
- 路由算法过于简化
- 无法被学术界认可

### SUMO 的优势

| 维度 | SUMO | 自研 |
|------|------|------|
| 历史 | 20+ 年，几千篇论文验证 | 新写的，无验证 |
| 车辆模型 | Krauss 跟驰、LC2013 变道 | 简单匀速模型 |
| 信号控制 | 完整的 TLS 程序 | 基础相位切换 |
| 性能 | C++ 引擎，10万+ 车辆 | Python，性能受限 |
| 社区 | 活跃，文档全 | 无 |
| 可复现性 | 学术界标准 | 难以复现 |

### 为什么不是 CityFlow？

- CityFlow 更轻量，但维护不活跃（最后一次更新 2022 年）
- SUMO 社区大、文档全、bug 少
- SUMO 的 TraCI Python 接口成熟稳定

## SUMO 核心概念

### 路网文件

```
manhattan.net.xml    ← 路网定义（节点、边、连接、信号灯）
manhattan.rou.xml    ← 车辆路由（车辆类型、出发时间、路径）
manhattan.sumocfg    ← 仿真配置（引用路网和路由）
```

### TraCI 接口

TraCI (Traffic Control Interface) 是 SUMO 的 Python 控制接口：

```python
import traci

# 启动仿真
traci.start(["sumo", "-c", "manhattan.sumocfg"])

# 读取状态
vehicle_count = traci.edge.getLastStepVehicleNumber("edge_id")
queue_length = traci.lane.getLastStepHaltingNumber("lane_id")

# 控制信号灯
traci.trafficlight.setPhase("tl_id", phase_id)
traci.trafficlight.setPhaseDuration("tl_id", duration)

# 推进仿真
traci.simulationStep()

# 关闭
traci.close()
```

### 信号灯控制

```python
# 获取信号灯状态
tl_logic = traci.trafficlight.getAllProgramLogics("tl_id")

# 设置相位
# Phase 0: 南北绿灯
# Phase 1: 南北黄灯
# Phase 2: 东西绿灯
# Phase 3: 东西黄灯
traci.trafficlight.setPhase("tl_id", 0)

# 设置相位时长（秒）
traci.trafficlight.setPhaseDuration("tl_id", 30)
```

## Sim Bridge 层设计

### 状态编码

将 SUMO 原始数据编码为 LLM 可理解的结构：

```python
def read_intersection_state(tl_id: str) -> dict:
    """读取路口状态，编码为 LLM 可理解的格式。"""
    lanes = traci.trafficlight.getControlledLanes(tl_id)
    
    state = {
        "intersection_id": tl_id,
        "timestamp": traci.simulation.getTime(),
        "current_phase": traci.trafficlight.getPhase(tl_id),
        "phase_duration": traci.trafficlight.getPhaseDuration(tl_id),
    }
    
    # 按方向聚合
    for direction in ["north", "south", "east", "west"]:
        dir_lanes = [l for l in lanes if get_direction(l) == direction]
        state[direction] = {
            "queue": sum(traci.lane.getLastStepHaltingNumber(l) for l in dir_lanes),
            "avg_wait": calculate_avg_wait(dir_lanes),
            "vehicle_count": sum(traci.lane.getLastStepVehicleNumber(l) for l in dir_lanes),
        }
    
    return state
```

### 动作映射

将 LLM 输出映射到 SUMO 操作：

```python
def apply_decision(tl_id: str, decision: dict):
    """将 LLM 决策应用到 SUMO。"""
    phase_map = {
        "NS_GREEN": 0,
        "NS_YELLOW": 1,
        "EW_GREEN": 2,
        "EW_YELLOW": 3,
    }
    
    phase = phase_map.get(decision["phase"])
    duration = max(10, min(60, decision["duration"]))
    
    traci.trafficlight.setPhase(tl_id, phase)
    traci.trafficlight.setPhaseDuration(tl_id, duration)
```

### 奖励计算

```python
def calculate_reward(tl_id: str) -> float:
    """计算当前步骤的奖励值。"""
    lanes = traci.trafficlight.getControlledLanes(tl_id)
    
    total_wait = 0
    total_queue = 0
    for lane in lanes:
        total_wait += traci.lane.getWaitingTime(lane)
        total_queue += traci.lane.getLastStepHaltingNumber(lane)
    
    # 奖励 = 负的等待时间（越小越好）
    reward = -(total_wait + total_queue * 5)
    return reward
```

## 仿真配置示例

### manhattan.sumocfg

```xml
<configuration>
    <input>
        <net-file value="manhattan.net.xml"/>
        <route-files value="manhattan.rou.xml"/>
        <additional-files value="manhattan.add.xml"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="3600"/>  <!-- 1小时 -->
        <step-length value="1"/>  <!-- 1秒一步 -->
    </time>
    <report>
        <verbose value="true"/>
        <log value="log.txt"/>
    </report>
</configuration>
```

### 车辆生成

```xml
<!-- manhattan.rou.xml -->
<routes>
    <vType id="car" accel="2.6" decel="4.5" length="5" maxSpeed="50"/>
    
    <flow id="ns_flow" begin="0" end="3600" vehsPerHour="800">
        <route edges="north_in south_out"/>
    </flow>
    
    <flow id="ew_flow" begin="0" end="3600" vehsPerHour="600">
        <route edges="east_in west_out"/>
    </flow>
</routes>
```

## 主循环

```python
def run_simulation(config: str, controller, steps: int = 3600):
    """运行仿真主循环。"""
    traci.start(["sumo", "-c", config])
    
    results = []
    for step in range(steps):
        # 读取所有路口状态
        states = {}
        for tl_id in traci.trafficlight.getIDList():
            states[tl_id] = read_intersection_state(tl_id)
        
        # 控制器决策
        decisions = controller.decide(states)
        
        # 执行决策
        for tl_id, decision in decisions.items():
            apply_decision(tl_id, decision)
        
        # 推进仿真
        traci.simulationStep()
        
        # 记录指标
        results.append(collect_metrics())
    
    traci.close()
    return results
```

## 关键 API 速查

| API | 用途 |
|-----|------|
| `traci.trafficlight.getIDList()` | 获取所有信号灯 ID |
| `traci.trafficlight.getPhase(tl)` | 获取当前相位 |
| `traci.trafficlight.setPhase(tl, p)` | 设置相位 |
| `traci.trafficlight.setPhaseDuration(tl, d)` | 设置相位时长 |
| `traci.trafficlight.getControlledLanes(tl)` | 获取控制的车道 |
| `traci.lane.getLastStepHaltingNumber(lane)` | 获取排队车辆数 |
| `traci.lane.getWaitingTime(lane)` | 获取等待时间 |
| `traci.edge.getLastStepVehicleNumber(edge)` | 获取边上的车辆数 |
| `traci.simulation.getMinExpectedNumber()` | 剩余车辆数 |
| `traci.simulationStep()` | 推进一步 |
