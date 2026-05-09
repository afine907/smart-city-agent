"""
Timing Benchmark — Compare fixed timing vs rule vs LLM adjustment.

Runs identical simulations with different decision strategies,
then produces quantitative comparison reports.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from traffic_agent.llm.client import LLMConfig
from traffic_agent.optimization.layered import TimingDecisionPipeline
from traffic_agent.simulation.sim_loop import SimulationReport, TimingSimulation


@dataclass
class StrategyResult:
    """Result from a single strategy run."""
    name: str
    report: SimulationReport
    duration_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "total_steps": self.report.total_steps,
            "total_vehicles_generated": self.report.total_vehicles_generated,
            "total_vehicles_completed": self.report.total_vehicles_completed,
            "avg_wait_time": round(self.report.avg_wait_time, 2),
            "throughput": round(self.report.throughput, 4),
            "adjustments_made": self.report.adjustments_made,
            "llm_adjustments": self.report.llm_adjustments,
            "rule_adjustments": self.report.rule_adjustments,
            "duration_seconds": round(self.duration_seconds, 2),
            "pipeline_stats": self.report.pipeline_stats,
        }


@dataclass
class BenchmarkReport:
    """Full benchmark report comparing multiple strategies."""
    results: Dict[str, StrategyResult]
    intersection_type: str
    scenario_name: str
    steps: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intersection_type": self.intersection_type,
            "scenario": self.scenario_name,
            "steps": self.steps,
            "strategies": {name: r.to_dict() for name, r in self.results.items()},
            "improvements": self._calc_improvements(),
        }

    def format_table(self) -> str:
        """Format as a readable comparison table."""
        lines = []
        lines.append("=" * 70)
        lines.append(f"  Timing Adjustment Benchmark")
        lines.append(f"  Intersection: {self.intersection_type} | Scenario: {self.scenario_name}")
        lines.append("=" * 70)
        lines.append("")

        # Header
        names = list(self.results.keys())
        header = f"  {'Metric':<25}"
        for name in names:
            header += f" {name:>12}"
        lines.append(header)
        lines.append("  " + "-" * (25 + 13 * len(names)))

        # Metrics
        metrics = [
            ("avg_wait_time", "Avg Wait (s)", True),
            ("throughput", "Throughput (/s)", False),
            ("total_vehicles_generated", "Generated", False),
            ("total_vehicles_completed", "Completed", False),
            ("adjustments_made", "Adjustments", None),
            ("llm_adjustments", "LLM Calls", None),
            ("duration_seconds", "Runtime (s)", None),
        ]

        for key, label, lower_better in metrics:
            row = f"  {label:<25}"
            for name in names:
                val = getattr(self.results[name].report, key, 0)
                if key == "duration_seconds":
                    val = self.results[name].duration_seconds
                if isinstance(val, float):
                    row += f" {val:>12.2f}"
                else:
                    row += f" {val:>12}"
            lines.append(row)

        # Improvements
        improvements = self._calc_improvements()
        if improvements:
            lines.append("")
            lines.append("  Improvements (vs fixed):")
            for key, val in improvements.items():
                arrow = "+" if val > 0 else ""
                lines.append(f"    {key}: {arrow}{val:.1f}%")

        lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)

    def _calc_improvements(self) -> Dict[str, float]:
        """Calculate improvements for each strategy vs the first (baseline)."""
        names = list(self.results.keys())
        if len(names) < 2:
            return {}

        baseline = self.results[names[0]]
        improvements = {}

        for name in names[1:]:
            result = self.results[name]
            # Lower is better for wait time
            if baseline.report.avg_wait_time > 0:
                imp = (baseline.report.avg_wait_time - result.report.avg_wait_time) / baseline.report.avg_wait_time * 100
                improvements[f"{name}_avg_wait"] = imp
            # Higher is better for throughput
            if baseline.report.throughput > 0:
                imp = (result.report.throughput - baseline.report.throughput) / baseline.report.throughput * 100
                improvements[f"{name}_throughput"] = imp

        return improvements


class TimingBenchmark:
    """
    Benchmark framework comparing timing adjustment strategies.

    Strategies:
    1. Fixed timing (baseline): no adjustment
    2. Rule-based: rule engine only
    3. Full pipeline: rules → cache → LLM

    Usage:
        bench = TimingBenchmark(steps=500, scenario="morning_peak")
        report = bench.run()
        print(report.format_table())
    """

    def __init__(
        self,
        steps: int = 500,
        scenario: str = "morning_peak",
        intersection_type: str = "crossroad",
        seed: int = 42,
        llm_config: Optional[LLMConfig] = None,
    ):
        self.steps = steps
        self.scenario = scenario
        self.intersection_type = intersection_type
        self.seed = seed
        self.llm_config = llm_config

    def run(self, strategies: Optional[List[str]] = None) -> BenchmarkReport:
        """
        Run benchmark with specified strategies.

        Args:
            strategies: list of strategy names to run.
                       Default: ["fixed", "rule", "pipeline"]
        """
        if strategies is None:
            strategies = ["fixed", "rule", "pipeline"]

        results = {}

        for strategy in strategies:
            print(f"\n  Running strategy: {strategy}...")
            start = time.time()

            if strategy == "fixed":
                report = self._run_fixed()
            elif strategy == "rule":
                report = self._run_rule()
            elif strategy == "pipeline":
                report = self._run_pipeline()
            else:
                raise ValueError(f"Unknown strategy: {strategy}")

            elapsed = time.time() - start
            results[strategy] = StrategyResult(
                name=strategy,
                report=report,
                duration_seconds=elapsed,
            )
            print(f"    Done in {elapsed:.1f}s | "
                  f"Avg wait: {report.avg_wait_time:.1f}s | "
                  f"Throughput: {report.throughput:.3f}/s")

        return BenchmarkReport(
            results=results,
            intersection_type=self.intersection_type,
            scenario_name=self.scenario,
            steps=self.steps,
        )

    def _run_fixed(self) -> SimulationReport:
        """Run with fixed timing (no adjustments)."""
        sim = TimingSimulation(
            intersection_type=self.intersection_type,
            scenario_name=self.scenario,
            pipeline=None,
            seed=self.seed,
        )
        return sim.run(steps=self.steps)

    def _run_rule(self) -> SimulationReport:
        """Run with rule engine only (no LLM)."""
        # Create a pipeline but only use rules (no cache, no LLM)
        from traffic_agent.optimization.rule_engine import TimingRuleEngine
        from traffic_agent.llm.parser import TimingAdjustment

        class RuleOnlyPipeline:
            """Pipeline that only uses rules, never calls LLM."""
            def __init__(self):
                self.rule_engine = TimingRuleEngine()
                self._stats = {"total_decisions": 0, "layer1_rules": 0}

            def decide(self, detector_data, signal_state, trend=None, **kwargs):
                self._stats["total_decisions"] += 1
                result = self.rule_engine.decide(detector_data, signal_state, trend)
                if result:
                    self._stats["layer1_rules"] += 1
                    return result
                return TimingAdjustment.no_adjustment("规则未命中，不调整")

            def get_stats(self):
                total = max(1, self._stats["total_decisions"])
                return {
                    **self._stats,
                    "rule_rate": self._stats["layer1_rules"] / total,
                    "layer2_cache": 0,
                    "layer3_llm": 0,
                    "free_rate": 1.0,
                }

        pipeline = RuleOnlyPipeline()
        sim = TimingSimulation(
            intersection_type=self.intersection_type,
            scenario_name=self.scenario,
            pipeline=pipeline,
            seed=self.seed,
        )
        return sim.run(steps=self.steps)

    def _run_pipeline(self) -> SimulationReport:
        """Run with full pipeline (rules → cache → LLM)."""
        pipeline = TimingDecisionPipeline(
            llm_config=self.llm_config,
        )
        sim = TimingSimulation(
            intersection_type=self.intersection_type,
            scenario_name=self.scenario,
            pipeline=pipeline,
            seed=self.seed,
        )
        return sim.run(steps=self.steps)

    def save(self, report: BenchmarkReport, path: str) -> None:
        """Save benchmark report to JSON."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  Report saved to {path}")


# Backward compatibility aliases
BenchmarkResult = StrategyResult
ComparisonBenchmark = TimingBenchmark
ComparisonReport = BenchmarkReport
