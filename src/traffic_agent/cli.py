"""
Smart City Agent — CLI Interface

Usage:
    python -m traffic_agent.cli run --scenario single_intersection
    python -m traffic_agent.cli run --scenario grid_3x3 --agents 9
    python -m traffic_agent.cli dashboard --port 8080
    python -m traffic_agent.cli compare --scenario grid_3x3
"""

import argparse
import json
import sys
import time
from typing import List, Optional

import numpy as np

from traffic_agent.agents.intersection import AgentConfig, IntersectionAgent
from traffic_agent.coordination.coordinator import CoordinationLayer
from traffic_agent.simulation.engine import (
    Intersection,
    SimulationConfig,
    SimulationEngine,
)


def create_single_intersection() -> SimulationEngine:
    """Create a single intersection simulation."""
    config = SimulationConfig(
        dt=0.1,
        max_steps=5000,
        arrival_rate=0.5,
        seed=42,
    )
    engine = SimulationEngine(config)
    
    ix = Intersection(
        id="intersection_0",
        approaches=4,
    )
    engine.add_intersection(ix)
    
    return engine


def create_grid_3x3() -> SimulationEngine:
    """Create a 3x3 grid of intersections."""
    config = SimulationConfig(
        dt=0.1,
        max_steps=5000,
        arrival_rate=0.3,
        seed=42,
    )
    engine = SimulationEngine(config)
    
    # Create 9 intersections
    for row in range(3):
        for col in range(3):
            ix_id = f"intersection_{row}_{col}"
            ix = Intersection(id=ix_id, approaches=4)
            engine.add_intersection(ix)
    
    # Connect neighbors
    for row in range(3):
        for col in range(3):
            ix_id = f"intersection_{row}_{col}"
            if col < 2:
                engine.connect(ix_id, f"intersection_{row}_{col+1}")
                engine.connect(f"intersection_{row}_{col+1}", ix_id)
            if row < 2:
                engine.connect(ix_id, f"intersection_{row+1}_{col}")
                engine.connect(f"intersection_{row+1}_{col}", ix_id)
    
    return engine


def run_simulation(args) -> None:
    """Run traffic simulation with RL agents."""
    print("🚦 Smart City Agent — Traffic Simulation")
    print("=" * 50)
    
    # Create simulation
    if args.scenario == "single_intersection":
        engine = create_single_intersection()
    elif args.scenario == "grid_3x3":
        engine = create_grid_3x3()
    else:
        print(f"Unknown scenario: {args.scenario}")
        sys.exit(1)
    
    # Create agents
    agents = {}
    agent_config = AgentConfig(
        learning_rate=args.lr,
        epsilon_start=args.epsilon,
    )
    
    for ix_id in engine.road_network.intersections:
        agent = IntersectionAgent(
            agent_id=ix_id,
            config=agent_config,
            num_approaches=4,
            num_phases=4,
        )
        agents[ix_id] = agent
    
    # Create coordination layer
    graph = {
        ix_id: engine.road_network.get_neighbors(ix_id)
        for ix_id in engine.road_network.intersections
    }
    coordinator = CoordinationLayer(graph)
    
    print(f"📊 Scenario: {args.scenario}")
    print(f"🤖 Agents: {len(agents)}")
    print(f"⏱️  Steps: {args.steps}")
    print(f"🎲 Epsilon: {args.epsilon}")
    print()
    
    # Training loop
    episode_rewards = {ix_id: 0.0 for ix_id in agents}
    
    for step in range(args.steps):
        # Step simulation
        observations = engine.step()
        
        # Each agent decides
        for ix_id, agent in agents.items():
            obs = observations[ix_id]
            agent.observe(obs)
            action = agent.act()
            engine.apply_action(ix_id, action.phase, action.duration)
        
        # Get new observations after actions
        next_observations = engine.step()
        
        # Learn from experience
        for ix_id, agent in agents.items():
            obs = observations[ix_id]
            next_obs = next_observations[ix_id]
            # Simple reward: negative queue length
            reward = -np.sum(next_obs.queue_lengths) * 0.1
            agent.learn(obs, agent.act(), reward, next_obs, done=False)
            episode_rewards[ix_id] += reward
        
        # Print progress
        if step % 500 == 0:
            avg_reward = np.mean(list(episode_rewards.values()))
            metrics = engine.metrics.get_summary()
            print(
                f"Step {step:5d} | "
                f"Avg Reward: {avg_reward:8.1f} | "
                f"Avg Wait: {metrics['avg_wait_time']:5.1f}s | "
                f"Throughput: {metrics['throughput']:4d}"
            )
    
    # Final results
    print()
    print("=" * 50)
    print("📈 Final Results")
    print("=" * 50)
    metrics = engine.metrics.get_summary()
    for key, value in metrics.items():
        print(f"  {key}: {value:.2f}")
    
    print()
    print("🤖 Agent Metrics")
    for ix_id, agent in agents.items():
        agent_metrics = agent.get_metrics()
        print(f"  {ix_id}: avg_reward={agent_metrics['agent/avg_reward']:.2f}")


