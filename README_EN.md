# Smart City Agent

> **Making traffic lights smarter with CrewAI Multi-Agent + LLM**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-248%20passed-brightgreen.svg)](tests/)

---

We're introducing LLM to make traffic lights smarter. Each intersection has an Agent that observes and decides, multiple Agents coordinate through a collaboration mechanism, making urban traffic more humanized.

---

## Multi-Agent Architecture

Built on [CrewAI](https://github.com/crewAIInc/crewAI), each intersection is controlled by an independent Agent, with multiple Agents working together:

```
┌─────────────────────────────────────────────────────────────────┐
│                    CrewAI Multi-Agent System                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    │
│   │ Agent: North  │    │ Agent: East   │    │ Agent: South  │    │
│   │ Observe       │    │ Observe       │    │ Observe       │    │
│   │ LLM Reasoning │    │ LLM Reasoning │    │ LLM Reasoning │    │
│   └───────┬──────┘    └───────┬──────┘    └───────┬──────┘    │
│           │                   │                   │            │
│           │    ┌──────────────┴──────────────┐    │            │
│           │    │                             │    │            │
│           ▼    ▼                             ▼    ▼            │
│   ┌───────────────────────────────────────────────────────┐   │
│   │              ConflictDetector                         │   │
│   │  Detect phase conflicts between neighboring intersections│
│   └───────────────────────────┬───────────────────────────┘   │
│                               │                               │
│                               ▼                               │
│   ┌───────────────────────────────────────────────────────┐   │
│   │              Coordinator Agent                         │   │
│   │  Collect decisions → LLM coordination → Final plan    │   │
│   └───────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Coordination Flow:**

1. Each Intersection Agent observes traffic and independently decides signal timing
2. ConflictDetector detects phase conflicts between neighboring intersections
3. Coordinator Agent resolves conflicts via LLM reasoning (emergency priority, queue priority)
4. Execute the coordinated final decisions

---

## Quick Start

```bash
# Clone + Install
git clone https://github.com/afine907/smart-city-agent.git
cd smart-city-agent
pip install -e .

# Single intersection simulation (rule engine)
python -m traffic_agent.cli run --steps 200

# Multi-agent simulation (CrewAI)
python -m traffic_agent.cli run --steps 200 --multi-agent

# Benchmark comparison
python -m traffic_agent.cli benchmark --steps 300 --scenario morning_peak
```

---

## Benchmark Results

Morning peak scenario (3x3 intersection grid):

| Metric | Fixed | Rule Engine | Improvement |
|--------|-------|-------------|-------------|
| Avg Wait (s) | 24.8 | 22.6 | **-8.8%** |
| Throughput (/s) | 2.44 | 2.39 | -2.2% |

Accident scenario:

| Metric | Fixed | Rule Engine | Improvement |
|--------|-------|-------------|-------------|
| Avg Wait (s) | 22.0 | 23.3 | -5.9% |
| Throughput (/s) | 1.60 | 1.79 | **+11.7%** |

---

## Built-in Scenarios

| Scenario | Description |
|----------|-------------|
| `morning_peak` | Morning rush, heavy NS flow |
| `evening_peak` | Evening rush, heavy EW flow |
| `normal` | Off-peak, balanced flow |
| `pedestrian_heavy` | Pedestrian peak |
| `accident` | Emergency, frequent ambulances |
| `bicycle_rush` | Bicycle rush hour |

```bash
python -m traffic_agent.cli run --scenario morning_peak --steps 300
python -m traffic_agent.cli scenarios
```

---

## Project Structure

```
src/traffic_agent/
├── simulation/
│   ├── signal_controller.py   # Signal controller + baseline timing
│   ├── detector.py            # Detector model + trend analysis
│   ├── scenarios.py           # Traffic scenario definitions
│   └── sim_loop.py            # Simulation main loop
├── crew/
│   ├── traffic_crew.py        # Multi-agent orchestration
│   └── coordination.py        # Conflict detection
├── llm/
│   ├── client.py              # LLM client
│   ├── parser.py              # Decision parsing
│   └── prompts.py             # Prompt templates
├── optimization/
│   ├── rule_engine.py         # Rule engine
│   ├── layered.py             # 3-tier decision pipeline
│   └── cache.py               # Decision cache
├── comparison/
│   └── benchmark.py           # Benchmark framework
└── cli.py                     # CLI entry point
```

---

## Testing

```bash
python -m pytest tests/ -v
```

---

## LLM Configuration

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_API_BASE="https://api.openai.com/v1"
```

---

## License

MIT License - See [LICENSE](LICENSE) for details.
