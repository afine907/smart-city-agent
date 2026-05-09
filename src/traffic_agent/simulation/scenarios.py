"""
Traffic Scenarios — Preset traffic patterns for simulation.

Each scenario defines how traffic flows change over time,
modeling real-world patterns like morning rush hour,
evening commute, accidents, and balanced periods.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TrafficPhase:
    """A phase within a scenario with specific traffic parameters."""
    name: str
    duration_steps: int
    arrival_rates: Dict[str, float]      # per-approach rates (vehicles/sec)
    pedestrian_rate: float = 0.02        # pedestrians per second
    bicycle_rate: float = 0.01           # bicycles per second
    direction_bias: Optional[Dict[str, float]] = None  # multiplier per direction
    emergency_rate: float = 0.005

    def get_arrival_rate(self, direction: str) -> float:
        """Get arrival rate for a direction, applying bias if present."""
        base = self.arrival_rates.get(direction, 0.3)
        if self.direction_bias:
            bias = self.direction_bias.get(direction, 1.0)
            return base * bias
        return base


@dataclass
class TrafficScenario:
    """A complete traffic scenario with multiple phases."""
    name: str
    name_cn: str  # Chinese name for display
    description: str
    intersection_type: str  # "crossroad" or "tjunction"
    phases: List[TrafficPhase]

    @property
    def total_steps(self) -> int:
        return sum(p.duration_steps for p in self.phases)

    def get_phase_at_step(self, step: int) -> Optional[TrafficPhase]:
        """Get the traffic phase active at a given simulation step."""
        cumulative = 0
        for phase in self.phases:
            cumulative += phase.duration_steps
            if step < cumulative:
                return phase
        return self.phases[-1] if self.phases else None


# ─── Preset Scenarios ───────────────────────────────────────────


def morning_peak(intersection_type: str = "crossroad") -> TrafficScenario:
    """Morning rush hour: heavy north-south traffic (commuters heading to work)."""
    return TrafficScenario(
        name="morning_peak",
        name_cn="早高峰",
        description="早高峰时段：南北方向车流密集，东西方向较空",
        intersection_type=intersection_type,
        phases=[
            TrafficPhase(
                name="ramp_up",
                duration_steps=50,
                arrival_rates={"north": 0.4, "south": 0.4, "east": 0.2, "west": 0.2},
                direction_bias={"north": 1.5, "south": 1.5},
                pedestrian_rate=0.03,
                bicycle_rate=0.02,
            ),
            TrafficPhase(
                name="peak",
                duration_steps=150,
                arrival_rates={"north": 0.6, "south": 0.6, "east": 0.3, "west": 0.3},
                direction_bias={"north": 2.0, "south": 2.0},
                pedestrian_rate=0.05,
                bicycle_rate=0.03,
            ),
            TrafficPhase(
                name="ramp_down",
                duration_steps=100,
                arrival_rates={"north": 0.3, "south": 0.3, "east": 0.2, "west": 0.2},
                direction_bias={"north": 1.3, "south": 1.3},
                pedestrian_rate=0.02,
                bicycle_rate=0.01,
            ),
        ],
    )


def evening_peak(intersection_type: str = "crossroad") -> TrafficScenario:
    """Evening rush hour: heavy east-west traffic (commuters leaving city center)."""
    return TrafficScenario(
        name="evening_peak",
        name_cn="晚高峰",
        description="晚高峰时段：东西方向车流密集，南北方向较空",
        intersection_type=intersection_type,
        phases=[
            TrafficPhase(
                name="ramp_up",
                duration_steps=50,
                arrival_rates={"north": 0.2, "south": 0.2, "east": 0.4, "west": 0.4},
                direction_bias={"east": 1.5, "west": 1.5},
                pedestrian_rate=0.03,
                bicycle_rate=0.01,
            ),
            TrafficPhase(
                name="peak",
                duration_steps=150,
                arrival_rates={"north": 0.3, "south": 0.3, "east": 0.6, "west": 0.6},
                direction_bias={"east": 2.0, "west": 2.0},
                pedestrian_rate=0.04,
                bicycle_rate=0.02,
            ),
            TrafficPhase(
                name="ramp_down",
                duration_steps=100,
                arrival_rates={"north": 0.2, "south": 0.2, "east": 0.3, "west": 0.3},
                direction_bias={"east": 1.3, "west": 1.3},
                pedestrian_rate=0.02,
                bicycle_rate=0.01,
            ),
        ],
    )


def normal_flow(intersection_type: str = "crossroad") -> TrafficScenario:
    """Normal balanced traffic flow."""
    return TrafficScenario(
        name="normal",
        name_cn="平峰",
        description="平峰时段：各方向车流均匀",
        intersection_type=intersection_type,
        phases=[
            TrafficPhase(
                name="steady",
                duration_steps=300,
                arrival_rates={"north": 0.3, "south": 0.3, "east": 0.3, "west": 0.3},
                pedestrian_rate=0.02,
                bicycle_rate=0.01,
            ),
        ],
    )


def pedestrian_heavy(intersection_type: str = "crossroad") -> TrafficScenario:
    """Pedestrian-heavy scenario: lots of people crossing, moderate vehicle traffic."""
    return TrafficScenario(
        name="pedestrian_heavy",
        name_cn="行人高峰",
        description="行人密集时段：行人数量多，车辆中等",
        intersection_type=intersection_type,
        phases=[
            TrafficPhase(
                name="ped_peak",
                duration_steps=200,
                arrival_rates={"north": 0.25, "south": 0.25, "east": 0.25, "west": 0.25},
                pedestrian_rate=0.15,  # 6x normal
                bicycle_rate=0.03,
            ),
        ],
    )


def accident_scenario(intersection_type: str = "crossroad") -> TrafficScenario:
    """Accident scenario: sudden traffic surge with emergency vehicles."""
    return TrafficScenario(
        name="accident",
        name_cn="突发事故",
        description="事故场景：某方向突然涌入大量车辆，频繁出现急救车",
        intersection_type=intersection_type,
        phases=[
            TrafficPhase(
                name="pre_accident",
                duration_steps=80,
                arrival_rates={"north": 0.3, "south": 0.3, "east": 0.3, "west": 0.3},
                pedestrian_rate=0.02,
                bicycle_rate=0.01,
            ),
            TrafficPhase(
                name="accident_active",
                duration_steps=120,
                arrival_rates={"north": 0.7, "south": 0.7, "east": 0.3, "west": 0.3},
                direction_bias={"north": 1.5, "south": 1.5},
                pedestrian_rate=0.01,
                bicycle_rate=0.005,
                emergency_rate=0.03,  # 6x normal
            ),
            TrafficPhase(
                name="recovery",
                duration_steps=100,
                arrival_rates={"north": 0.3, "south": 0.3, "east": 0.3, "west": 0.3},
                pedestrian_rate=0.02,
                bicycle_rate=0.01,
            ),
        ],
    )


def bicycle_rush(intersection_type: str = "crossroad") -> TrafficScenario:
    """Bicycle rush hour: lots of cyclists, moderate vehicle traffic."""
    return TrafficScenario(
        name="bicycle_rush",
        name_cn="非机动车高峰",
        description="非机动车密集时段：自行车/电动车多，车辆中等",
        intersection_type=intersection_type,
        phases=[
            TrafficPhase(
                name="bike_peak",
                duration_steps=200,
                arrival_rates={"north": 0.3, "south": 0.3, "east": 0.3, "west": 0.3},
                pedestrian_rate=0.02,
                bicycle_rate=0.1,  # 10x normal
            ),
        ],
    )


# ─── Scenario Registry ─────────────────────────────────────────

SCENARIOS = {
    "morning_peak": morning_peak,
    "evening_peak": evening_peak,
    "normal": normal_flow,
    "pedestrian_heavy": pedestrian_heavy,
    "accident": accident_scenario,
    "bicycle_rush": bicycle_rush,
}


def get_scenario(name: str, intersection_type: str = "crossroad") -> TrafficScenario:
    """Get a scenario by name."""
    factory = SCENARIOS.get(name)
    if factory is None:
        raise ValueError(f"Unknown scenario: {name}. Available: {list(SCENARIOS.keys())}")
    return factory(intersection_type)


def list_scenarios() -> List[Dict[str, str]]:
    """List all available scenarios."""
    return [
        {"name": name, "name_cn": factory().name_cn, "description": factory().description}
        for name, factory in SCENARIOS.items()
    ]