def compare_timing(args) -> None:
    """Compare AI vs Fixed timing."""
    print("⚖️  AI vs Fixed Timing Comparison")
    print("=" * 50)
    
    # Run AI simulation
    print("\n🤖 Running AI agents...")
    engine_ai = create_grid_3x3()
    agents = {}
    for ix_id in engine_ai.road_network.intersections:
        agent = IntersectionAgent(agent_id=ix_id, num_approaches=4)
        agents[ix_id] = agent
    
    for step in range(2000):
        observations = engine_ai.step()
        for ix_id, agent in agents.items():
            agent.observe(observations[ix_id])
            action = agent.act()
            engine_ai.apply_action(ix_id, action.phase, action.duration)
    
    ai_metrics = engine_ai.metrics.get_summary()
    
    # Run Fixed timing (no RL)
    print("🔴 Running fixed timing...")
    engine_fixed = create_grid_3x3()
    for step in range(2000):
        engine_fixed.step()
    
    fixed_metrics = engine_fixed.metrics.get_summary()
    
    # Compare
    print()
    print("=" * 50)
    print("📊 Comparison Results")
    print("=" * 50)
    print(f"{'Metric':<25} {'Fixed':>10} {'AI':>10} {'Improve':>10}")
    print("-" * 55)
    
    for key in ["avg_wait_time", "throughput", "phase_changes"]:
        fixed_val = fixed_metrics[key]
        ai_val = ai_metrics[key]
        if fixed_val > 0:
            improvement = (fixed_val - ai_val) / fixed_val * 100
        else:
            improvement = 0
        print(f"{key:<25} {fixed_val:>10.1f} {ai_val:>10.1f} {improvement:>9.1f}%")


def launch_dashboard(args) -> None:
    """Launch real-time dashboard."""
    print(f"🌐 Dashboard starting on http://localhost:{args.port}")
    print("   (Dashboard implementation coming soon)")
    print("   Use: python -m traffic_agent.cli run --scenario grid_3x3")


def main():
    parser = argparse.ArgumentParser(
        description="Smart City Agent — AI Traffic Signal Control"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run simulation")
    run_parser.add_argument(
        "--scenario", 
        choices=["single_intersection", "grid_3x3"],
        default="single_intersection",
        help="Simulation scenario"
    )
    run_parser.add_argument("--steps", type=int, default=5000, help="Number of steps")
    run_parser.add_argument("--lr", type=float, default=3e-4, help="Learning rate")
    run_parser.add_argument("--epsilon", type=float, default=1.0, help="Initial epsilon")
    run_parser.set_defaults(func=run_simulation)
    
    # Compare command
    compare_parser = subparsers.add_parser("compare", help="Compare AI vs Fixed")
    compare_parser.add_argument(
        "--scenario",
        choices=["single_intersection", "grid_3x3"],
        default="grid_3x3",
        help="Simulation scenario"
    )
    compare_parser.set_defaults(func=compare_timing)
    
    # Dashboard command
    dashboard_parser = subparsers.add_parser("dashboard", help="Launch dashboard")
    dashboard_parser.add_argument("--port", type=int, default=8080, help="Port")
    dashboard_parser.set_defaults(func=launch_dashboard)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
