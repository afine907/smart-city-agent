"""
Traffic Scenario Presets — predefined configurations for benchmarking.

Each scenario represents a realistic traffic condition:
- Morning Peak: commuters flowing into city center
- Normal: balanced everyday traffic
- Accident: emergency + congestion
- Evening Peak: commuters flowing out
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from traffic_agent.simulation.engine import SimulationConfig


@dataclass
class PhaseConfig:
    """Configuration for a simulation phase (time segment)."""
    name: str
    duration_steps: int
    arrival_rate: float = 0.5
    emergency_rate: float = 0.005
    # Direction bias: multiplier for each approach (N, E, S, W)
    direction_bias: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0])
    description: str = ""


@dataclass
class ScenarioConfig:
    """Full scenario configuration with multiple phases."""
    name: str
    description: str
    phases: List[PhaseConfig]
    seed: int = 42
    total_steps: int = 300

    def to_simulation_configs(self) -> List[tuple]:
        """
        Convert to list of (SimulationConfig, duration) tuples.
        Each phase gets its own SimulationConfig.
        """
        configs = []
        for phase in self.phases:
            config = SimulationConfig(
                arrival_rate=phase.arrival_rate,
                emergency_rate=phase.emergency_rate,
                seed=self.seed,
            )
            configs.append((config, phase.duration_steps))
        return configs


# ─── Preset Scenarios ──────────────────────────────────────

SCENARIO_MORNING_PEAK = ScenarioConfig(
    name="morning_peak",
    description="早高峰：大量车辆从外围涌入市中心，南北方向拥堵",
    seed=42,
    total_steps=300,
    phases=[
        PhaseConfig(
            name="ramp_up",
            duration_steps=50,
            arrival_rate=0.6,
            emergency_rate=0.003,
            direction_bias=[1.5, 0.8, 1.5, 0.8],  # 南北重
            description="早高峰渐起",
        ),
        PhaseConfig(
            name="peak",
            duration_steps=150,
            arrival_rate=0.9,
            emergency_rate=0.005,
            direction_bias=[2.0, 0.6, 2.0, 0.6],  # 南北重
            description="早高峰最拥堵时段",
        ),
        PhaseConfig(
            name="ramp_down",
            duration_steps=100,
            arrival_rate=0.5,
            emergency_rate=0.003,
            direction_bias=[1.2, 0.9, 1.2, 0.9],
            description="早高峰消退",
        ),
    ],
)

SCENARIO_NORMAL = ScenarioConfig(
    name="normal",
    description="平峰：均衡交通流量，各方向车辆数相近",
    seed=42,
    total_steps=300,
    phases=[
        PhaseConfig(
            name="steady",
            duration_steps=300,
            arrival_rate=0.4,
            emergency_rate=0.002,
            direction_bias=[1.0, 1.0, 1.0, 1.0],
            description="稳定平峰流量",
        ),
    ],
)

SCENARIO_ACCIDENT = ScenarioConfig(
    name="accident",
    description="事故场景：某路口拥堵+救护车频繁，测试紧急车辆优先",
    seed=42,
    total_steps=300,
    phases=[
        PhaseConfig(
            name="pre_accident",
            duration_steps=80,
            arrival_rate=0.5,
            emergency_rate=0.002,
            direction_bias=[1.0, 1.0, 1.0, 1.0],
            description="事故前正常流量",
        ),
        PhaseConfig(
            name="accident_active",
            duration_steps=120,
            arrival_rate=0.7,  # 拥堵导致更多车辆排队
            emergency_rate=0.03,  # 救护车/警车频繁
            direction_bias=[1.5, 1.5, 1.0, 1.0],  # 事故方向偏重
            description="事故发生：拥堵+紧急车辆",
        ),
        PhaseConfig(
            name="recovery",
            duration_steps=100,
            arrival_rate=0.4,
            emergency_rate=0.005,
            direction_bias=[1.0, 1.0, 1.0, 1.0],
            description="事故处理完毕，交通恢复",
        ),
    ],
)

SCENARIO_EVENING_PEAK = ScenarioConfig(
    name="evening_peak",
    description="晚高峰：车辆从市中心向外扩散，东西方向拥堵",
    seed=42,
    total_steps=300,
    phases=[
        PhaseConfig(
            name="ramp_up",
            duration_steps=50,
            arrival_rate=0.6,
            emergency_rate=0.003,
            direction_bias=[0.8, 1.5, 0.8, 1.5],  # 东西重
            description="晚高峰渐起",
        ),
        PhaseConfig(
            name="peak",
            duration_steps=150,
            arrival_rate=0.9,
            emergency_rate=0.005,
            direction_bias=[0.6, 2.0, 0.6, 2.0],  # 东西重
            description="晚高峰最拥堵时段",
        ),
        PhaseConfig(
            name="ramp_down",
            duration_steps=100,
            arrival_rate=0.5,
            emergency_rate=0.003,
            direction_bias=[0.9, 1.2, 0.9, 1.2],
            description="晚高峰消退",
        ),
    ],
)


ALL_SCENARIOS = {
    "morning_peak": SCENARIO_MORNING_PEAK,
    "normal": SCENARIO_NORMAL,
    "accident": SCENARIO_ACCIDENT,
    "evening_peak": SCENARIO_EVENING_PEAK,
}


def create_scenario(name: str, **overrides) -> ScenarioConfig:
    """Create a scenario by name with optional overrides."""
    if name not in ALL_SCENARIOS:
        raise ValueError(f"Unknown scenario: {name}. Available: {list(ALL_SCENARIOS.keys())}")

    scenario = ALL_SCENARIOS[name]

    # Apply overrides
    if "seed" in overrides:
        scenario = ScenarioConfig(
            name=scenario.name,
            description=scenario.description,
            phases=scenario.phases,
            seed=overrides["seed"],
            total_steps=overrides.get("total_steps", scenario.total_steps),
        )

    return scenario
