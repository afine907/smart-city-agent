"""
LLM Traffic Controller — CLI Interface

Usage:
    python -m traffic_agent.cli run --type crossroad --steps 500
    python -m traffic_agent.cli run --type crossroad --steps 500 --llm
    python -m traffic_agent.cli benchmark --type crossroad --steps 500
    python -m traffic_agent.cli scenarios
"""

from __future__ import annotations


import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def cmd_run(args) -> None:
    """Run a timing adjustment simulation."""
    if args.multi_agent:
        return cmd_run_multi_agent(args)

    from traffic_agent.simulation.sim_loop import TimingSimulation

    # Optionally create pipeline for LLM/rule decisions
    pipeline = None  # type: ignore[assignment]
    if args.llm:
        from traffic_agent.llm.client import LLMConfig
        from traffic_agent.optimization.layered import TimingDecisionPipeline

        llm_config = LLMConfig(
            fast_model=args.model,
            api_key=args.api_key,
        )
        pipeline = TimingDecisionPipeline(llm_config=llm_config)
        print(f"  LLM pipeline enabled (model: {args.model})")
    elif args.rule:
        from traffic_agent.optimization.rule_only import RuleOnlyPipeline

        pipeline = RuleOnlyPipeline()
        print("  Rule engine enabled")
    else:
        print("  Fixed timing (no adjustments)")

    print(f"  Type: {args.type}")
    print(f"  Scenario: {args.scenario}")
    print(f"  Steps: {args.steps}")
    print(f"  Seed: {args.seed}")
    print()

    sim = TimingSimulation(
        intersection_type=args.type,
        scenario_name=args.scenario,
        pipeline=pipeline,
        seed=args.seed,
        ns_green=args.ns_green,
        ew_green=args.ew_green,
    )

    report = sim.run(steps=args.steps, verbose=args.verbose)

    # Print report
    print()
    print("=" * 60)
    print(f"  Simulation Report")
    print("=" * 60)
    print(f"  Total steps: {report.total_steps}")
    print(f"  Vehicles generated: {report.total_vehicles_generated}")
    print(f"  Vehicles completed: {report.total_vehicles_completed}")
    print(f"  Avg wait time: {report.avg_wait_time:.2f}s")
    print(f"  Throughput: {report.throughput:.3f} vehicles/s")
    print(f"  Adjustments made: {report.adjustments_made}")
    print(f"  LLM adjustments: {report.llm_adjustments}")
    print(f"  Rule adjustments: {report.rule_adjustments}")
    print()

    if report.pipeline_stats:
        print("  Pipeline stats:")
        for k, v in report.pipeline_stats.items():
            if isinstance(v, dict):
                print(f"    {k}:")
                for kk, vv in v.items():
                    print(f"      {kk}: {vv}")
            elif isinstance(v, float):
                print(f"    {k}: {v:.3f}")
            else:
                print(f"    {k}: {v}")

    # Export log if requested
    if args.export:
        sim.export_log(args.export)
        print(f"\n  Log exported to {args.export}")

    print("=" * 60)


