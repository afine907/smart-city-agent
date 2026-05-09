"""
LLM Prompts — Prompt templates for traffic signal timing adjustment.

All prompts are designed for the "±10s adjustment" model:
LLM does NOT control the signal directly. It only suggests
small timing adjustments on top of a fixed baseline plan.
"""

# System prompt for the timing adjustment advisor
TIMING_ADJUSTMENT_SYSTEM = """你是一个交通信号读秒优化顾问，负责为路口信号灯提供读秒微调建议。

## 背景
路口有一个固定的基线配时方案（如南北绿灯60秒、东西绿灯90秒）。
你的任务是根据实时检测器数据，建议对当前绿灯相位进行微调。

## 约束
- 调整范围：-10 到 +10 秒（负数=缩短当前绿灯，正数=延长当前绿灯）
- 安全第一：不能让任何方向等待超过120秒
- 当前绿灯剩余不足10秒时不建议缩短
- 置信度要诚实评估

## 决策原则
1. **车流量**：排队多的方向应该获得更多绿灯时间
2. **行人安全**：有行人等待时应适当延长绿灯
3. **非机动车**：自行车/电动车需要额外通行时间
4. **趋势判断**：流量上升趋势应提前延长，下降趋势可缩短
5. **公平性**：不能让一个方向连续等待过久

## 输出格式
严格JSON格式，不要有其他文字：
{"adjustment": <整数, -10到10>, "reasoning": "<中文解释>", "confidence": <0.0-1.0>, "alerts": ["<预警信息>"]}"""

# User message template
TIMING_ADJUSTMENT_USER = """当前路口状态：

路口: {intersection_id}
类型: {intersection_type}
当前相位: {current_phase}
基线绿灯时长: {base_duration}秒
已持续: {phase_elapsed}秒
剩余: {phase_remaining}秒

各方向检测器数据:
- 北: 车辆{north_vehicles}辆, 行人{north_pedestrians}人, 非机动车{north_bicycles}辆
- 南: 车辆{south_vehicles}辆, 行人{south_pedestrians}人, 非机动车{south_bicycles}辆
- 东: 车辆{east_vehicles}辆, 行人{east_pedestrians}人, 非机动车{east_bicycles}辆
- 西: 车辆{west_vehicles}辆, 行人{west_pedestrians}人, 非机动车{west_bicycles}辆

流量趋势（最近5个周期的排队车辆数）:
- 南北方向: {ns_trend}
- 东西方向: {ew_trend}

最近调整历史:
{recent_adjustments}

请给出当前绿灯相位的读秒调整建议（JSON格式）。"""


def format_timing_message(
    intersection_id: str,
    intersection_type: str,
    current_phase: str,
    base_duration: float,
    phase_elapsed: float,
    phase_remaining: float,
    detector_data: dict,
    ns_trend: list,
    ew_trend: list,
    recent_adjustments: list,
) -> str:
    """
    Format the user message for LLM timing adjustment.

    Args:
        intersection_id: ID of the intersection
        intersection_type: "crossroad" or "tjunction"
        current_phase: current signal phase name
        base_duration: baseline green duration
        phase_elapsed: seconds elapsed in current phase
        phase_remaining: seconds remaining in current phase
        detector_data: dict with readings per direction
        ns_trend: list of recent NS queue counts
        ew_trend: list of recent EW queue counts
        recent_adjustments: list of recent adjustment dicts

    Returns:
        Formatted user message string
    """
    readings = detector_data.get("readings", {})

    def get_reading(direction, field):
        return readings.get(direction, {}).get(field, 0)

    # Format recent adjustments
    if recent_adjustments:
        adj_text = "\n".join(
            f"  - {a.get('phase', '?')}: 调整{a.get('adjustment', 0):+d}秒, "
            f"原因: {a.get('reason', '无')}"
            for a in recent_adjustments[-3:]  # last 3
        )
    else:
        adj_text = "  无"

    return TIMING_ADJUSTMENT_USER.format(
        intersection_id=intersection_id,
        intersection_type=intersection_type,
        current_phase=current_phase,
        base_duration=base_duration,
        phase_elapsed=phase_elapsed,
        phase_remaining=phase_remaining,
        north_vehicles=get_reading("north", "vehicles"),
        north_pedestrians=get_reading("north", "pedestrians"),
        north_bicycles=get_reading("north", "bicycles"),
        south_vehicles=get_reading("south", "vehicles"),
        south_pedestrians=get_reading("south", "pedestrians"),
        south_bicycles=get_reading("south", "bicycles"),
        east_vehicles=get_reading("east", "vehicles"),
        east_pedestrians=get_reading("east", "pedestrians"),
        east_bicycles=get_reading("east", "bicycles"),
        west_vehicles=get_reading("west", "vehicles"),
        west_pedestrians=get_reading("west", "pedestrians"),
        west_bicycles=get_reading("west", "bicycles"),
        ns_trend=ns_trend or [],
        ew_trend=ew_trend or [],
        recent_adjustments=adj_text,
    )
