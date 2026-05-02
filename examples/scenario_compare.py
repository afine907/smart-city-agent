"""
Scenario Comparison — compare LLM vs fixed timing across scenarios.

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
    print("🚦 Multi-Scenario Comparison\n")
    print("=" * 60)

    results = []

    for name, scenario in ALL_SCENARIOS.items():
        # Shorten phases for demo
        short_scenario = ScenarioConfig(
            name=scenario.name,
            description=scenario.description,
            phases=[
                type(p)(
                    name=p.name,
                    duration_steps=min(p.duration_steps, 30),
                    arrival_rate=p.arrival_rate,
                    emergency_rate=p.emergency_rate,
                    direction_bias=p.direction_bias,
                    description=p.description,
                )
                for p in scenario.phases[:1]
            ],
            seed=42,
            total_steps=30,
        )

        print(f"\n🔴 Running fixed timing: {name}")
        runner = ScenarioRunner(short_scenario)
        fixed = runner.run_with_fixed()

        print(f"🧠 Running LLM agents: {name}")
        llm = runner.run_with_llm()

        results.append((name, fixed, llm))

    # Print comparison table
    print("\n" + "=" * 60)
    print(f"{'场景':<15} {'指标':<15} {'固定配时':>10} {'LLM':>10} {'改善':>8}")
    print("-" * 60)

    for name, fixed, llm in results:
        for metric in ["avg_wait_time", "throughput", "total_queue"]:
            f_val = fixed.metrics.get(metric, 0)
            l_val = llm.metrics.get(metric, 0)

            if f_val > 0:
                if metric in ["avg_wait_time", "total_queue"]:
                    improvement = (f_val - l_val) / f_val * 100
                else:
                    improvement = (l_val - f_val) / f_val * 100
                print(f"{name:<15} {metric:<15} {f_val:>10.1f} {l_val:>10.1f} {improvement:>+7.1f}%")
        print()

    print("=" * 60)
    print("✅ 对比完成")


if __name__ == "__main__":
    main()