def cmd_run_multi_agent(args) -> None:
    """Run multi-agent simulation with CrewAI."""
    from traffic_agent.simulation.grid import GridSimulation
    from traffic_agent.crew.traffic_crew import TrafficControlCrew, CrewConfig
    from traffic_agent.llm.client import LLMConfig

    print("  Multi-Agent mode (CrewAI)")
    print(f"  Scenario: {args.scenario}")
    print(f"  Steps: {args.steps}")
    print()

    # Create grid simulation (3x3 intersections)
    sim = GridSimulation()

    # Create crew config
    llm_config = LLMConfig(
        fast_model=args.model,
        api_key=args.api_key,
    )
    crew_config = CrewConfig(
        llm=llm_config,
        use_rules=getattr(args, 'rule', True),
        use_cache=True,
        enable_timing_adjustment=True,
    )

    # Create multi-agent crew
    intersection_ids = list(sim.intersections.keys())
    graph = sim.get_graph()

    crew = TrafficControlCrew(
        intersection_ids=intersection_ids,
        graph=graph,
        config=crew_config,
    )

    # Connect simulation engine to CrewAI tools
    crew.set_engine(sim)

    print(f"  Intersections: {len(intersection_ids)}")
    print(f"  Agents: {len(intersection_ids)} intersection + 1 coordinator")
    print(f"  Pipeline: rules={'ON' if crew_config.use_rules else 'OFF'}"
          f" | cache={'ON' if crew_config.use_cache else 'OFF'}"
          f" | LLM=CrewAI")
    print()

    # Run simulation
    for step in range(args.steps):
        # Advance simulation
        sim.step()

        # Get decisions from multi-agent crew
        decisions = crew.step(sim)

        if args.verbose and step % 50 == 0:
            layers: dict[str, int] = {}
            for d in decisions:
                layer = d.get("layer", "unknown")
                layers[layer] = layers.get(layer, 0) + 1
            layer_str = ", ".join(f"{k}={v}" for k, v in layers.items())
            print(f"  Step {step}: {len(decisions)} decisions ({layer_str})")

    # Print report
    metrics = crew.get_metrics()
    print()
    print("=" * 60)
    print("  Multi-Agent Simulation Report")
    print("=" * 60)
    print(f"  Total steps: {args.steps}")
    print(f"  Intersections: {len(intersection_ids)}")
    print(f"  Total decisions: {metrics['total_decisions']}")
    print(f"  Rule hits: {metrics['total_rule_hits']} ({metrics['rule_hit_rate']:.2%})")
    print(f"  Cache hits: {metrics['total_cache_hits']} ({metrics['cache_hit_rate']:.2%})")
    print(f"  LLM calls: {metrics['total_llm_calls']}")
    print()

    # Simulation metrics
    sim_metrics = sim.get_metrics()
    print(f"  Vehicles generated: {sim_metrics['vehicles_generated']}")
    print(f"  Vehicles completed: {sim_metrics['vehicles_completed']}")
    print(f"  Avg wait time: {sim_metrics['avg_wait_time']:.1f}s")
    print(f"  Throughput: {sim_metrics['throughput']:.2f} veh/s")
    print()

    if args.export:
        import json
        export_data = {**metrics, **sim_metrics}
        with open(args.export, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        print(f"  Metrics exported to {args.export}")

    print("=" * 60)


def cmd_benchmark(args) -> None:
    """Run benchmark comparing strategies."""
    from traffic_agent.comparison.benchmark import TimingBenchmark

    bench = TimingBenchmark(
        steps=args.steps,
        scenario=args.scenario,
        intersection_type=args.type,
        seed=args.seed,
    )

    # Determine strategies
    strategies = ["fixed", "rule"]
    if args.llm:
        strategies.append("pipeline")

    print(f"  Benchmark: {args.type} / {args.scenario}")
    print(f"  Steps: {args.steps}, Seed: {args.seed}")
    print(f"  Strategies: {', '.join(strategies)}")

    report = bench.run(strategies=strategies)
    print(report.format_table())

    # Save if requested
    if args.output:
        bench.save(report, args.output)
    else:
        bench.save(report, f"docs/benchmark-{args.type}-{args.scenario}.json")


def cmd_scenarios(args) -> None:
    """List available scenarios."""
    from traffic_agent.simulation.scenarios import list_scenarios

    scenarios = list_scenarios()
    print("Available scenarios:")
    print()
    for s in scenarios:
        print(f"  {s['name']:<20} {s['name_cn']:<10} {s['description']}")


def cmd_serve(args) -> None:
    """Start the API server for the dashboard."""
    import uvicorn

    print(f"  Starting API server on {args.host}:{args.port}")
    print(f"  Dashboard: http://{args.host}:{args.port}/")
    print(f"  API docs:  http://{args.host}:{args.port}/docs")
    print()

    uvicorn.run(
        "traffic_agent.api.sse_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


def main():
    parser = argparse.ArgumentParser(
        description="LLM Traffic Signal Timing Adjustment Controller"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run simulation")
    run_parser.add_argument("--type", choices=["crossroad", "tjunction"],
                           default="crossroad", help="Intersection type")
    run_parser.add_argument("--scenario", default="normal",
                           help="Traffic scenario (morning_peak, evening_peak, normal, accident, pedestrian_heavy, bicycle_rush)")
    run_parser.add_argument("--steps", type=int, default=500, help="Simulation steps")
    run_parser.add_argument("--seed", type=int, default=42, help="Random seed")
    run_parser.add_argument("--llm", action="store_true", help="Enable LLM pipeline")
    run_parser.add_argument("--rule", action="store_true", help="Enable rule engine only")
    run_parser.add_argument("--multi-agent", action="store_true", help="Enable multi-agent mode (CrewAI)")
    run_parser.add_argument("--model", default="LongCat-Flash-Chat", help="LLM model")
    run_parser.add_argument("--api-key", default=None, help="LLM API key")
    run_parser.add_argument("--ns-green", type=float, default=None, help="NS green duration override")
    run_parser.add_argument("--ew-green", type=float, default=None, help="EW green duration override")
    run_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    run_parser.add_argument("--export", type=str, default=None, help="Export log to JSON file")
    run_parser.set_defaults(func=cmd_run)

    # Benchmark command
    bench_parser = subparsers.add_parser("benchmark", help="Run benchmark comparison")
    bench_parser.add_argument("--type", choices=["crossroad", "tjunction"],
                             default="crossroad", help="Intersection type")
    bench_parser.add_argument("--scenario", default="morning_peak",
                             help="Traffic scenario")
    bench_parser.add_argument("--steps", type=int, default=500, help="Simulation steps")
    bench_parser.add_argument("--seed", type=int, default=42, help="Random seed")
    bench_parser.add_argument("--llm", action="store_true", help="Include LLM pipeline")
    bench_parser.add_argument("--model", default="LongCat-Flash-Chat", help="LLM model")
    bench_parser.add_argument("--api-key", default=None, help="LLM API key")
    bench_parser.add_argument("--output", type=str, default=None, help="Save JSON report")
    bench_parser.set_defaults(func=cmd_benchmark)

    # Scenarios command
    scenarios_parser = subparsers.add_parser("scenarios", help="List available scenarios")
    scenarios_parser.set_defaults(func=cmd_scenarios)

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start the API server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    serve_parser.add_argument("--port", type=int, default=8080, help="Bind port")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    serve_parser.set_defaults(func=cmd_serve)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n  Interrupted by user")
        sys.exit(130)
    except ImportError as e:
        print(f"\n  ❌ Missing dependency: {e}")
        print("  Try: pip install -e '.[llm,dev]'")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"\n  ❌ File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error")
        print(f"\n  ❌ Error: {e}")
        if args.verbose if hasattr(args, 'verbose') else False:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
