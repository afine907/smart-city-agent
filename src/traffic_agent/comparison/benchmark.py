"""
Comparison Benchmark — AI vs Fixed Timing comparison framework.

Runs identical simulations with LLM agents and fixed timing,
then produces quantitative comparison reports.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from traffic_agent.crew.traffic_crew import CrewConfig, TrafficControlCrew
from traffic_agent.llm.client import LLMConfig
from traffic_agent.simulation.engine import SimulationConfig
from traffic_agent.simulation.grid import GridSimulation


@dataclass
class BenchmarkResult:
    """Result from a single simulation run."""
    name: str
    steps: int
    metrics: Dict[str, float]
    duration_seconds: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "steps": self.steps,
            "metrics": self.metrics,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class ComparisonReport:
    """Full comparison between LLM and Fixed timing."""
    llm_result: BenchmarkResult
    fixed_result: BenchmarkResult
    improvements: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "llm": self.llm_result.to_dict(),
            "fixed": self.fixed_result.to_dict(),
            "improvements": self.improvements,
        }
    
    def format_table(self) -> str:
        """Format as a readable comparison table."""
        lines = []
        lines.append("=" * 60)
        lines.append("  📊 AI vs Fixed Timing Comparison")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"  Steps: {self.llm_result.steps}")
        lines.append("")
        
        # Header
        lines.append(f"  {'Metric':<25} {'Fixed':>10} {'LLM':>10} {'Δ':>10}")
        lines.append("  " + "-" * 55)
        
        # Metrics
        fixed_m = self.fixed_result.metrics
        llm_m = self.llm_result.metrics
        
        rows = [
            ("avg_wait_time", "Avg Wait (s)", True),
            ("max_wait_time", "Max Wait (s)", True),
            ("throughput", "Throughput", False),
            ("total_vehicles", "Total Queue", True),
            ("total_served", "Vehicles Served", False),
        ]
        
        for key, label, lower_better in rows:
            f_val = fixed_m.get(key, 0)
            l_val = llm_m.get(key, 0)
            imp = self.improvements.get(key, 0)
            
            arrow = "✅" if (imp > 0 and lower_better) or (imp < 0 and not lower_better) else "⚠️"
            sign = "+" if imp > 0 else ""
            
            if "time" in key or "wait" in key:
                lines.append(f"  {label:<25} {f_val:>10.1f} {l_val:>10.1f} {sign}{imp:>8.1f}% {arrow}")
            elif "throughput" in key:
                lines.append(f"  {label:<25} {f_val:>10.2f} {l_val:>10.2f} {sign}{imp:>8.1f}% {arrow}")
            else:
                lines.append(f"  {label:<25} {f_val:>10.0f} {l_val:>10.0f} {sign}{imp:>8.1f}% {arrow}")
        
        lines.append("")
        
        # Timing
        lines.append(f"  ⏱️  Fixed: {self.fixed_result.duration_seconds:.1f}s | LLM: {self.llm_result.duration_seconds:.1f}s")
        lines.append("=" * 60)
        
        return "\n".join(lines)


class ComparisonBenchmark:
    """
    Benchmark framework comparing LLM vs Fixed timing.
    
    Usage:
        bench = ComparisonBenchmark(steps=200)
        report = bench.run()
        print(report.format_table())
        bench.save(report, "results.json")
    """
    
    def __init__(
        self,
        steps: int = 200,
        seed: int = 42,
        llm_config: Optional[LLMConfig] = None,
    ):
        self.steps = steps
        self.seed = seed
        self.llm_config = llm_config or LLMConfig(
            fast_model="LongCat-Flash-Chat",
            api_key="ak_2Cn4wg4B92dL4kz8Vu95T6Tw2S36T",
            api_base="https://api.longcat.chat/openai",
        )
    
    def run(self) -> ComparisonReport:
        """Run both simulations and produce comparison report."""
        print(f"🏁 Running benchmark: {self.steps} steps each")
        print()
        
        # Run fixed timing
        print("🔴 Running fixed timing...")
        fixed_result = self._run_fixed()
        print(f"   Done in {fixed_result.duration_seconds:.1f}s")
        
        # Run LLM
        print("🧠 Running LLM agents...")
        llm_result = self._run_llm()
        print(f"   Done in {llm_result.duration_seconds:.1f}s")
        
        # Calculate improvements
        improvements = self._calc_improvements(fixed_result, llm_result)
        
        report = ComparisonReport(
            llm_result=llm_result,
            fixed_result=fixed_result,
            improvements=improvements,
        )
        
        return report
    
    def _run_fixed(self) -> BenchmarkResult:
        """Run simulation with fixed round-robin timing."""
        sim_config = SimulationConfig(seed=self.seed, arrival_rate=0.5)
        sim = GridSimulation(config=sim_config)
        
        intersection_ids = [f"ix_{r}_{c}" for r in range(3) for c in range(3)]
        phase_cycle = ["NS_GREEN", "EW_GREEN"]
        phase_duration = 30  # steps per phase
        
        start_time = time.time()
        
        for step in range(self.steps):
            sim.step()
            
            # Fixed round-robin: switch phase every phase_duration steps
            for ix_id in intersection_ids:
                ix = sim.intersections[ix_id]
                cycle_pos = (step // phase_duration) % len(phase_cycle)
                new_phase = phase_cycle[cycle_pos]
                if ix.current_phase != new_phase:
                    ix.current_phase = new_phase
                    ix.phase_timer = 0.0
        
        elapsed = time.time() - start_time
        metrics = sim.get_metrics()
        
        return BenchmarkResult(
            name="fixed",
            steps=self.steps,
            metrics=metrics,
            duration_seconds=elapsed,
        )
    
    def _run_llm(self) -> BenchmarkResult:
        """Run simulation with LLM agent decisions."""
        sim_config = SimulationConfig(seed=self.seed, arrival_rate=0.5)
        sim = GridSimulation(config=sim_config)
        
        intersection_ids = [f"ix_{r}_{c}" for r in range(3) for c in range(3)]
        graph = sim.get_graph()
        
        crew_config = CrewConfig(
            llm=self.llm_config,
            decision_interval=5.0,
            enable_coordination=True,
            use_cache=True,
            verbose=False,
        )
        
        crew = TrafficControlCrew(intersection_ids, graph, crew_config)
        
        start_time = time.time()
        
        for step in range(self.steps):
            sim.step()
            
            # LLM decides every 5 steps
            if step % 5 == 0:
                crew.step(sim)
        
        elapsed = time.time() - start_time
        metrics = sim.get_metrics()
        
        return BenchmarkResult(
            name="llm",
            steps=self.steps,
            metrics=metrics,
            duration_seconds=elapsed,
        )
    
    def _calc_improvements(
        self,
        fixed: BenchmarkResult,
        llm: BenchmarkResult,
    ) -> Dict[str, float]:
        """Calculate % improvement for each metric (positive = better)."""
        improvements = {}
        
        fixed_m = fixed.metrics
        llm_m = llm.metrics
        
        # Lower is better
        for key in ["avg_wait_time", "max_wait_time", "total_vehicles"]:
            f_val = fixed_m.get(key, 0)
            l_val = llm_m.get(key, 0)
            if f_val > 0:
                improvements[key] = (f_val - l_val) / f_val * 100
        
        # Higher is better
        for key in ["throughput", "total_served"]:
            f_val = fixed_m.get(key, 0)
            l_val = llm_m.get(key, 0)
            if f_val > 0:
                improvements[key] = (l_val - f_val) / f_val * 100
        
        return improvements
    
    def save(self, report: ComparisonReport, path: str) -> None:
        """Save comparison report to JSON."""
        output = {
            "comparison": report.to_dict(),
            "config": {
                "steps": self.steps,
                "seed": self.seed,
                "llm_model": self.llm_config.fast_model,
            },
        }
        
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Report saved to {path}")
