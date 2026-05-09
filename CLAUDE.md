# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LLM Traffic Timing Assistant — uses CrewAI multi-agent framework + LLM to fine-tune traffic signal timing. Two modes:

1. **Single intersection**: ±10s adjustment via 3-tier pipeline (rules → cache → LLM)
2. **Multi-agent (CrewAI)**: 3×3 grid with per-intersection Agent, Coordinator Agent, and 6 CrewAI tools

The system uses a 3-tier decision pipeline: rule engine (free) → decision cache (free) → LLM via CrewAI (paid). About 70%+ of decisions are handled by rules and cache.

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

# Run multi-agent simulation (CrewAI, 3×3 grid)
python -m traffic_agent.cli run --multi-agent --steps 100 --verbose

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
│   ├── grid.py              # 3×3 grid simulation with SignalController
│   └── osm*.py              # OpenStreetMap network simulation (legacy)
├── crew/                    # CrewAI multi-agent orchestration
│   ├── __init__.py          # Package exports
│   ├── traffic_crew.py      # TrafficControlCrew — 3-tier pipeline + CrewAI
│   └── coordination.py      # ConflictDetector, GreenWaveAdvisor, PriorityResolver
├── tools/                   # CrewAI tools
│   └── traffic_tools.py     # 6 @tool functions + IntersectionState + SimulationState
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

**Single-intersection path:**
- `SignalController` — manages signal state, applies ±10s adjustments, enforces safety constraints
- `DetectorSimulator` — generates detector readings from simulation vehicles
- `TrendAnalyzer` — tracks traffic flow trends over sliding window
- `TimingRuleEngine` — 6 rules for instant decisions (low traffic, high queue, pedestrians, etc.)
- `TimingDecisionPipeline` — 3-layer orchestrator: rules → cache → LLM
- `TimingSimulation` — ties everything together into a simulation loop
- `TimingBenchmark` — runs fixed/rule/pipeline strategies and compares results
- `TimingAdjustment` — LLM output: `{adjustment, reasoning, confidence, alerts}`

**Multi-agent (CrewAI) path:**
- `TrafficControlCrew` — CrewAI orchestrator with 3-tier pipeline + per-intersection Agents
- `CrewConfig` — configuration: use_rules, use_cache, enable_coordination, LLM models
- `ConflictDetector` — detects phase mismatches and excessive green between neighbors
- `GreenWaveAdvisor` — suggests phase offsets for green wave along corridors
- `PriorityResolver` — resolves conflicts by emergency → queue → wait → tiebreak
- `IntersectionState` — traffic state per intersection (queues, waits, phase, emergency)
- `SimulationState` — shared container: engine + graph reference for CrewAI tools
- 6 CrewAI `@tool` functions: get_state, get_neighbors, apply_signal, apply_adjustment, check_conflicts, get_trend

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

267 tests in `tests/`. No external services required for core tests. LLM-dependent tests use mocks.

```bash
python -m pytest tests/ -v                        # all tests
python -m pytest tests/test_crew.py               # CrewAI tools + crew + coordination
python -m pytest tests/test_signal_controller.py  # signal controller
python -m pytest tests/test_timing_rules.py       # rule engine + parser
python -m pytest tests/test_sim_loop.py           # simulation loop
python -m pytest tests/test_comparison.py         # benchmark framework
python -m pytest tests/test_scenarios.py          # scenario presets + runner
python -m pytest tests/test_optimization.py       # cache, cost tracker, pipeline
python -m pytest tests/test_detector.py           # detector + trend analyzer
python -m pytest tests/test_coordination.py       # conflict detection + resolution
python -m pytest tests/test_grid.py               # grid simulation
python -m pytest tests/test_visualization.py      # SSE events + dashboard
```

Coverage: `python -m pytest tests/ --cov=traffic_agent`
