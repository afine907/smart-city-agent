"""
Layered Model Demo — shows the three-layer decision pipeline.

Demonstrates how decisions route through rules → cache → LLM.

Usage:
    python examples/layered_demo.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from traffic_agent.llm.client import LLMConfig
from traffic_agent.optimization.layered import LayeredDecisionMaker
from traffic_agent.tools.traffic_tools import IntersectionState


def make_state(
    intersection_id: str = "center",
    queue_north: int = 0,
    queue_south: int = 0,
    queue_east: int = 0,
    queue_west: int = 0,
    phase: str = "NS_GREEN",
) -> IntersectionState:
    """Helper to create an IntersectionState for testing."""
    return IntersectionState(
        intersection_id=intersection_id,
        queue_north=queue_north,
        queue_south=queue_south,
        queue_east=queue_east,
        queue_west=queue_west,
        current_phase=phase,
        phase_timer=15.0,
        time_since_change=15.0,
        emergency=False,
        emergency_direction=None,
        avg_wait_time=10.0,
        max_wait_time=20.0,
        total_passed=100,
    )


def main():
    print("🧠 Layered Decision Model Demo\n")

    llm_config = LLMConfig()
    if not llm_config.api_key:
        print("❌ Set LONGCAT_API_KEY environment variable")
        return

    maker = LayeredDecisionMaker(llm_config=llm_config)

    scenarios = [
        ("简单: 低流量", make_state(queue_north=1, queue_south=0, queue_east=0, queue_west=0)),
        ("中等: 不均衡", make_state(queue_north=3, queue_south=2, queue_east=10, queue_west=8)),
        ("复杂: 高流量", make_state(queue_north=12, queue_south=10, queue_east=15, queue_west=11)),
        ("紧急: 救护车", make_state(queue_north=5, queue_south=3, queue_east=8, queue_west=6)),
    ]

    # Set emergency on last one
    scenarios[3][1].emergency = True
    scenarios[3][1].emergency_direction = "north"

    for label, state in scenarios:
        print(f"--- {label} ---")
        print(f"  排队: N={state.queue_north} S={state.queue_south} E={state.queue_east} W={state.queue_west}")
        decision = maker.decide(state)
        print(f"  → 决策: {decision.phase} ({decision.duration}s)")
        print(f"  💭 {decision.reasoning[:60]}...")
        print()

    # Print stats
    stats = maker.get_stats()
    print("=" * 50)
    print("📊 决策统计:")
    print(f"  总决策: {stats['total_decisions']}")
    print(f"  Layer 1 (规则): {stats['layer1_rules']} ({stats['rule_rate']:.0%})")
    print(f"  Layer 2 (缓存): {stats['layer2_cache']} ({stats['cache_rate']:.0%})")
    print(f"  Layer 3 (LLM):  {stats['layer3_llm']} ({stats['llm_rate']:.0%})")
    print(f"  免费率: {stats['free_rate']:.0%}")
    print()
    print("✅ Demo 完成")


if __name__ == "__main__":
    main()
