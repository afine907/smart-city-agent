"""
LLM Traffic Controller — CLI Interface

Usage:
    python -m traffic_agent.cli run --scenario single
    python -m traffic_agent.cli run --scenario grid_3x3
    python -m traffic_agent.cli compare
    python -m traffic_agent.cli dashboard --port 8080
"""

import argparse
import json
import sys
import time
from typing import Dict, List

from traffic_agent.crew.traffic_crew import TrafficControlCrew, CrewConfig
from traffic_agent.llm.client import LLMConfig
from traffic_agent.simulation.engine import SimulationConfig, SimulationEngine


def create_single() -> SimulationEngine:
    """Create single intersection simulation."""
    config = SimulationConfig(dt=1.0, max_steps=500, seed=42)
    engine = SimulationEngine(config)
    engine.add_intersection("intersection_0")
    return engine


def create_grid_3x3() -> SimulationEngine:
    """Create 3x3 grid of intersections."""
    config = SimulationConfig(dt=1.0, max_steps=500, seed=42)
    engine = SimulationEngine(config)
    
    # Create 9 intersections
    for row in range(3):
        for col in range(3):
            engine.add_intersection(f"ix_{row}_{col}")
    
    # Connect neighbors
    for row in range(3):
        for col in range(3):
            ix_id = f"ix_{row}_{col}"
            if col < 2:
                engine.connect(ix_id, f"ix_{row}_{col+1}")
                engine.connect(f"ix_{row}_{col+1}", ix_id)
            if row < 2:
                engine.connect(ix_id, f"ix_{row+1}_{col}")
                engine.connect(f"ix_{row+1}_{col}", ix_id)
    
    return engine


def create_grid_3x3_graph() -> Dict[str, List[str]]:
    """Create adjacency list for 3x3 grid."""
    graph = {}
    for row in range(3):
        for col in range(3):
            ix_id = f"ix_{row}_{col}"
            neighbors = []
            if col > 0: neighbors.append(f"ix_{row}_{col-1}")
            if col < 2: neighbors.append(f"ix_{row}_{col+1}")
            if row > 0: neighbors.append(f"ix_{row-1}_{col}")
            if row < 2: neighbors.append(f"ix_{row+1}_{col}")
            graph[ix_id] = neighbors
    return graph


def run_simulation(args) -> None:
    """Run traffic simulation with LLM agents."""
    print("🚦 LLM Traffic Controller")
    print("=" * 50)
    
    # Create simulation
    if args.scenario == "single":
        engine = create_single()
        intersection_ids = ["intersection_0"]
        graph = {"intersection_0": []}
    elif args.scenario == "grid_3x3":
        engine = create_grid_3x3()
        intersection_ids = [f"ix_{r}_{c}" for r in range(3) for c in range(3)]
        graph = create_grid_3x3_graph()
    else:
        print(f"Unknown scenario: {args.scenario}")
        sys.exit(1)
    
    # Configure LLM
    llm_config = LLMConfig(
        fast_model=args.model,
        api_key=args.api_key,
    )
    
    crew_config = CrewConfig(
        llm=llm_config,
        decision_interval=args.interval,
        verbose=args.verbose,
        use_cache=not args.no_cache,
        enable_coordination=not args.no_coordination,
    )
    
    # Create crew
    crew = TrafficControlCrew(intersection_ids, graph, crew_config)
    
    print(f"📊 Scenario: {args.scenario}")
    print(f"🤖 Intersections: {len(intersection_ids)}")
    print(f"🧠 Model: {args.model}")
    print(f"⏱️  Steps: {args.steps}")
    print(f"🔄 Decision interval: {args.interval}s")
    print()
    
    # Run simulation loop
    for step in range(args.steps):
        # Advance simulation
        engine.step()
        
        # LLM agents decide (at specified intervals)
        if step % max(1, int(args.interval)) == 0:
            decisions = crew.step(engine)
            
            if args.verbose and decisions:
                for d in decisions:
                    print(f"  🚦 {d['intersection_id']}: "
                          f"{d['phase']} {d['duration']}s — "
                          f"{d['reasoning'][:60]}...")
        
        # Progress
        if step % 100 == 0:
            metrics = engine._get_metrics()
            crew_metrics = crew.get_metrics()
            print(
                f"Step {step:4d} | "
                f"Queue: {metrics.get('total_vehicles', 0):3d} | "
                f"Wait: {metrics.get('avg_wait_time', 0):5.1f}s | "
                f"Calls: {crew_metrics['total_llm_calls']} | "
                f"Cache: {crew_metrics['cache_hit_rate']:.0%}"
            )
    
    # Final results
    print()
    print("=" * 50)
    print("📈 Final Results")
    print("=" * 50)
    
    metrics = engine._get_metrics()
    crew_metrics = crew.get_metrics()
    
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")
    
    print()
    print("💰 LLM Usage")
    for key, value in crew_metrics.items():
        if isinstance(value, dict):
            for k, v in value.items():
                print(f"  {key}.{k}: {v}")
        elif isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")
    
    # Show reasoning samples
    if args.verbose:
        print()
        print("🧠 Sample Reasoning")
        print("-" * 50)
        for ix_id in intersection_ids[:3]:
            history = crew.get_reasoning_history(ix_id, limit=1)
            if history:
                d = history[0]
                print(f"\n{ix_id}:")
                print(f"  Phase: {d.get('phase')} | Duration: {d.get('duration')}s")
                print(f"  Reasoning: {d.get('reasoning', 'N/A')}")


