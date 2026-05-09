"""
Scenario Comparison — compare fixed vs rule timing across scenarios.

Runs all 4 scenarios and produces a comparison table.

Usage:
    python examples/scenario_compare.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from traffic_agent.scenarios.presets import ALL_SCENARIOS, ScenarioConfig
from traffic_agent.scenarios.runner import ScenarioRunner


def main():
    print("Traffic Scenario Comparison\n")
    print("=" * 60)

    results = []

    for name, scenario in ALL_SCENARIOS.items():
        # Shorten for demo
        short = ScenarioConfig(
            name=scenario.name,
            description=scenario.description,
            phases=scenario.phases[:1],
            seed=42,
            total_steps=50,
        )
        short.phases[0].duration_steps = 50

        runner = ScenarioRunner(short)

        print(f"\n  Running fixed timing: {name}")
        fixed = runner.run_fixed()

        print(f"  Running rule engine: {name}")
        rule = runner.run_rule()

        results.append((name, fixed, rule))

    # Print comparison table
    print("\n" + "=" * 60)
    print(f"{'Scenario':<15} {'Metric':<20} {'Fixed':>10} {'Rule':>10} {'Change':>8}")
    print("-" * 60)

    for name, fixed, rule in results:
        f = fixed.report
        r = rule.report

        for metric, label in [
            ("avg_wait_time", "Avg Wait (s)"),
            ("throughput", "Throughput (/s)"),
            ("total_vehicles_completed", "Completed"),
        ]:
            f_val = getattr(f, metric)
            r_val = getattr(r, metric)
            if f_val > 0:
                change = (r_val - f_val) / f_val * 100
                if metric == "avg_wait_time":
                    change = -change  # lower is better
                print(f"{name:<15} {label:<20} {f_val:>10.2f} {r_val:>10.2f} {change:>+7.1f}%")
        print()

    print("=" * 60)
    print("Done")


if __name__ == "__main__":
    main()
