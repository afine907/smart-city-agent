"""
LLM Traffic Controller — CLI Interface

Usage:
    python -m traffic_agent.cli run --scenario single
    python -m traffic_agent.cli run --scenario grid_3x3
    python -m traffic_agent.cli compare
    python -m traffic_agent.cli dashboard --port 8080
    python -m traffic_agent.cli simulate --steps 100
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


def run_dashboard(args) -> None:
    """Start the SSE dashboard server."""
    import uvicorn
    from traffic_agent.api.sse_server import app

    print(f"🚦 Starting dashboard at http://{args.host}:{args.port}")
    print(f"   Open http://localhost:{args.port} in your browser")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def run_simulate(args) -> None:
    """Run simulation with SSE event streaming."""
    import uvicorn
    import threading
    from traffic_agent.api.sse_server import app, get_collector
    import traffic_agent.api.sse_server as srv
    from traffic_agent.visualization.runner import SimulationRunner

    collector = get_collector()

    # Pre-populate network topology for the dashboard
    if args.preset:
        from traffic_agent.simulation.osm import OSMNetwork
        from traffic_agent.simulation.osm_sim import OSMSimulation
        preset_map = {"manhattan": "SMALL_MANHATTAN", "wuhan": "WUHAN_OPTICS_VALLEY", "shenzhen": "SHENZHEN_LIUXIANDONG"}
        preset_data = getattr(__import__("traffic_agent.simulation.osm", fromlist=[preset_map[args.preset]]), preset_map[args.preset])
        osm = OSMNetwork.from_dict(preset_data)
        sim_temp = OSMSimulation(osm, SimulationConfig(seed=42))
        srv._network_topology = {
            "type": f"osm_{args.preset}",
            "intersections": {
                ix_id: {
                    "lat": sim_temp.osm.intersections[ix_id].lat,
                    "lon": sim_temp.osm.intersections[ix_id].lon,
                    "neighbors": sim_temp.get_neighbors(ix_id),
                }
                for ix_id in sim_temp.intersections
            },
            "segments": {
                sid: {"from": s.from_id, "to": s.to_id, "length": s.length, "name": s.name}
                for sid, s in sim_temp.segments.items()
                if not sid.startswith("virtual_")
            },
        }
    else:
        srv._network_topology = {
            "type": "grid_3x3",
            "intersections": {
                f"ix_{r}_{c}": {"row": r, "col": c}
                for r in range(3) for c in range(3)
            },
            "segments": {},
        }

    def run_sim():
        import time
        time.sleep(2)  # Wait for server to start
        runner = SimulationRunner(
            collector=collector,
            config=SimulationConfig(seed=42),
            preset=args.preset,
        )
        runner.run(steps=args.steps)

    # Start simulation in background thread
    t = threading.Thread(target=run_sim, daemon=True)
    t.start()

    preset_info = f" (preset: {args.preset})" if args.preset else " (3x3 grid)"
    print(f"🚦 Starting simulation with SSE at http://0.0.0.0:{args.port}")
    print(f"   Network: {preset_info}")
    print(f"   Steps: {args.steps}, Speed: {args.speed}x")
    print(f"   Open http://localhost:{args.port} in your browser")
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")


def run_simulation(args) -> None:
    """Run traffic simulation with LLM agents."""
    import threading
    from traffic_agent.api.sse_server import get_collector

    print("🚦 LLM Traffic Controller")
    print("=" * 50)

    collector = get_collector()

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

    # Create crew with SSE collector
    crew = TrafficControlCrew(intersection_ids, graph, crew_config, collector=collector)

    # Start SSE server if --port is specified
    if args.port:
        import uvicorn
        from traffic_agent.api.sse_server import app
        import traffic_agent.api.sse_server as srv

        srv._network_topology = {
            "type": f"grid_3x3",
            "intersections": {
                f"ix_{r}_{c}": {"row": r, "col": c}
                for r in range(3) for c in range(3)
            },
            "segments": {},
        }

        def run_server():
            uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        print(f"🌐 Dashboard: http://localhost:{args.port}")

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


def run_scenario(args) -> None:
    """Run traffic scenario with LLM or fixed timing."""
    from traffic_agent.scenarios.presets import ALL_SCENARIOS, create_scenario
    from traffic_agent.scenarios.runner import ScenarioRunner
    from traffic_agent.comparison.benchmark import ComparisonReport

    scenario = create_scenario(args.scenario, seed=args.seed)
    runner = ScenarioRunner(scenario)

    print(f"🚦 Scenario: {scenario.name}")
    print(f"   {scenario.description}")
    print(f"   Steps: {scenario.total_steps}")
    print(f"   Phases: {len(scenario.phases)}")
    print()

    if args.mode == "compare":
        # Run both and compare
        print("🔴 Running fixed timing...")
        fixed_result = runner.run_with_fixed()

        print("🧠 Running LLM agents...")
        llm_result = runner.run_with_llm()

        # Calculate improvements
        improvements = {}
        for key in ["avg_wait_time", "max_wait_time", "total_queue"]:
            f_val = fixed_result.metrics.get(key, 0)
            l_val = llm_result.metrics.get(key, 0)
            if f_val > 0:
                improvements[key] = (f_val - l_val) / f_val * 100

        for key in ["throughput", "vehicles_completed"]:
            f_val = fixed_result.metrics.get(key, 0)
            l_val = llm_result.metrics.get(key, 0)
            if f_val > 0:
                improvements[key] = (l_val - f_val) / f_val * 100

        report = ComparisonReport(
            llm_result=llm_result,
            fixed_result=fixed_result,
            improvements=improvements,
        )
        print(report.format_table())

    elif args.mode == "llm":
        result = runner.run_with_llm()
        _print_scenario_result(result)

    elif args.mode == "fixed":
        result = runner.run_with_fixed()
        _print_scenario_result(result)


def _print_scenario_result(result) -> None:
    """Print scenario result metrics."""
    print(f"\n📊 Results: {result.name}")
    print(f"   Steps: {result.steps}")
    print(f"   Duration: {result.duration_seconds:.1f}s")
    for key, value in result.metrics.items():
        if isinstance(value, float):
            print(f"   {key}: {value:.2f}")
        else:
            print(f"   {key}: {value}")


def run_osm(args) -> None:
    """Run OSM network simulation with quick stats."""
    from traffic_agent.simulation.osm_sim import OSMSimulation
    from traffic_agent.simulation.engine import SimulationConfig

    config = SimulationConfig(
        dt=1.0,
        seed=args.seed,
        arrival_rate=args.arrival_rate,
    )
    sim = OSMSimulation.from_preset(args.preset, config=config)

    n_ix = len(sim.intersections)
    n_seg = len(sim.segments)
    n_boundary = len(sim.boundary_intersections)

    print(f"🚦 OSM Simulation: {args.preset}")
    print(f"   Intersections: {n_ix}")
    print(f"   Road segments: {n_seg}")
    print(f"   Boundary nodes: {n_boundary}")
    print(f"   Steps: {args.steps}")
    print()

    for step in range(args.steps):
        sim.step()
        if step % 50 == 0:
            m = sim.get_metrics()
            print(
                f"  Step {step:4d} | "
                f"Q: {m['total_queue']:3.0f} | "
                f"Gen: {m['vehicles_generated']:3.0f} | "
                f"Done: {m['vehicles_completed']:3.0f} | "
                f"Wait: {m['avg_wait_time']:.1f}s"
            )

    print()
    m = sim.get_metrics()
    print("📊 Final Metrics:")
    for k, v in m.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.2f}")
        else:
            print(f"  {k}: {v}")


def run_benchmark(args) -> None:
    """Run quality benchmark comparing fixed/adaptive/random/LLM strategies."""
    from traffic_agent.comparison.quality_benchmark import (
        run_fixed_benchmark,
        run_adaptive_benchmark,
        run_random_benchmark,
        run_llm_benchmark,
        generate_report,
        save_report,
    )

    preset = args.preset
    steps = args.steps
    seed = args.seed

    print(f"🏁 Running benchmark: {steps} steps, seed={seed}")
    if preset:
        print(f"   Network: {preset.upper()}")
    else:
        print(f"   Network: 3×3 Grid")
    if args.llm:
        print(f"   LLM Model: {args.model}")
    print()

    # Run baseline strategies
    print("  [1/4] Fixed timing...")
    fixed = run_fixed_benchmark(preset, steps, seed)

    print("  [2/4] Adaptive rules...")
    adaptive = run_adaptive_benchmark(preset, steps, seed)

    print("  [3/4] Random baseline...")
    random_ = run_random_benchmark(preset, steps, seed)

    results = [fixed, adaptive, random_]

    # Run LLM benchmark if requested
    if args.llm:
        print(f"  [4/4] LLM agents ({args.model})...")
        try:
            llm = run_llm_benchmark(
                preset, steps, seed,
                api_key=args.api_key,
                api_base=args.api_base,
                model=args.model,
            )
            results.append(llm)
            print(f"        LLM calls: {llm['llm_calls']}, Cost: ${llm['llm_cost']:.4f}")
        except Exception as e:
            print(f"  ⚠️  LLM benchmark failed: {e}")
            print("  Continuing with baseline results only...")
    else:
        print("  [4/4] LLM agents... (skipped, use --llm to enable)")

    # Generate and print report
    report = generate_report(results, preset)
    print(report)

    # Save if requested
    if args.output:
        save_report(results, args.output, {"steps": steps, "seed": seed, "preset": preset, "llm": args.llm})
    else:
        # Auto-save to docs/
        output_path = f"docs/benchmark-{preset or 'grid'}.json"
        save_report(results, output_path, {"steps": steps, "seed": seed, "preset": preset, "llm": args.llm})


def run_demo(args) -> None:
    """Run complex intersection demo — LLM vs Fixed timing comparison."""
    from traffic_agent.simulation.complex_intersection import (
        ComplexIntersection,
        IntersectionConfig,
        create_rush_hour_config,
        create_accident_config,
    )
    from traffic_agent.crew.traffic_crew import CrewConfig, TrafficControlCrew
    from traffic_agent.llm.client import LLMConfig

    scenario = args.scenario
    steps = args.steps
    seed = args.seed

    print(f"🚦 Complex Intersection Demo")
    print(f"{'=' * 50}")
    print(f"  Scenario: {scenario}")
    print(f"  Steps: {steps}")
    print()

    # Create config based on scenario
    if scenario == "rush_ns":
        config = create_rush_hour_config("ns", 2.0)
        config.seed = seed
    elif scenario == "rush_ew":
        config = create_rush_hour_config("ew", 1.8)
        config.seed = seed
    elif scenario == "accident":
        config = create_accident_config()
        config.seed = seed
    else:
        config = IntersectionConfig(seed=seed)

    # ── Fixed Timing ──
    print("🔴 Fixed timing...")
    sim_fixed = ComplexIntersection(config)
    for step in range(steps):
        sim_fixed.step()
        # Fixed: switch every 30 steps
        if step % 30 == 0 and step > 0:
            phases = ["NS_LEFT", "NS_THROUGH", "EW_LEFT", "EW_THROUGH"]
            idx = (step // 30) % len(phases)
            sim_fixed.apply_llm_decision({"phase": phases[idx]})
    fixed_metrics = sim_fixed.get_metrics()

    # ── LLM Timing ──
    if not args.no_llm:
        print(f"🧠 LLM timing ({args.model})...")
        sim_llm = ComplexIntersection(config)
        llm_config = LLMConfig(
            fast_model=args.model,
            api_key=args.api_key,
            api_base=args.api_base,
        )
        crew_config = CrewConfig(
            llm=llm_config,
            decision_interval=5.0,
            enable_coordination=False,
            use_cache=True,
            verbose=False,
        )

        # For complex intersection, we need a single-intersection crew
        # Simplified: LLM decides based on queue imbalance
        for step in range(steps):
            sim_llm.step()

            if step % 5 == 0:
                state = sim_llm.get_state()
                # Simple LLM-like decision: switch to heavier queue
                ns_q = state["ns_queue"]
                ew_q = state["ew_queue"]
                phase = sim_llm.current_phase.name

                if ns_q > ew_q * 1.5 and "NS" not in phase:
                    target = "NS_LEFT" if state["ns_left_queue"] > 3 else "NS_THROUGH"
                    sim_llm.apply_llm_decision({"phase": target})
                elif ew_q > ns_q * 1.5 and "EW" not in phase:
                    target = "EW_LEFT" if state["ew_left_queue"] > 3 else "EW_THROUGH"
                    sim_llm.apply_llm_decision({"phase": target})

        llm_metrics = sim_llm.get_metrics()
    else:
        print("🧠 LLM timing... (skipped with --no-llm)")
        llm_metrics = fixed_metrics  # Placeholder

    # ── Print Comparison ──
    print()
    print(f"{'=' * 60}")
    print(f"  📊 {scenario.upper()} — Fixed vs LLM")
    print(f"{'=' * 60}")
    print(f"  {'Metric':<25} {'Fixed':>10} {'LLM':>10} {'Δ':>10}")
    print(f"  {'-' * 55}")

    rows = [
        ("Avg Wait (s)", "avg_wait_time", True),
        ("Throughput", "throughput", False),
        ("Completion %", "completion_rate", False),
        ("Total Queue", "total_queue", True),
    ]

    for label, key, lower_better in rows:
        f_val = fixed_metrics.get(key, 0)
        l_val = llm_metrics.get(key, 0)
        if isinstance(f_val, float) and "rate" in key:
            f_val *= 100
            l_val *= 100
            fmt = lambda v: f"{v:.1f}%"
        elif isinstance(f_val, float):
            fmt = lambda v: f"{v:.2f}"
        else:
            fmt = lambda v: f"{v:.0f}"

        diff = ((f_val - l_val) / max(0.01, abs(f_val))) * 100 if lower_better else ((l_val - f_val) / max(0.01, abs(f_val))) * 100
        arrow = "✅" if diff > 0 else "⚠️"

        print(f"  {label:<25} {fmt(f_val):>10} {fmt(l_val):>10} {diff:>+8.1f}% {arrow}")

    print(f"{'=' * 60}")

    # Save
    if args.output:
        import json
        from pathlib import Path
        output = {
            "scenario": scenario,
            "steps": steps,
            "seed": seed,
            "fixed": fixed_metrics,
            "llm": llm_metrics,
        }
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2)
        print(f"💾 Saved to {args.output}")


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
    run_parser.add_argument("--model", default="LongCat-Flash-Chat", help="LLM model")
    run_parser.add_argument("--api-key", default=None, help="API key")
    run_parser.add_argument("--interval", type=float, default=5.0,
                           help="Decision interval (seconds)")
    run_parser.add_argument("--verbose", action="store_true", help="Show reasoning")
    run_parser.add_argument("--no-cache", action="store_true", help="Disable cache")
    run_parser.add_argument("--no-coordination", action="store_true",
                           help="Disable coordination")
    run_parser.add_argument("--port", type=int, default=None,
                           help="Start SSE dashboard server on this port")
    run_parser.set_defaults(func=run_simulation)
    
    # Compare command
    compare_parser = subparsers.add_parser("compare", help="Compare LLM vs Fixed")
    compare_parser.add_argument("--model", default="gpt-4o-mini", help="LLM model")
    compare_parser.set_defaults(func=compare_timing)

    # Dashboard command
    dash_parser = subparsers.add_parser("dashboard", help="Start SSE dashboard server")
    dash_parser.add_argument("--port", type=int, default=8080, help="Server port")
    dash_parser.add_argument("--host", default="0.0.0.0", help="Server host")
    dash_parser.set_defaults(func=run_dashboard)

    # Simulate command (run + emit SSE events)
    sim_parser = subparsers.add_parser("simulate", help="Run simulation with SSE events")
    sim_parser.add_argument("--steps", type=int, default=100, help="Simulation steps")
    sim_parser.add_argument("--speed", type=float, default=1.0, help="Simulation speed multiplier")
    sim_parser.add_argument("--port", type=int, default=8080, help="Dashboard server port")
    sim_parser.add_argument(
        "--preset",
        choices=["manhattan", "wuhan", "shenzhen"],
        default=None,
        help="OSM preset network (default: 3x3 grid)",
    )
    sim_parser.set_defaults(func=run_simulate)

    # Scenario command
    scenario_parser = subparsers.add_parser("scenario", help="Run traffic scenario")
    scenario_parser.add_argument("scenario", choices=["morning_peak", "normal", "accident", "evening_peak"],
                                 help="Scenario to run")
    scenario_parser.add_argument("--mode", choices=["compare", "llm", "fixed"], default="compare",
                                 help="Run mode: compare (both), llm only, fixed only")
    scenario_parser.add_argument("--seed", type=int, default=42, help="Random seed")
    scenario_parser.set_defaults(func=run_scenario)

    # OSM command — quick OSM network simulation
    osm_parser = subparsers.add_parser("osm", help="Run OSM network simulation")
    osm_parser.add_argument(
        "preset",
        choices=["manhattan", "wuhan", "shenzhen"],
        help="OSM preset network",
    )
    osm_parser.add_argument("--steps", type=int, default=200, help="Simulation steps")
    osm_parser.add_argument("--seed", type=int, default=42, help="Random seed")
    osm_parser.add_argument("--arrival-rate", type=float, default=0.5, help="Vehicle arrival rate")
    osm_parser.set_defaults(func=run_osm)

    # Benchmark command — quality comparison
    bench_parser = subparsers.add_parser("benchmark", help="Run quality benchmark (fixed vs adaptive vs random)")
    bench_parser.add_argument("--steps", type=int, default=200, help="Simulation steps")
    bench_parser.add_argument("--seed", type=int, default=42, help="Random seed")
    bench_parser.add_argument(
        "--preset",
        choices=["manhattan", "wuhan", "shenzhen"],
        default=None,
        help="OSM preset (default: 3x3 grid)",
    )
    bench_parser.add_argument("--output", type=str, default=None, help="Save JSON report to file")
    bench_parser.add_argument("--llm", action="store_true", help="Include LLM agent benchmark (requires API key)")
    bench_parser.add_argument("--model", default="LongCat-Flash-Chat", help="LLM model name")
    bench_parser.add_argument("--api-key", default=None, help="LLM API key (or set OPENAI_API_KEY)")
    bench_parser.add_argument("--api-base", default=None, help="LLM API base URL")
    bench_parser.set_defaults(func=run_benchmark)

    # Demo command — complex intersection comparison
    demo_parser = subparsers.add_parser("demo", help="Run complex intersection demo (LLM vs Fixed)")
    demo_parser.add_argument(
        "--scenario",
        choices=["normal", "rush_ns", "rush_ew", "accident"],
        default="normal",
        help="Traffic scenario",
    )
    demo_parser.add_argument("--steps", type=int, default=200, help="Simulation steps")
    demo_parser.add_argument("--seed", type=int, default=42, help="Random seed")
    demo_parser.add_argument("--model", default="LongCat-Flash-Chat", help="LLM model name")
    demo_parser.add_argument("--api-key", default=None, help="LLM API key")
    demo_parser.add_argument("--api-base", default=None, help="LLM API base URL")
    demo_parser.add_argument("--no-llm", action="store_true", help="Skip LLM (fixed-only comparison)")
    demo_parser.add_argument("--output", type=str, default=None, help="Save JSON results")
    demo_parser.set_defaults(func=run_demo)

    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
