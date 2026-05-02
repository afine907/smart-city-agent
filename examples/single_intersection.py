"""
Single Intersection Demo — minimal example of LLM traffic control.

Shows how a single intersection agent makes decisions using LLM.

Usage:
    python examples/single_intersection.py
"""

import os
import sys

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from traffic_agent.llm.client import LLMClient, LLMConfig
from traffic_agent.llm.parser import ResponseParser
from traffic_agent.simulation.engine import Intersection, SimulationConfig
from traffic_agent.tools.traffic_tools import TRAFFIC_EXPERT_PROMPT


def main():
    print("🚦 Single Intersection LLM Demo\n")

    # Create a single intersection
    config = SimulationConfig(arrival_rate=0.5)
    ix = Intersection("center", row=1, col=1, config=config)

    # Initialize LLM
    llm_config = LLMConfig()
    if not llm_config.api_key:
        print("❌ Set LONGCAT_API_KEY environment variable")
        print("   export LONGCAT_API_KEY='your-key'")
        return

    client = LLMClient(llm_config)

    # Simulate 3 steps
    for step in range(3):
        print(f"--- Step {step + 1} ---")

        # Generate some vehicles
        ix.step(1.0)

        # Build state description
        state_text = f"""路口 {ix.intersection_id}:
  当前相位: {ix.current_phase}
  相位计时: {ix.phase_timer:.1f}s
  北方向排队: {len(ix.vehicles.get('north', []))} 辆
  南方向排队: {len(ix.vehicles.get('south', []))} 辆
  东方向排队: {len(ix.vehicles.get('east', []))} 辆
  西方向排队: {len(ix.vehicles.get('west', []))} 辆"""

        print(state_text)

        # Ask LLM for decision
        system = TRAFFIC_EXPERT_PROMPT.format(intersection_id=ix.intersection_id)
        response = client.chat(
            system_prompt=system,
            user_message=f"当前路况:\n{state_text}\n\n请做出信号灯决策（JSON格式）。",
            temperature=0.3,
        )

        decision = ResponseParser.parse(response.content)
        if decision:
            print(f"  🧠 LLM 决策: {decision.phase} ({decision.duration}s)")
            print(f"  💭 推理: {decision.reasoning}")
            print(f"  📊 Token: {response.tokens_input}+{response.tokens_output}")
        else:
            print("  ⚠️ 解析失败，使用回退")
            decision = ResponseParser.fallback("解析失败")

        print()

    print("✅ Demo 完成")


if __name__ == "__main__":
    main()
