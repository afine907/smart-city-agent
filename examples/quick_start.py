"""
Quick Start — Minimal example to run a traffic simulation.

This example demonstrates the simplest way to use the traffic simulation
with rule-based timing adjustments.

Usage:
    python examples/quick_start.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from traffic_agent.optimization.rule_only import RuleOnlyPipeline
from traffic_agent.simulation.sim_loop import TimingSimulation


def main():
    print("🚦 Traffic Simulation Quick Start\n")

    # Create simulation with rule engine
    sim = TimingSimulation(
        intersection_type="crossroad",
        scenario_name="morning_peak",
        pipeline=RuleOnlyPipeline(),
        seed=42,
    )

    # Run 100 steps
    print("Running simulation (100 steps)...")
    report = sim.run(steps=100, verbose=False)

    # Print results
    print(f"\n{'='*40}")
    print(f"  Results:")
    print(f"{'='*40}")
    print(f"  Vehicles generated: {report.total_vehicles_generated}")
    print(f"  Vehicles completed: {report.total_vehicles_completed}")
    print(f"  Avg wait time: {report.avg_wait_time:.1f}s")
    print(f"  Throughput: {report.throughput:.2f} veh/s")
    print(f"  Adjustments: {report.adjustments_made}")
    print(f"{'='*40}")

    # Export results
    export_path = "examples/quick_start_result.json"
    sim.export_log(export_path)
    print(f"\n✅ Results exported to {export_path}")


if __name__ == "__main__":
    main()
