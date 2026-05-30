# Test Coverage Report

## Current Status

**Overall Coverage: 81%** (3778 statements, 715 missing)

## Coverage by Module

| Module | Statements | Missing | Coverage |
|--------|------------|---------|----------|
| optimization/statistics.py | 88 | 0 | 100% |
| optimization/cache.py | 51 | 0 | 100% |
| optimization/cost_tracker.py | 80 | 0 | 100% |
| simulation/signal_controller.py | 109 | 0 | 100% |
| simulation/scenarios.py | 54 | 0 | 100% |
| visualization/events.py | 83 | 0 | 100% |
| logging_config.py | 32 | 0 | 100% |
| simulation/replay.py | 58 | 1 | 98% |
| simulation/grid.py | 256 | 5 | 98% |
| optimization/strategies.py | 75 | 1 | 99% |
| optimization/rule_engine.py | 84 | 2 | 98% |
| crew/coordination.py | 100 | 3 | 97% |
| simulation/router.py | 86 | 3 | 97% |
| visualization/persistence.py | 68 | 2 | 97% |
| simulation/sim_loop.py | 147 | 8 | 95% |
| optimization/rule_only.py | 16 | 1 | 94% |
| tools/traffic_tools.py | 113 | 10 | 91% |
| visualization/runner.py | 49 | 4 | 92% |
| simulation/osm_sim.py | 299 | 34 | 89% |
| simulation/prediction.py | 73 | 10 | 86% |
| llm/parser.py | 126 | 21 | 83% |
| scenarios/runner.py | 31 | 6 | 81% |
| simulation/control.py | 100 | 17 | 83% |
| simulation/detector.py | 140 | 24 | 83% |
| simulation/engine.py | 169 | 35 | 79% |
| crew/traffic_crew.py | 172 | 39 | 77% |
| llm/client.py | 69 | 20 | 71% |
| comparison/benchmark.py | 116 | 9 | 92% |
| optimization/layered.py | 74 | 38 | 49% |
| llm/prompts.py | 10 | 7 | 30% |
| simulation/osm.py | 165 | 84 | 49% |

## Coverage Goals

- **Target**: 85%+ overall coverage
- **Priority**: Focus on low-coverage modules
- **Strategy**: Add tests for uncovered code paths

## Improving Coverage

### High Priority (Coverage < 60%)

1. `llm/prompts.py` (30%) — Add tests for prompt templates
2. `optimization/layered.py` (49%) — Add tests for LLM pipeline
3. `simulation/osm.py` (49%) — Add tests for OSM network

### Medium Priority (Coverage 60-80%)

4. `llm/client.py` (71%) — Add tests for LLM client
5. `crew/traffic_crew.py` (77%) — Add tests for CrewAI orchestration
6. `simulation/engine.py` (79%) — Add tests for simulation engine

### Low Priority (Coverage > 80%)

7. All other modules — Maintain and improve

## Running Coverage

```bash
# Run tests with coverage
python -m pytest tests/ --cov=traffic_agent --cov-report=term-missing

# Generate HTML report
python -m pytest tests/ --cov=traffic_agent --cov-report=html

# View HTML report
open htmlcov/index.html
```

## Coverage Configuration

Coverage settings in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "-v --tb=short --cov=traffic_agent --cov-report=term-missing"
```

## Notes

- Coverage is calculated on `src/traffic_agent/` directory
- Test files are excluded from coverage
- Third-party imports are excluded
- Coverage reports are generated on each test run
