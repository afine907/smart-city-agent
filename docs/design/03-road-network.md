# 第3章 路网层：OSM → SUMO

## 城市优先级

1. **shenzhen** — 深圳西丽留仙洞（老板上班的地方），最先搞定
2. **wuhan** — 武汉光谷
3. **manhattan** — 纽约时代广场

## 深圳西丽留仙洞路网

### 区域范围

西丽留仙洞片区，覆盖留仙大道、打石一路、同发路等主要道路。

**Bounding Box**（Overpass API 查询用）：
```
南: 22.575  西: 113.940
北: 22.595  东: 113.970
```

### OSM 数据获取

#### 方式 1：Overpass API（推荐）

```python
import requests

def download_shenzhen_osm(output: str = "shenzhen.osm"):
    """下载深圳西丽留仙洞 OSM 数据。"""
    bbox = "22.575,113.940,22.595,113.970"
    query = f"""
    [out:xml][timeout:60];
    (
      way["highway"]({bbox});
      node["highway"="traffic_signals"]({bbox});
    );
    out body;
    >;
    out skel qt;
    """
    
    response = requests.post(
        "https://overpass-api.de/api/interpreter",
        data={"data": query},
        timeout=120
    )
    response.raise_for_status()
    
    with open(output, "w") as f:
        f.write(response.text)
    
    print(f"Downloaded to {output}")
    return output
```

#### 方式 2：SUMO osmWebWizard

```bash
python $SUMO_HOME/tools/osmWebWizard.py
# 在地图上框选深圳西丽区域，自动生成配置
```

### netconvert 转换

```bash
# 基础转换
netconvert --osm-files shenzhen.osm -o shenzhen.net.xml \
    --tls.guess-signals true \
    --tls.discard-simple true \
    --tls.join true \
    --remove-edges.isolated true \
    --speed-in-kmh true \
    --default.lanenumber 2

# 如果报错，尝试宽松模式
netconvert --osm-files shenzhen.osm -o shenzhen.net.xml \
    --tls.guess-signals true \
    --tls.discard-simple true \
    --ignore-errors.edge-type true \
    --speed-in-kmh true
```

### 常见问题处理

| 问题 | 原因 | 解决 |
|------|------|------|
| 信号灯缺失 | OSM 数据没标记 | 手动添加 `--tls.guess-signals true` |
| 孤立节点 | OSM 数据碎片 | `--remove-edges.isolated true` |
| 车道数错误 | OSM 没有车道信息 | `--default.lanenumber 2` |
| 连接断开 | 路网不连续 | 用 NETEDIT 手动修复 |
| 编码错误 | 中文路名 | `--output.original-names false` |

### 手动修复（NETEDIT）

```bash
# 打开 NETEDIT 图形编辑器
netedit shenzhen.net.xml

# 常见操作：
# 1. 添加缺失的连接：选中边 → 右键 → Create Edge
# 2. 修复信号灯：选中路口 → Traffic Light → Edit
# 3. 调整车道数：选中边 → Number of Lanes
```

## 仿真配置

### shenzhen.sumocfg

```xml
<configuration>
    <input>
        <net-file value="shenzhen.net.xml"/>
        <route-files value="shenzhen.rou.xml"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="3600"/>
        <step-length value="1"/>
    </time>
</configuration>
```

### 车辆路由生成

```bash
# 使用 SUMO 自带工具生成随机路由
python $SUMO_HOME/tools/randomTrips.py \
    -n shenzhen.net.xml \
    -o shenzhen.rou.xml \
    -b 0 -e 3600 \
    -p 3 \
    --seed 42 \
    --validate
```

### 不同需求水平

```bash
# 低需求（每 10 秒一辆）
python $SUMO_HOME/tools/randomTrips.py -n shenzhen.net.xml -o shenzhen_low.rou.xml -p 10

# 中需求（每 3 秒一辆）
python $SUMO_HOME/tools/randomTrips.py -n shenzhen.net.xml -o shenzhen_medium.rou.xml -p 3

# 高需求（每 1 秒一辆）
python $SUMO_HOME/tools/randomTrips.py -n shenzhen.net.xml -o shenzhen_high.rou.xml -p 1
```

## 验证脚本

```python
"""验证深圳路网是否可用。"""
import traci

def validate_shenzhen(config: str = "shenzhen.sumocfg"):
    traci.start(["sumo", "-c", config])
    
    # 检查信号灯
    tls = traci.trafficlight.getIDList()
    print(f"Traffic lights: {len(tls)}")
    for tl in tls:
        phases = traci.trafficlight.getAllProgramLogics(tl)
        print(f"  {tl}: {len(phases[0].phases)} phases")
    
    # 检查路口
    junctions = traci.junction.getIDList()
    print(f"Junctions: {len(junctions)}")
    
    # 检查边
    edges = traci.edge.getIDList()
    print(f"Edges: {len(edges)}")
    
    # 跑 100 步看看
    for i in range(100):
        traci.simulationStep()
    
    remaining = traci.simulation.getMinExpectedNumber()
    print(f"Vehicles remaining after 100 steps: {remaining}")
    
    traci.close()
    return len(tls) > 0

if __name__ == "__main__":
    validate_shenzhen()
```

## 从 SUMO 示例路网开始

如果 OSM 数据有问题，先用 SUMO 自带的示例路网验证流程：

```bash
# SUMO 自带示例
ls $SUMO_HOME/examples/

# 常用示例
$SUMO_HOME/examples/net/4十字路口/
$SUMO_HOME/examples/net/cross/
```

```python
# 用示例路网快速验证 LLM 决策流程
import traci
traci.start(["sumo", "-c", f"{os.environ['SUMO_HOME']}/examples/net/cross/cross.sumocfg"])
# ... 验证 LLM 决策逻辑
traci.close()
```

## 三个城市的路网文件结构

```
networks/
├── shenzhen/                    # 优先
│   ├── shenzhen.osm
│   ├── shenzhen.net.xml
│   ├── shenzhen.rou.xml
│   ├── shenzhen.sumocfg
│   ├── shenzhen_low.rou.xml
│   ├── shenzhen_medium.rou.xml
│   └── shenzhen_high.rou.xml
├── wuhan/                       # 第二
│   └── ...
└── manhattan/                   # 第三
    └── ...
```
