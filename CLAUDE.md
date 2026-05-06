# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LLM Traffic Controller — a multi-agent traffic signal control system using CrewAI agents with LLM-powered decision making. Supports both a 3×3 grid simulation and real OpenStreetMap road networks (Manhattan, Wuhan, Shenzhen presets). The system layers rule-based fallbacks, decision caching, and LLM API calls to minimize cost while maintaining decision quality.

## Common Commands

```bash
# Install (editable mode)
pip install -e ".[llm,dev]"
# or
uv sync

# Run simulation (no LLM required)
python -m traffic_agent.cli run --steps 50
python -m traffic_agent.cli run --scenario grid_3x3 --steps 200 --verbose

# Start SSE dashboard (serves at http://localhost:8080)
python -m traffic_agent.cli simulate --steps 200 --port 8080
python -m traffic_agent.cli simulate --preset manhattan --steps 200

# Compare LLM vs fixed timing
python -m traffic_agent.cli compare --model gpt-4o-mini

# Run preset scenarios
python -m traffic_agent.cli scenario morning_peak --mode compare
python -m traffic_agent.cli scenario accident --mode llm

# Run quality benchmark (no LLM)
python -m traffic_agent.cli benchmark --preset shenzhen --steps 200

# OSM network simulation
python -m traffic_agent.cli osm wuhan --steps 200

# Complex intersection demo
python -m traffic_agent.cli demo --scenario rush_ns --steps 200

# Tests
python -m pytest tests/ -v
python -m pytest tests/test_grid.py -v     # single module
python -m pytest tests/test_core.py -v     # specific test file
```

## Architecture

### Package Layout

```
src/traffic_agent/
├── simulation/         # Core simulation engines
│   ├── engine.py       #   Base data structures (Vehicle, Intersection, SimulationEngine)
│   ├── grid.py         #   3×3 grid simulation (GridSimulation)
│   ├── osm.py          #   OpenStreetMap network loader (OSMNetwork, presets)
│   ├── osm_sim.py      #   OSM-based simulation (OSMSimulation)
│   ├── router.py       #   Dijkstra shortest-path routing (RoutePlanner)
│   └── complex_intersection.py  # 4-way intersection with 8-phase NEMA signals
├── agents/             # CrewAI agent definitions
├── crew/               # CrewAI orchestration + coordination (TrafficControlCrew)
├── llm/                # LLM client (client.py) + JSON response parser (parser.py)
├── optimization/       # 3-tier decision pipeline: rule_engine → cache → LLM
├── scenarios/          # Preset traffic scenarios (morning_peak, accident, etc.)
├── comparison/         # Benchmark framework for fixed vs LLM vs adaptive
├── visualization/      # SSE events (events.py), runner, and 6 HTML dashboards
├── api/                # FastAPI SSE server (sse_server.py)
├── tools/              # Agent tools (IntersectionState, observation, communication)
└── cli.py              # CLI entry point — all commands
```

### Key Design Patterns

**Dual Simulation Engines**: `SimulationEngine` (engine.py) is the base with a simple per-intersection vehicle model. `GridSimulation` (grid.py) extends it with road segments and inter-intersection vehicle routing. `OSMSimulation` (osm_sim.py) works on real OSM topologies with Dijkstra routing. `ComplexIntersection` (complex_intersection.py) models a single intersection with 8-phase NEMA signals, left/through/right lanes.

**3-Tier Decision Pipeline** (optimization/): Rule engine (free, <1ms) → decision cache (free, ~40% hit rate) → LLM API call (paid). The layered orchestrator in `layered.py` routes decisions through these tiers automatically.

**SSE Visualization Pipeline**: `SimulationRunner` (visualization/runner.py) drives the simulation and emits typed events via `EventCollector`. The FastAPI server (api/sse_server.py) streams these to the browser via `/api/events/stream`. Six dashboard variants exist in `visualization/*.html` (Tesla-style is the default at `/`).

**Network Topology**: Grid simulations use `ix_{row}_{col}` IDs. OSM simulations use real intersection IDs with lat/lon coordinates. Preset networks are defined as Python dicts in `osm.py` (SMALL_MANHATTAN, WUHAN_OPTICS_VALLEY, SHENZHEN_LIUXIANDONG).

### Signal Phases

- Grid/Engine: Simple 2-phase — `NS_GREEN` / `EW_GREEN` (approaches 0,2 = N,S; 1,3 = E,W)
- Complex Intersection: 8-phase NEMA — `NS_LEFT` → `NS_THROUGH` → `NS_YELLOW` → `ALL_RED_1` → `EW_LEFT` → `EW_THROUGH` → `EW_YELLOW` → `ALL_RED_2`

### LLM Configuration

Defaults to LongCat API (OpenAI-compatible). Set via environment:
- `OPENAI_API_KEY` or `LONGCAT_API_KEY` — API key
- `OPENAI_API_BASE` or `LONGCAT_API_BASE` — custom base URL

The LLM client (`llm/client.py`) loads `.env` from project root if present.

## Testing

Tests are in `tests/` with 164+ tests. No external services required for the core/grid/osm/scenario tests. LLM-dependent tests use mocks. Run with `python -m pytest tests/ -v`. Coverage: `python -m pytest tests/ --cov=traffic_agent`.
