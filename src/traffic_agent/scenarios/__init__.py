"""Scenarios module — preset traffic scenarios for benchmarking."""

from traffic_agent.scenarios.presets import (
    ScenarioConfig,
    create_scenario,
    SCENARIO_MORNING_PEAK,
    SCENARIO_NORMAL,
    SCENARIO_ACCIDENT,
    SCENARIO_EVENING_PEAK,
)

__all__ = [
    "ScenarioConfig",
    "create_scenario",
    "SCENARIO_MORNING_PEAK",
    "SCENARIO_NORMAL",
    "SCENARIO_ACCIDENT",
    "SCENARIO_EVENING_PEAK",
]
