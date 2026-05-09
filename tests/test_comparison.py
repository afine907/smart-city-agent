"""
Tests for comparison benchmark framework.
"""

import json
import tempfile
from pathlib import Path

import pytest

from traffic_agent.comparison.benchmark import (
    BenchmarkReport,
    StrategyResult,
    TimingBenchmark,
)
from traffic_agent.simulation.sim_loop import SimulationReport


def _make_report(
    total_steps=100,
    avg_wait=15.0,
    throughput=0.5,
    generated=80,
    completed=60,
    adjustments=10,
    llm_adj=2,
    rule_adj=8,
) -> SimulationReport:
    return SimulationReport(
        total_steps=total_steps,
        total_time=float(total_steps),
        total_vehicles_generated=generated,
        total_vehicles_completed=completed,
        avg_wait_time=avg_wait,
        max_wait_time=avg_wait * 2,
        throughput=throughput,
        adjustments_made=adjustments,
        llm_adjustments=llm_adj,
        rule_adjustments=rule_adj,
        zero_adjustments=0,
        pipeline_stats={},
        adjustment_log=[],
    )


class TestStrategyResult:
    """Test StrategyResult dataclass."""

    def test_creation(self):
        report = _make_report()
        result = StrategyResult(name="test", report=report, duration_seconds=1.23)
        assert result.name == "test"
        assert result.duration_seconds == 1.23

    def test_to_dict(self):
        report = _make_report(avg_wait=10.0, throughput=0.8)
        result = StrategyResult(name="test", report=report, duration_seconds=0.5)
        d = result.to_dict()
        assert d["name"] == "test"
        assert d["avg_wait_time"] == 10.0
        assert d["throughput"] == 0.8
        assert d["duration_seconds"] == 0.5


class TestBenchmarkReport:
    """Test BenchmarkReport formatting."""

    def test_improvements_calculated(self):
        fixed_report = _make_report(avg_wait=20.0, throughput=1.0)
        rule_report = _make_report(avg_wait=15.0, throughput=1.3)
        pipeline_report = _make_report(avg_wait=12.0, throughput=1.5)

        report = BenchmarkReport(
            results={
                "fixed": StrategyResult("fixed", fixed_report, 1.0),
                "rule": StrategyResult("rule", rule_report, 1.0),
                "pipeline": StrategyResult("pipeline", pipeline_report, 2.0),
            },
            intersection_type="crossroad",
            scenario_name="test",
            steps=100,
        )

        improvements = report._calc_improvements()
        # rule vs fixed: (20-15)/20*100 = 25%
        assert improvements["rule_avg_wait"] == pytest.approx(25.0)
        # pipeline vs fixed: (20-12)/20*100 = 40%
        assert improvements["pipeline_avg_wait"] == pytest.approx(40.0)

    def test_format_table(self):
        fixed_report = _make_report(avg_wait=20.0, throughput=1.0)
        rule_report = _make_report(avg_wait=15.0, throughput=1.3)

        report = BenchmarkReport(
            results={
                "fixed": StrategyResult("fixed", fixed_report, 1.0),
                "rule": StrategyResult("rule", rule_report, 1.0),
            },
            intersection_type="crossroad",
            scenario_name="test",
            steps=100,
        )

        table = report.format_table()
        assert "Timing Adjustment Benchmark" in table
        assert "fixed" in table
        assert "rule" in table
        assert "Avg Wait" in table

    def test_to_dict(self):
        fixed_report = _make_report(avg_wait=20.0)
        rule_report = _make_report(avg_wait=12.0)

        report = BenchmarkReport(
            results={
                "fixed": StrategyResult("fixed", fixed_report, 1.0),
                "rule": StrategyResult("rule", rule_report, 2.0),
            },
            intersection_type="crossroad",
            scenario_name="test",
            steps=100,
        )

        d = report.to_dict()
        assert "strategies" in d
        assert "fixed" in d["strategies"]
        assert "rule" in d["strategies"]
        assert "improvements" in d


class TestTimingBenchmark:
    """Test TimingBenchmark (unit tests only, no LLM calls)."""

    def test_fixed_simulation_runs(self):
        """Test that fixed-timing simulation runs and produces metrics."""
        bench = TimingBenchmark(steps=30, seed=42)
        report = bench._run_fixed()

        assert report.total_steps == 30
        assert report.avg_wait_time >= 0
        assert report.throughput >= 0

    def test_rule_simulation_runs(self):
        """Test that rule-based simulation runs."""
        bench = TimingBenchmark(steps=30, seed=42)
        report = bench._run_rule()

        assert report.total_steps == 30
        assert report.rule_adjustments >= 0

    def test_save_report(self):
        """Test saving report to JSON file."""
        bench = TimingBenchmark(steps=10, seed=42)
        report = bench.run(strategies=["fixed"])

        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/report.json"
            bench.save(report, path)

            assert Path(path).exists()

            with open(path) as f:
                data = json.load(f)

            assert "strategies" in data
            assert "fixed" in data["strategies"]
