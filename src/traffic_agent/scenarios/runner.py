"""
Scenario Runner — runs multi-phase simulations using the new timing architecture.

Bridges the old ScenarioConfig presets with the new TimingSimulation engine.
"""

from __future__ import annotations


import time
from typing import Optional

from traffic_agent.comparison.benchmark import StrategyResult, SimulationReport
from traffic_agent.llm.client import LLMConfig
from traffic_agent.optimization.layered import TimingDecisionPipeline
from traffic_agent.scenarios.presets import ScenarioConfig
from traffic_agent.simulation.sim_loop import TimingSimulation


class ScenarioRunner:
    """
    Run a traffic scenario with fixed timing or LLM pipeline.

    Usage:
        from traffic_agent.scenarios import create_scenario
        from traffic_agent.scenarios.runner import ScenarioRunner

        scenario = create_scenario("morning_peak")
        runner = ScenarioRunner(scenario)

        fixed = runner.run_fixed()
        llm = runner.run_pipeline()
    """

    def __init__(self, scenario: ScenarioConfig):
        self.scenario = scenario

    def run_fixed(self) -> StrategyResult:
        """Run scenario with fixed timing (no adjustments)."""
        start = time.time()
        sim = TimingSimulation(
            intersection_type="crossroad",
            scenario_name=self.scenario.name,
            pipeline=None,
            seed=self.scenario.seed,
        )
        report = sim.run(steps=self.scenario.total_steps)
        elapsed = time.time() - start
        return StrategyResult(name=f"fixed_{self.scenario.name}", report=report, duration_seconds=elapsed)

    def run_rule(self) -> StrategyResult:
        """Run scenario with rule engine only (no LLM)."""
        from traffic_agent.optimization.rule_only import RuleOnlyPipeline

        start = time.time()
        pipeline = RuleOnlyPipeline()
        sim = TimingSimulation(
            intersection_type="crossroad",
            scenario_name=self.scenario.name,
            pipeline=pipeline,
            seed=self.scenario.seed,
        )
        report = sim.run(steps=self.scenario.total_steps)
        elapsed = time.time() - start
        return StrategyResult(name=f"rule_{self.scenario.name}", report=report, duration_seconds=elapsed)

    def run_pipeline(self, llm_config: Optional[LLMConfig] = None) -> StrategyResult:
        """Run scenario with full pipeline (rules → cache → LLM)."""
        start = time.time()
        pipeline = TimingDecisionPipeline(llm_config=llm_config)
        sim = TimingSimulation(
            intersection_type="crossroad",
            scenario_name=self.scenario.name,
            pipeline=pipeline,
            seed=self.scenario.seed,
        )
        report = sim.run(steps=self.scenario.total_steps)
        elapsed = time.time() - start
        return StrategyResult(name=f"pipeline_{self.scenario.name}", report=report, duration_seconds=elapsed)
