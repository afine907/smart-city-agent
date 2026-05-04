"""
Reasoning Quality Benchmark — Quantitative comparison of traffic control strategies.

Compares three approaches:
1. Fixed timing (round-robin)
2. Adaptive rules (queue-length based, like SCATS/SCOOT)
3. LLM agents (our AI system)

Supports both 3x3 grid and OSM presets.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from traffic_agent.simulation.engine import Intersection, SimulationConfig, Vehicle
from traffic_agent.simulation.grid import GridSimulation
from traffic_agent.simulation.osm_sim import OSMSimulation


# ─── Strategy Implementations ──────────────────────────────────────


class FixedTimingStrategy:
    """Fixed round-robin timing. No adaptation."""

    def __init__(self, phase_duration: int = 30):
        self.phase_duration = phase_duration
        self.phase_cycle = ["NS_GREEN", "EW_GREEN"]

    def decide(self, intersection: Intersection, step: int) -> str:
        cycle_pos = (step // self.phase_duration) % len(self.phase_cycle)
        return self.phase_cycle[cycle_pos]


class AdaptiveRuleStrategy:
    """
    Queue-length adaptive strategy (simplified SCATS/SCOOT).

    Extends green phase when queue is long, switches when queue is short.
    More realistic baseline than fixed timing.
    """

    def __init__(self, min_green: int = 10, max_green: int = 60, threshold: int = 5):
        self.min_green = min_green
        self.max_green = max_green
        self.threshold = threshold

    def decide(self, intersection: Intersection, step: int) -> str:
        # Count queues for each phase (approach 0=N, 2=S → NS; 1=E, 3=W → EW)
        ns_queue = intersection.get_queue(0) + intersection.get_queue(2)
        ew_queue = intersection.get_queue(1) + intersection.get_queue(3)

        current_phase = intersection.current_phase
        timer = intersection.phase_timer

        # Determine preferred phase based on queue
        if ns_queue > ew_queue + self.threshold:
            preferred = "NS_GREEN"
        elif ew_queue > ns_queue + self.threshold:
            preferred = "EW_GREEN"
        else:
            preferred = current_phase  # Keep current

        # Switch if: min green elapsed AND (preferred is different OR max green hit)
        if timer >= self.min_green:
            if current_phase != preferred:
                return preferred
            if timer >= self.max_green:
                # Force switch
                return "EW_GREEN" if current_phase == "NS_GREEN" else "NS_GREEN"

        return current_phase


# ─── Simulation Runners ────────────────────────────────────────────


def _run_simulation(
    sim,
    strategy_name: str,
    strategy,
    steps: int,
    use_llm: bool = False,
) -> Dict[str, Any]:
    """Run a simulation with the given strategy and return metrics."""
    start_time = time.time()
    wait_times = []
    queue_lengths = []

    for step in range(steps):
        sim.step()

        # Apply strategy to each intersection
        for ix_id, ix in sim.intersections.items():
            if use_llm:
                # LLM decisions happen externally via crew.step()
                continue
            new_phase = strategy.decide(ix, step)
            if new_phase != ix.current_phase:
                ix.current_phase = new_phase
                ix.phase_timer = 0.0

        # Collect per-step metrics
        metrics = sim.get_metrics()
        queue_lengths.append(metrics["total_queue"])
        wait_times.append(metrics["avg_wait_time"])

    elapsed = time.time() - start_time
    final_metrics = sim.get_metrics()

    # Compute percentiles
    wait_arr = np.array(wait_times) if wait_times else np.array([0])
    queue_arr = np.array(queue_lengths) if queue_lengths else np.array([0])

    return {
        "name": strategy_name,
        "steps": steps,
        "duration_seconds": elapsed,
        "final_metrics": final_metrics,
        "avg_wait_time": float(np.mean(wait_arr)),
        "p50_wait_time": float(np.percentile(wait_arr, 50)),
        "p95_wait_time": float(np.percentile(wait_arr, 95)),
        "p99_wait_time": float(np.percentile(wait_arr, 99)),
        "max_wait_time": float(np.max(wait_arr)),
        "avg_queue": float(np.mean(queue_arr)),
        "max_queue": float(np.max(queue_arr)),
        "throughput": final_metrics.get("throughput", 0),
        "vehicles_generated": final_metrics.get("vehicles_generated", 0),
        "vehicles_completed": final_metrics.get("vehicles_completed", 0),
    }


def run_fixed_benchmark(preset: str | None, steps: int, seed: int) -> Dict[str, Any]:
    """Run fixed timing benchmark."""
    config = SimulationConfig(seed=seed, arrival_rate=0.5)
    sim = OSMSimulation.from_preset(preset, config) if preset else GridSimulation(config=config)
    strategy = FixedTimingStrategy()
    return _run_simulation(sim, "fixed_timing", strategy, steps)


def run_adaptive_benchmark(preset: str | None, steps: int, seed: int) -> Dict[str, Any]:
    """Run adaptive rule-based benchmark."""
    config = SimulationConfig(seed=seed, arrival_rate=0.5)
    sim = OSMSimulation.from_preset(preset, config) if preset else GridSimulation(config=config)
    strategy = AdaptiveRuleStrategy()
    return _run_simulation(sim, "adaptive_rules", strategy, steps)


def run_random_benchmark(preset: str | None, steps: int, seed: int) -> Dict[str, Any]:
    """Run random phase selection benchmark (worst case baseline)."""
    config = SimulationConfig(seed=seed, arrival_rate=0.5)
    sim = OSMSimulation.from_preset(preset, config) if preset else GridSimulation(config=config)

    class RandomStrategy:
        def decide(self, intersection, step):
            return np.random.choice(["NS_GREEN", "EW_GREEN"])

    return _run_simulation(sim, "random", RandomStrategy(), steps)


def run_llm_benchmark(
    preset: str | None,
    steps: int,
    seed: int,
    api_key: str | None = None,
    api_base: str | None = None,
    model: str = "LongCat-Flash-Chat",
) -> Dict[str, Any]:
    """Run LLM agent benchmark using LongCat API."""
    from traffic_agent.llm.client import LLMClient, LLMConfig
    from traffic_agent.crew.traffic_crew import CrewConfig, TrafficControlCrew

    config = SimulationConfig(seed=seed, arrival_rate=0.5)
    sim = OSMSimulation.from_preset(preset, config) if preset else GridSimulation(config=config)

    intersection_ids = list(sim.intersections.keys())
    graph = sim.get_graph() if hasattr(sim, "get_graph") else {
        ix_id: sim.get_neighbors(ix_id)
        for ix_id in sim.intersections
    }

    llm_config = LLMConfig(
        fast_model=model,
        api_key=api_key,
        api_base=api_base,
    )
    crew_config = CrewConfig(
        llm=llm_config,
        decision_interval=5.0,
        enable_coordination=True,
        use_cache=True,
        verbose=False,
    )

    crew = TrafficControlCrew(intersection_ids, graph, crew_config)

    start_time = time.time()
    wait_times = []
    queue_lengths = []

    for step in range(steps):
        sim.step()

        # LLM agents decide every 5 steps
        if step % 5 == 0:
            crew.step(sim)

        metrics = sim.get_metrics()
        queue_lengths.append(metrics["total_queue"])
        wait_times.append(metrics["avg_wait_time"])

    elapsed = time.time() - start_time
    final_metrics = sim.get_metrics()
    crew_metrics = crew.get_metrics()

    wait_arr = np.array(wait_times) if wait_times else np.array([0])
    queue_arr = np.array(queue_lengths) if queue_lengths else np.array([0])

    return {
        "name": f"llm_{model}",
        "steps": steps,
        "duration_seconds": elapsed,
        "final_metrics": final_metrics,
        "avg_wait_time": float(np.mean(wait_arr)),
        "p50_wait_time": float(np.percentile(wait_arr, 50)),
        "p95_wait_time": float(np.percentile(wait_arr, 95)),
        "p99_wait_time": float(np.percentile(wait_arr, 99)),
        "max_wait_time": float(np.max(wait_arr)),
        "avg_queue": float(np.mean(queue_arr)),
        "max_queue": float(np.max(queue_arr)),
        "throughput": final_metrics.get("throughput", 0),
        "vehicles_generated": final_metrics.get("vehicles_generated", 0),
        "vehicles_completed": final_metrics.get("vehicles_completed", 0),
        "llm_calls": crew_metrics["total_llm_calls"],
        "cache_hit_rate": crew_metrics["cache_hit_rate"],
        "llm_cost": crew_metrics["llm_stats"]["total_cost"],
    }


# ─── Report Generation ─────────────────────────────────────────────


def generate_report(results: list[Dict[str, Any]], preset: str | None = None) -> str:
    """Generate a formatted comparison report."""
    lines = []
    net_label = preset.upper() if preset else "3×3 Grid"
    lines.append(f"{'='*65}")
    lines.append(f"  🚦 Traffic Control Strategy Benchmark — {net_label}")
    lines.append(f"{'='*65}")
    lines.append("")

    # Table header
    lines.append(f"  {'Strategy':<20} {'AvgWait':>8} {'P95':>8} {'P99':>8} {'MaxQ':>6} {'TP':>6}")
    lines.append(f"  {'-'*56}")

    for r in results:
        lines.append(
            f"  {r['name']:<20} "
            f"{r['avg_wait_time']:>7.1f}s "
            f"{r['p95_wait_time']:>7.1f}s "
            f"{r['p99_wait_time']:>7.1f}s "
            f"{r['max_queue']:>5.0f} "
            f"{r['throughput']:>5.2f}"
        )

    lines.append("")

    # Improvement analysis (vs fixed timing)
    if len(results) >= 2:
        fixed = results[0]
        lines.append(f"  📈 Improvement vs {fixed['name']}:")
        lines.append(f"  {'-'*40}")
        for r in results[1:]:
            wait_imp = (fixed["avg_wait_time"] - r["avg_wait_time"]) / max(0.1, fixed["avg_wait_time"]) * 100
            p95_imp = (fixed["p95_wait_time"] - r["p95_wait_time"]) / max(0.1, fixed["p95_wait_time"]) * 100
            tp_imp = (r["throughput"] - fixed["throughput"]) / max(0.01, fixed["throughput"]) * 100

            arrow_w = "✅" if wait_imp > 0 else "❌"
            arrow_tp = "✅" if tp_imp > 0 else "❌"

            lines.append(
                f"    {r['name']:<20} "
                f"wait: {wait_imp:+.1f}% {arrow_w}  "
                f"throughput: {tp_imp:+.1f}% {arrow_tp}"
            )
        lines.append("")

    # Detailed stats
    lines.append(f"  📊 Detailed Statistics:")
    lines.append(f"  {'-'*40}")
    for r in results:
        lines.append(f"    {r['name']}:")
        lines.append(f"      Vehicles: {r['vehicles_generated']} generated, {r['vehicles_completed']} completed")
        lines.append(f"      Wait: avg={r['avg_wait_time']:.1f}s, p50={r['p50_wait_time']:.1f}s, p95={r['p95_wait_time']:.1f}s, p99={r['p99_wait_time']:.1f}s")
        lines.append(f"      Queue: avg={r['avg_queue']:.1f}, max={r['max_queue']:.0f}")
        lines.append(f"      Duration: {r['duration_seconds']:.1f}s")

    lines.append(f"{'='*65}")
    return "\n".join(lines)


def save_report(
    results: list[Dict[str, Any]],
    path: str,
    config: dict | None = None,
) -> None:
    """Save full report as JSON."""
    output = {
        "results": results,
        "config": config or {},
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"💾 Report saved to {path}")
