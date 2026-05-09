"""
Tests for traffic scenario presets and runner.
"""

import pytest

from traffic_agent.scenarios.presets import (
    ALL_SCENARIOS,
    SCENARIO_ACCIDENT,
    SCENARIO_EVENING_PEAK,
    SCENARIO_MORNING_PEAK,
    SCENARIO_NORMAL,
    ScenarioConfig,
    create_scenario,
)
from traffic_agent.scenarios.runner import ScenarioRunner
from traffic_agent.simulation.engine import SimulationConfig


class TestScenarioPresets:
    """Test scenario configuration presets."""

    def test_all_scenarios_exist(self):
        assert "morning_peak" in ALL_SCENARIOS
        assert "normal" in ALL_SCENARIOS
        assert "accident" in ALL_SCENARIOS
        assert "evening_peak" in ALL_SCENARIOS

    def test_scenario_config_structure(self):
        for name, scenario in ALL_SCENARIOS.items():
            assert isinstance(scenario, ScenarioConfig)
            assert scenario.name == name
            assert len(scenario.phases) > 0
            assert scenario.total_steps > 0

    def test_phase_configs_valid(self):
        for scenario in ALL_SCENARIOS.values():
            for phase in scenario.phases:
                assert phase.duration_steps > 0
                assert 0 < phase.arrival_rate <= 2.0
                assert 0 <= phase.emergency_rate <= 0.1
                assert len(phase.direction_bias) == 4

    def test_morning_peak_ns_bias(self):
        """Morning peak should have heavier north-south flow."""
        peak_phase = SCENARIO_MORNING_PEAK.phases[1]  # peak phase
        assert peak_phase.direction_bias[0] > peak_phase.direction_bias[1]  # N > E
        assert peak_phase.direction_bias[2] > peak_phase.direction_bias[3]  # S > W

    def test_evening_peak_ew_bias(self):
        """Evening peak should have heavier east-west flow."""
        peak_phase = SCENARIO_EVENING_PEAK.phases[1]  # peak phase
        assert peak_phase.direction_bias[1] > peak_phase.direction_bias[0]  # E > N
        assert peak_phase.direction_bias[3] > peak_phase.direction_bias[2]  # W > S

    def test_accident_high_emergency(self):
        """Accident scenario should have high emergency rate in active phase."""
        active = SCENARIO_ACCIDENT.phases[1]  # accident_active
        assert active.emergency_rate > 0.01
        assert active.arrival_rate > 0.5

    def test_normal_balanced(self):
        """Normal scenario should have balanced direction bias."""
        for phase in SCENARIO_NORMAL.phases:
            assert phase.direction_bias == [1.0, 1.0, 1.0, 1.0]

    def test_create_scenario(self):
        scenario = create_scenario("normal")
        assert scenario.name == "normal"

    def test_create_scenario_with_overrides(self):
        scenario = create_scenario("normal", seed=123, total_steps=500)
        assert scenario.seed == 123
        assert scenario.total_steps == 500

    def test_create_scenario_unknown(self):
        with pytest.raises(ValueError, match="Unknown scenario"):
            create_scenario("nonexistent")

    def test_to_simulation_configs(self):
        configs = SCENARIO_NORMAL.to_simulation_configs()
        assert len(configs) == len(SCENARIO_NORMAL.phases)
        for config, duration in configs:
            assert isinstance(config, SimulationConfig)
            assert duration > 0


class TestScenarioRunner:
    """Test ScenarioRunner with the new timing architecture."""

    def test_fixed_normal_scenario(self):
        """Normal scenario with fixed timing should run without errors."""
        scenario = ScenarioConfig(
            name="normal",
            description="test",
            phases=SCENARIO_NORMAL.phases[:1],
            seed=42,
            total_steps=30,
        )
        scenario.phases[0].duration_steps = 30

        runner = ScenarioRunner(scenario)
        result = runner.run_fixed()

        assert result.name == "fixed_normal"
        assert result.report.total_steps == 30
        assert result.report.avg_wait_time >= 0
        assert result.duration_seconds >= 0

    def test_rule_normal_scenario(self):
        """Normal scenario with rule engine should run."""
        scenario = ScenarioConfig(
            name="normal",
            description="test",
            phases=SCENARIO_NORMAL.phases[:1],
            seed=42,
            total_steps=30,
        )
        scenario.phases[0].duration_steps = 30

        runner = ScenarioRunner(scenario)
        result = runner.run_rule()

        assert result.name == "rule_normal"
        assert result.report.total_steps == 30
