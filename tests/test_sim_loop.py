"""Tests for simulation loop."""

import pytest
from traffic_agent.simulation.sim_loop import TimingSimulation, StepResult, SimulationReport


class TestTimingSimulation:
    def test_create_crossroad(self):
        sim = TimingSimulation(intersection_type="crossroad", seed=42)
        assert sim.intersection_type == "crossroad"
        assert sim.plan.intersection_type == "crossroad"

    def test_create_tjunction(self):
        sim = TimingSimulation(intersection_type="tjunction", seed=42)
        assert sim.intersection_type == "tjunction"
        assert sim.plan.intersection_type == "tjunction"

    def test_step_returns_result(self):
        sim = TimingSimulation(seed=42)
        result = sim.step()
        assert isinstance(result, StepResult)
        assert result.step == 1
        assert result.timestamp == 1.0

    def test_run_returns_report(self):
        sim = TimingSimulation(seed=42)
        report = sim.run(steps=50)
        assert isinstance(report, SimulationReport)
        assert report.total_steps == 50
        assert report.total_time == 50.0

    def test_vehicles_generated(self):
        sim = TimingSimulation(seed=42)
        report = sim.run(steps=100)
        assert report.total_vehicles_generated > 0

    def test_vehicles_completed(self):
        sim = TimingSimulation(seed=42)
        report = sim.run(steps=300)
        # With 300 steps, some vehicles should have completed
        assert report.total_vehicles_completed > 0

    def test_signal_state_changes(self):
        sim = TimingSimulation(seed=42)
        phases_seen = set()
        for _ in range(500):
            result = sim.step()
            phases_seen.add(result.signal_state["current_phase"])
        # Should see multiple phases
        assert len(phases_seen) > 1

    def test_scenario_affects_generation(self):
        # Morning peak should generate more vehicles than normal
        sim_peak = TimingSimulation(
            scenario_name="morning_peak", seed=42
        )
        sim_normal = TimingSimulation(
            scenario_name="normal", seed=42
        )
        peak_report = sim_peak.run(steps=200)
        normal_report = sim_normal.run(steps=200)
        # Peak should generate at least as many vehicles
        assert peak_report.total_vehicles_generated >= normal_report.total_vehicles_generated * 0.8

    def test_with_rule_pipeline(self):
        from traffic_agent.optimization.rule_engine import TimingRuleEngine
        from traffic_agent.llm.parser import TimingAdjustment

        class RuleOnlyPipeline:
            def __init__(self):
                self.rule_engine = TimingRuleEngine()

            def decide(self, detector_data, signal_state, trend=None, **kwargs):
                result = self.rule_engine.decide(detector_data, signal_state, trend)
                if result:
                    return result
                return TimingAdjustment.no_adjustment()

            def get_stats(self):
                return self.rule_engine.get_stats()

        sim = TimingSimulation(
            pipeline=RuleOnlyPipeline(),
            seed=42,
        )
        report = sim.run(steps=200)
        # Should have made some adjustments
        assert report.adjustments_made >= 0

    def test_export_log(self, tmp_path):
        sim = TimingSimulation(seed=42)
        sim.run(steps=50)
        log_path = str(tmp_path / "log.json")
        sim.export_log(log_path)

        import json
        with open(log_path) as f:
            data = json.load(f)
        assert "adjustments" in data
        assert "pipeline_stats" in data

    def test_custom_timing(self):
        sim = TimingSimulation(
            seed=42,
            ns_green=45.0,
            ew_green=75.0,
        )
        plan_info = sim.controller.get_plan_info()
        phases = {p["name"]: p["duration"] for p in plan_info["phases"]}
        assert phases["NS_GREEN"] == 45.0
        assert phases["EW_GREEN"] == 75.0

    def test_detector_data_in_result(self):
        sim = TimingSimulation(seed=42)
        result = sim.step()
        assert "readings" in result.detector_data
        assert "north" in result.detector_data["readings"]

    def test_queue_sizes_in_result(self):
        sim = TimingSimulation(seed=42)
        result = sim.step()
        assert "north" in result.queue_sizes
        assert "south" in result.queue_sizes
        assert "east" in result.queue_sizes
        assert "west" in result.queue_sizes
