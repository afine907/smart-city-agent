# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-05-29

### Added
- 100-iteration evolution plan (ITERATION_PLAN.md)
- Traffic heatmap visualization module (`visualization/heatmap.py`)
- Green wave coordination visualization (`visualization/green_wave.py`)
- Anomaly detection and alert system (`optimization/anomaly.py`)
- Health check endpoints (`/healthz`, `/readyz`)
- Traffic statistics module with collection and reporting
- Signal timing replay module for analysis
- Short-term traffic prediction with trend detection
- Pluggable signal control strategy interface
- API key authentication with rate limiting
- Prometheus metrics collection (corrected format)
- Event persistence with SQLite backend (WAL mode)
- Structured logging configuration
- Simulation pause/resume/step control
- CLI end-to-end tests (13 tests)
- API integration tests (10 tests)
- Coordination module tests (17 tests, +325% coverage)
- Performance benchmark tests (6 tests)
- Heatmap visualization tests (14 tests)
- Green wave visualization tests (10 tests)
- Anomaly detection tests (13 tests)
- CONTRIBUTING.md with development guidelines
- CHANGELOG.md (this file)
- Quick start example script

### Fixed
- Version mismatch between `__init__.py` and `pyproject.toml`
- k8s health check probe paths (`/readyz`, `/healthz`)
- CLI error handling with friendly messages
- Silent exception swallowing in CrewAI result parsing (now logged)
- Rate limiter race condition (added threading.Lock)
- Cache object mutation in layered pipeline (shallow copy)
- Prometheus output format (grouped by metric name, +Inf bucket)
- Histogram memory leak (max_samples limit)
- SQLite connection leak on _create_tables failure
- 95th percentile calculation (now uses numpy.percentile)
- avg_phase_duration field (now computed from phase_durations)

### Changed
- Extract `RuleOnlyPipeline` to shared module
- Replace `np.random.seed()` with local `Generator(PCG64())` instances
- Add `asyncio.Lock` to protect simulation state in API
- Replace anonymous class pattern with named class in detector.py
- Add `from __future__ import annotations` to all source files
- Cache type annotations now accept both TimingAdjustment and TrafficDecision
- API version updated to 0.2.0

### Removed
- Stale RL configuration fields from `configs/default.json`
- Unused `trained_agent.json` (250KB artifact)

## [0.2.0] - 2025-01-01

### Added
- CrewAI multi-agent architecture with 3-tier pipeline
- Per-intersection Agent with 6 CrewAI tools
- Coordinator Agent with conflict detection
- Green wave advisor and priority resolver
- Real-time SSE dashboard with React frontend
- Grid simulation (3x3 intersections)
- OSM network integration with 3 preset cities
- Dijkstra route planner
- FastAPI SSE server with 10+ endpoints
- Benchmark framework comparing fixed/rule/pipeline
- 267 tests across 14 test files
- Docker and Kubernetes deployment support

## [0.1.0] - 2024-12-01

### Added
- Initial release
- Single intersection simulation
- Signal controller with ±10s adjustment
- Rule engine with 6 rules
- Decision cache (LRU + TTL)
- LLM client with OpenAI-compatible API
- CLI with run, benchmark, scenarios commands
- Basic test suite

[Unreleased]: https://github.com/afine907/smart-city-agent/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/afine907/smart-city-agent/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/afine907/smart-city-agent/releases/tag/v0.1.0
