"""
Scenario Comparison — compare fixed vs rule timing across scenarios.

Runs all available scenarios and produces a comparison table.

Usage:
    python examples/scenario_compare.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from traffic_agent.simulation.scenarios import list_scenarios
from traffic_agent.simulation.sim_loop import TimingSimulation


def main():
    print("Traffic Scenario Comparison\n")
    print("=" * 60)

    scenarios = list_scenarios()
    results = []

    for s in scenarios:
        name = s["name"]
        print(f"\n  Running: {name}")

        # Fixed timing
        sim_fixed = TimingSimulation(
            intersection_type="crossroad",
            scenario_name=name,
            pipeline=None,
            seed=42,
        )
        report_fixed = sim_fixed.run(steps=100, verbose=False)

        # Rule engine
        from traffic_agent.optimization.rule_only import RuleOnlyPipeline

        sim_rule = TimingSimulation(
            intersection_type="crossroad",
            scenario_name=name,
            pipeline=RuleOnlyPipeline(),
            seed=42,
        )
        report_rule = sim_rule.run(steps=100, verbose=False)

        results.append((name, report_fixed, report_rule))

    # Print comparison table
    print("\n" + "=" * 60)
    print(f"{'Scenario':<20} {'Metric':<20} {'Fixed':>10} {'Rule':>10} {'Change':>8}")
    print("-" * 70)

    for name, fixed, rule in results:
        for metric, label in [
            ("avg_wait_time", "Avg Wait (s)"),
            ("throughput", "Throughput (/s)"),
            ("total_vehicles_completed", "Completed"),
        ]:
            f_val = getattr(fixed, metric)
            r_val = getattr(rule, metric)
            if f_val > 0:
                change = (r_val - f_val) / f_val * 100
                if metric == "avg_wait_time":
                    change = -change  # lower is better
                print(f"{name:<20} {label:<20} {f_val:>10.2f} {r_val:>10.2f} {change:>+7.1f}%")
        print()

    print("=" * 60)
    print("Done")


if __name__ == "__main__":
    main()
