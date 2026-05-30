"""
Traffic Statistics — Aggregation and reporting for simulation results.

Provides statistical analysis of traffic simulation data including
queue lengths, wait times, throughput, and signal performance metrics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class TrafficStatistics:
    """Aggregated traffic statistics from a simulation run."""

    # Time range
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0

    # Vehicle counts
    total_generated: int = 0
    total_completed: int = 0
    completion_rate: float = 0.0

    # Queue statistics
    avg_queue_length: float = 0.0
    max_queue_length: int = 0
    queue_95th_percentile: float = 0.0

    # Wait time statistics
    avg_wait_time: float = 0.0
    max_wait_time: float = 0.0
    wait_time_95th_percentile: float = 0.0

    # Throughput
    throughput_per_second: float = 0.0
    throughput_per_minute: float = 0.0

    # Signal statistics
    total_phase_changes: int = 0
    avg_phase_duration: float = 0.0
    total_adjustments: int = 0
    avg_adjustment: float = 0.0

    # Per-direction breakdown
    direction_stats: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "time_range": {
                "start": self.start_time,
                "end": self.end_time,
                "duration": self.duration,
            },
            "vehicles": {
                "generated": self.total_generated,
                "completed": self.total_completed,
                "completion_rate": self.completion_rate,
            },
            "queue": {
                "avg_length": self.avg_queue_length,
                "max_length": self.max_queue_length,
                "p95_length": self.queue_95th_percentile,
            },
            "wait_time": {
                "avg": self.avg_wait_time,
                "max": self.max_wait_time,
                "p95": self.wait_time_95th_percentile,
            },
            "throughput": {
                "per_second": self.throughput_per_second,
                "per_minute": self.throughput_per_minute,
            },
            "signals": {
                "phase_changes": self.total_phase_changes,
                "avg_duration": self.avg_phase_duration,
                "adjustments": self.total_adjustments,
                "avg_adjustment": self.avg_adjustment,
            },
            "by_direction": self.direction_stats,
        }

    def to_json(self, indent: int = 2) -> str:
        """Export as JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, path: str | Path) -> None:
        """Save to JSON file."""
        Path(path).write_text(self.to_json(), encoding="utf-8")

    def format_summary(self) -> str:
        """Format as human-readable summary."""
        lines = [
            "=" * 50,
            "  Traffic Statistics Summary",
            "=" * 50,
            f"  Duration: {self.duration:.1f}s",
            f"  Vehicles: {self.total_generated} generated, {self.total_completed} completed ({self.completion_rate:.1%})",
            "",
            "  Queue:",
            f"    Average: {self.avg_queue_length:.1f} vehicles",
            f"    Maximum: {self.max_queue_length} vehicles",
            f"    95th percentile: {self.queue_95th_percentile:.1f}",
            "",
            "  Wait Time:",
            f"    Average: {self.avg_wait_time:.1f}s",
            f"    Maximum: {self.max_wait_time:.1f}s",
            f"    95th percentile: {self.wait_time_95th_percentile:.1f}s",
            "",
            "  Throughput:",
            f"    {self.throughput_per_second:.2f} vehicles/s",
            f"    {self.throughput_per_minute:.1f} vehicles/min",
            "",
            "  Signals:",
            f"    Phase changes: {self.total_phase_changes}",
            f"    Adjustments: {self.total_adjustments} (avg {self.avg_adjustment:+.1f}s)",
            "=" * 50,
        ]
        return "\n".join(lines)


class StatisticsCollector:
    """Collects raw data during simulation and computes statistics."""

    def __init__(self):
        self._queue_samples: list[int] = []
        self._wait_samples: list[float] = []
        self._timestamps: list[float] = []
        self._generated: int = 0
        self._completed: int = 0
        self._phase_changes: int = 0
        self._phase_durations: list[float] = []
        self._adjustments: list[float] = []
        self._direction_data: dict[str, list[float]] = {}

    def record_queue(self, length: int, timestamp: float = 0.0) -> None:
        """Record a queue length sample."""
        self._queue_samples.append(length)
        self._timestamps.append(timestamp)

    def record_wait(self, wait_time: float) -> None:
        """Record a wait time sample."""
        self._wait_samples.append(wait_time)

    def record_vehicle_generated(self) -> None:
        """Record a vehicle generation event."""
        self._generated += 1

    def record_vehicle_completed(self) -> None:
        """Record a vehicle completion event."""
        self._completed += 1

    def record_phase_change(self, duration: float = 0.0) -> None:
        """Record a signal phase change with its duration."""
        self._phase_changes += 1
        if duration > 0:
            self._phase_durations.append(duration)

    def record_adjustment(self, seconds: float) -> None:
        """Record a timing adjustment."""
        self._adjustments.append(seconds)

    def compute(self) -> TrafficStatistics:
        """Compute aggregated statistics from collected samples."""
        stats = TrafficStatistics()

        # Time range
        if self._timestamps:
            stats.start_time = self._timestamps[0]
            stats.end_time = self._timestamps[-1]
            stats.duration = stats.end_time - stats.start_time

        # Vehicle counts
        stats.total_generated = self._generated
        stats.total_completed = self._completed
        if self._generated > 0:
            stats.completion_rate = self._completed / self._generated

        # Queue statistics
        if self._queue_samples:
            stats.avg_queue_length = sum(self._queue_samples) / len(self._queue_samples)
            stats.max_queue_length = max(self._queue_samples)
            stats.queue_95th_percentile = float(np.percentile(self._queue_samples, 95))

        # Wait time statistics
        if self._wait_samples:
            stats.avg_wait_time = sum(self._wait_samples) / len(self._wait_samples)
            stats.max_wait_time = max(self._wait_samples)
            stats.wait_time_95th_percentile = float(np.percentile(self._wait_samples, 95))

        # Throughput
        if stats.duration > 0:
            stats.throughput_per_second = self._completed / stats.duration
            stats.throughput_per_minute = stats.throughput_per_second * 60

        # Signal statistics
        stats.total_phase_changes = self._phase_changes
        if self._phase_durations:
            stats.avg_phase_duration = sum(self._phase_durations) / len(self._phase_durations)
        stats.total_adjustments = len(self._adjustments)
        if self._adjustments:
            stats.avg_adjustment = sum(self._adjustments) / len(self._adjustments)

        return stats
