"""
Scenario Runner — runs multi-phase simulations with different configs.

Supports time-varying traffic patterns for realistic scenario testing.
"""

import time
from typing import Any, Dict, List, Optional

from traffic_agent.comparison.benchmark import BenchmarkResult
from traffic_agent.crew.traffic_crew import CrewConfig, TrafficControlCrew
from traffic_agent.llm.client import LLMConfig
from traffic_agent.optimization.cost_tracker import CostTracker
from traffic_agent.scenarios.presets import ScenarioConfig
from traffic_agent.simulation.engine import SimulationConfig
from traffic_agent.simulation.grid import GridSimulation


class ScenarioRunner:
    """
    Run a traffic scenario with LLM or fixed timing.

    Usage:
        runner = ScenarioRunner(scenario)
        result = runner.run_with_llm()
        result = runner.run_with_fixed()
    """

    def __init__(self, scenario: ScenarioConfig):
        self.scenario = scenario

    def run_with_fixed(self) -> BenchmarkResult:
        """Run scenario with fixed round-robin timing."""
        start_time = time.time()

        sim = GridSimulation(config=SimulationConfig(seed=self.scenario.seed))
        intersection_ids = list(sim.intersections.keys())
        phase_cycle = ["NS_GREEN", "EW_GREEN"]
        phase_duration = 30

        step_count = 0
        for config, duration in self.scenario.to_simulation_configs():
            sim.config.arrival_rate = config.arrival_rate
            sim.config.emergency_rate = config.emergency_rate

            for _ in range(duration):
                sim.step()

                # Fixed round-robin
                for ix_id in intersection_ids:
                    ix = sim.intersections[ix_id]
                    cycle_pos = (step_count // phase_duration) % len(phase_cycle)
                    new_phase = phase_cycle[cycle_pos]
                    if ix.current_phase != new_phase:
                        ix.current_phase = new_phase
                        ix.phase_timer = 0.0

                step_count += 1

        elapsed = time.time() - start_time
        metrics = sim.get_metrics()
        metrics["steps"] = step_count

        return BenchmarkResult(
            name=f"fixed_{self.scenario.name}",
            steps=step_count,
            metrics=metrics,
            duration_seconds=elapsed,
        )

    def run_with_llm(
        self,
        llm_config: Optional[LLMConfig] = None,
        cost_tracker: Optional[CostTracker] = None,
    ) -> BenchmarkResult:
        """Run scenario with LLM agent decisions."""
        start_time = time.time()

        sim = GridSimulation(config=SimulationConfig(seed=self.scenario.seed))
        intersection_ids = list(sim.intersections.keys())
        graph = sim.get_graph()

        crew_config = CrewConfig(
            llm=llm_config or LLMConfig(),
            decision_interval=5.0,
            enable_coordination=True,
            use_cache=True,
        )

        crew = TrafficControlCrew(intersection_ids, graph, crew_config)

        step_count = 0
        for config, duration in self.scenario.to_simulation_configs():
            sim.config.arrival_rate = config.arrival_rate
            sim.config.emergency_rate = config.emergency_rate

            for _ in range(duration):
                sim.step()

                # LLM decides every 5 steps
                if step_count % 5 == 0:
                    decisions = crew.step(sim)

                    # Track costs
                    if cost_tracker and decisions:
                        for d in decisions:
                            cost_tracker.record(
                                intersection_id=d.get("intersection_id", "unknown"),
                                model=crew.config.llm.fast_model,
                            )

                step_count += 1

        elapsed = time.time() - start_time
        metrics = sim.get_metrics()
        metrics["steps"] = step_count
        metrics["llm_calls"] = crew._total_llm_calls
        metrics["cache_hits"] = crew._total_cache_hits

        return BenchmarkResult(
            name=f"llm_{self.scenario.name}",
            steps=step_count,
            metrics=metrics,
            duration_seconds=elapsed,
        )