def compare_timing(args) -> None:
    """Compare LLM vs fixed timing."""
    print("⚖️  LLM vs Fixed Timing Comparison")
    print("=" * 50)
    
    # Run LLM simulation
    print("\n🧠 Running LLM agents...")
    engine_llm = create_grid_3x3()
    intersection_ids = [f"ix_{r}_{c}" for r in range(3) for c in range(3)]
    graph = create_grid_3x3_graph()
    
    crew = TrafficControlCrew(
        intersection_ids, graph,
        CrewConfig(llm=LLMConfig(fast_model=args.model))
    )
    
    for step in range(200):
        engine_llm.step()
        if step % 5 == 0:
            crew.step(engine_llm)
    
    llm_metrics = engine_llm._get_metrics()
    
    # Run fixed timing
    print("🔴 Running fixed timing...")
    engine_fixed = create_grid_3x3()
    for step in range(200):
        engine_fixed.step()
    
    fixed_metrics = engine_fixed._get_metrics()
    
    # Compare
    print()
    print("=" * 50)
    print("📊 Comparison Results")
    print("=" * 50)
    print(f"{'Metric':<25} {'Fixed':>10} {'LLM':>10} {'Improve':>10}")
    print("-" * 55)
    
    for key in ["avg_wait_time", "total_vehicles"]:
        fixed_val = fixed_metrics.get(key, 0)
        llm_val = llm_metrics.get(key, 0)
        if fixed_val > 0:
            improvement = (fixed_val - llm_val) / fixed_val * 100
        else:
            improvement = 0
        print(f"{key:<25} {fixed_val:>10.1f} {llm_val:>10.1f} {improvement:>9.1f}%")


def main():
    parser = argparse.ArgumentParser(
        description="LLM Traffic Controller — AI-Powered Traffic Signal Control"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run simulation")
    run_parser.add_argument("--scenario", choices=["single", "grid_3x3"],
                           default="single", help="Simulation scenario")
    run_parser.add_argument("--steps", type=int, default=500, help="Steps")
    run_parser.add_argument("--model", default="gpt-4o-mini", help="LLM model")
    run_parser.add_argument("--api-key", default=None, help="API key")
    run_parser.add_argument("--interval", type=float, default=5.0,
                           help="Decision interval (seconds)")
    run_parser.add_argument("--verbose", action="store_true", help="Show reasoning")
    run_parser.add_argument("--no-cache", action="store_true", help="Disable cache")
    run_parser.add_argument("--no-coordination", action="store_true",
                           help="Disable coordination")
    run_parser.set_defaults(func=run_simulation)
    
    # Compare command
    compare_parser = subparsers.add_parser("compare", help="Compare LLM vs Fixed")
    compare_parser.add_argument("--model", default="gpt-4o-mini", help="LLM model")
    compare_parser.set_defaults(func=compare_timing)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
