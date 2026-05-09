# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LLM Traffic Timing Assistant — uses LLM to fine-tune traffic signal timing by ±10 seconds based on real-time detector data (vehicles, pedestrians, bicycles). Keeps fixed baseline timing and adds an AI adjustment layer on top. Supports crossroad and T-junction intersections.

The system uses a 3-tier decision pipeline: rule engine (free) → decision cache (free) → LLM call (paid). About 70%+ of decisions are handled by rules and cache.

## Common Commands

```bash
# Install
pip install -e ".[llm,dev]"
# or
uv sync

# Run simulation (no LLM, rule engine only)
python -m traffic_agent.cli run --steps 200
python -m traffic_agent.cli run --type crossroad --scenario morning_peak --steps 300

# Run simulation with LLM adjustments
python -m traffic_agent.cli run --steps 200 --llm

# Run benchmark: fixed vs rule vs LLM pipeline
python -m traffic_agent.cli benchmark --steps 500

# List available scenarios
python -m traffic_agent.cli scenarios

# Export decision log
python -m traffic_agent.cli run --steps 200 --export log.json

# Run old-style grid/OSM simulations (legacy)
python -m traffic_agent.cli run --scenario grid_3x3 --steps 50
python -m traffic_agent.cli osm manhattan --steps 200

# Tests
python -m pytest tests/ -v
python -m pytest tests/test_signal_controller.py -v
python -m pytest tests/test_timing_rules.py -v
python -m pytest tests/test_sim_loop.py -v
```

## Architecture

### Core Concept: ±10s Timing Adjustment

The LLM does NOT control the signal. It suggests adjustments of ±10 seconds to the baseline timing. Safety constraints: min green 15s, max green 90s, adjustment clamped to [-10, +10].

### Package Layout

```
src/traffic_agent/
├── simulation/              # Core simulation
│   ├── signal_controller.py # Signal controller + baseline timing + ±10s adjustment
│   ├── detector.py          # Detector model + trend analysis
│   ├── scenarios.py         # Traffic scenario definitions (6 presets)
│   ├── sim_loop.py          # Simulation main loop (TimingSimulation)
│   ├── engine.py            # Base simulation data structures (legacy)
│   ├── grid.py              # 3×3 grid simulation (legacy)
│   └── osm*.py              # OpenStreetMap network simulation (legacy)
├── llm/
│   ├── client.py            # LLM client (OpenAI-compatible)
│   ├── parser.py            # TimingAdjustment parsing + validation
│   └── prompts.py           # LLM prompt templates
├── optimization/
│   ├── rule_engine.py       # 6-rule engine for fast decisions
│   ├── layered.py           # 3-tier pipeline: rules → cache → LLM
│   ├── cache.py             # LRU + TTL decision cache
│   └── cost_tracker.py      # LLM cost tracking
├── scenarios/
│   ├── presets.py           # Old-style scenario configs (GridSimulation)
│   └── runner.py            # Scenario runner (bridges to TimingSimulation)
├── comparison/
│   └── benchmark.py         # Benchmark: fixed vs rule vs pipeline
├── visualization/           # SSE events + HTML dashboards
├── api/                     # FastAPI SSE server
└── cli.py                   # CLI entry point
```

### Key Classes

- `SignalController` — manages signal state, applies ±10s adjustments, enforces safety constraints
- `DetectorSimulator` — generates detector readings from simulation vehicles
- `TrendAnalyzer` — tracks traffic flow trends over sliding window
- `TimingRuleEngine` — 6 rules for instant decisions (low traffic, high queue, pedestrians, etc.)
- `TimingDecisionPipeline` — 3-layer orchestrator: rules → cache → LLM
- `TimingSimulation` — ties everything together into a simulation loop
- `TimingBenchmark` — runs fixed/rule/pipeline strategies and compares results
- `TimingAdjustment` — LLM output: `{adjustment, reasoning, confidence, alerts}`

### Signal Phases

Crossroad: `NS_GREEN` → `NS_YELLOW` → `ALL_RED` → `EW_GREEN` → `EW_YELLOW` → `ALL_RED`
T-junction: `NS_GREEN` → `NS_YELLOW` → `ALL_RED` → `EW_GREEN` → `EW_YELLOW`

Green approaches: 0=north, 1=east, 2=south, 3=west

### Traffic Scenarios

Defined in `simulation/scenarios.py` with `TrafficPhase` and `TrafficScenario`:
- `morning_peak` — heavy NS flow, ramp up → peak → ramp down
- `evening_peak` — heavy EW flow
- `normal` — balanced
- `pedestrian_heavy` — high pedestrian volume
- `accident` — emergency vehicles + congestion
- `bicycle_rush` — bicycle rush hour

### LLM Configuration

Supports OpenAI-compatible API. Set via environment:
- `OPENAI_API_KEY` or `LONGCAT_API_KEY` — API key
- `OPENAI_API_BASE` or `LONGCAT_API_BASE` — custom base URL

The LLM client (`llm/client.py`) loads `.env` from project root if present.

## Testing

248 tests in `tests/`. No external services required for core tests. LLM-dependent tests use mocks.

```bash
python -m pytest tests/ -v                        # all tests
python -m pytest tests/test_signal_controller.py  # signal controller
python -m pytest tests/test_timing_rules.py       # rule engine + parser
python -m pytest tests/test_sim_loop.py           # simulation loop
python -m pytest tests/test_comparison.py         # benchmark framework
python -m pytest tests/test_scenarios.py          # scenario presets + runner
python -m pytest tests/test_optimization.py       # cache, cost tracker, pipeline
python -m pytest tests/test_detector.py           # detector + trend analyzer
```

Coverage: `python -m pytest tests/ --cov=traffic_agent`
