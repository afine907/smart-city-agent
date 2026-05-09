"""
Scenario Runner — runs multi-phase simulations using the new timing architecture.

Bridges the old ScenarioConfig presets with the new TimingSimulation engine.
"""

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
        from traffic_agent.optimization.rule_engine import TimingRuleEngine
        from traffic_agent.llm.parser import TimingAdjustment

        class RuleOnlyPipeline:
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
