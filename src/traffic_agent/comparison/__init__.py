"""Comparison module — fixed vs rule vs LLM timing benchmark framework."""

from traffic_agent.comparison.benchmark import (
    TimingBenchmark,
    BenchmarkReport,
    StrategyResult,
    # Backward compatibility
    ComparisonBenchmark,
    BenchmarkResult,
    ComparisonReport,
)

__all__ = [
    "TimingBenchmark",
    "BenchmarkReport",
    "StrategyResult",
    "ComparisonBenchmark",
    "BenchmarkResult",
    "ComparisonReport",
]
