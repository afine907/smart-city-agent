"""
Prometheus Metrics — Metrics collection for monitoring.

Provides Prometheus-compatible metrics for the traffic control system.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricValue:
    """A single metric value with labels."""

    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class MetricsCollector:
    """Collects and exposes metrics in Prometheus format."""

    def __init__(self, max_histogram_samples: int = 10000):
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._labels: dict[str, dict[str, str]] = {}
        self._max_histogram_samples = max_histogram_samples

    def increment_counter(self, name: str, value: float = 1.0, **labels: str) -> None:
        """Increment a counter metric."""
        key = self._make_key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value
        self._labels[key] = labels

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        """Set a gauge metric value."""
        key = self._make_key(name, labels)
        self._gauges[key] = value
        self._labels[key] = labels

    def observe_histogram(self, name: str, value: float, **labels: str) -> None:
        """Observe a value for a histogram metric."""
        key = self._make_key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        samples = self._histograms[key]
        samples.append(value)
        # Evict oldest samples when limit is reached
        if len(samples) > self._max_histogram_samples:
            self._histograms[key] = samples[-self._max_histogram_samples:]
        self._labels[key] = labels

    def get_counter(self, name: str, **labels: str) -> float:
        """Get counter value."""
        key = self._make_key(name, labels)
        return self._counters.get(key, 0)

    def get_gauge(self, name: str, **labels: str) -> float:
        """Get gauge value."""
        key = self._make_key(name, labels)
        return self._gauges.get(key, 0)

    def get_histogram(self, name: str, **labels: str) -> dict[str, float]:
        """Get histogram statistics."""
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])

        if not values:
            return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0}

        return {
            "count": len(values),
            "sum": sum(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
        }

    def to_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        lines: list[str] = []
        emitted_types: set[str] = set()

        # Group counters by metric name
        counter_groups: dict[str, list[tuple[str, float]]] = {}
        for key, value in self._counters.items():
            name = key.split("{")[0]
            counter_groups.setdefault(name, []).append((key, value))

        for name, entries in counter_groups.items():
            if name not in emitted_types:
                lines.append(f"# TYPE {name} counter")
                emitted_types.add(name)
            for key, value in entries:
                labels = self._labels.get(key, {})
                label_str = self._format_labels(labels)
                lines.append(f"{name}{label_str} {value}")

        # Group gauges by metric name
        gauge_groups: dict[str, list[tuple[str, float]]] = {}
        for key, value in self._gauges.items():
            name = key.split("{")[0]
            gauge_groups.setdefault(name, []).append((key, value))

        for name, entries in gauge_groups.items():
            if name not in emitted_types:
                lines.append(f"# TYPE {name} gauge")
                emitted_types.add(name)
            for key, value in entries:
                labels = self._labels.get(key, {})
                label_str = self._format_labels(labels)
                lines.append(f"{name}{label_str} {value}")

        # Group histograms by metric name
        hist_groups: dict[str, list[tuple[str, list[float]]]] = {}
        for key, values in self._histograms.items():
            name = key.split("{")[0]
            hist_groups.setdefault(name, []).append((key, values))

        for name, entries in hist_groups.items():
            if name not in emitted_types:
                lines.append(f"# TYPE {name} histogram")
                emitted_types.add(name)
            for key, values in entries:
                labels = self._labels.get(key, {})
                label_str = self._format_labels(labels)

                if values:
                    # Cumulative buckets
                    for bucket in [0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, float("inf")]:
                        if bucket == float("inf"):
                            count = len(values)
                            bucket_labels = {**labels, "le": "+Inf"}
                        else:
                            count = sum(1 for v in values if v <= bucket)
                            bucket_labels = {**labels, "le": str(bucket)}
                        bucket_str = self._format_labels(bucket_labels)
                        lines.append(f"{name}_bucket{bucket_str} {count}")

                    # Sum and count
                    lines.append(f"{name}_sum{label_str} {sum(values)}")
                    lines.append(f"{name}_count{label_str} {len(values)}")

        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        """Reset all metrics."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._labels.clear()

    @staticmethod
    def _escape_label_value(value: str) -> str:
        """Escape special characters in Prometheus label values."""
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    def _make_key(self, name: str, labels: dict[str, str]) -> str:
        """Create a unique key for a metric with labels."""
        if not labels:
            return name
        label_str = ",".join(
            f'{k}="{self._escape_label_value(v)}"' for k, v in sorted(labels.items())
        )
        return f"{name}{{{label_str}}}"

    def _format_labels(self, labels: dict[str, str]) -> str:
        """Format labels for Prometheus output."""
        if not labels:
            return ""
        label_str = ",".join(
            f'{k}="{self._escape_label_value(v)}"' for k, v in sorted(labels.items())
        )
        return "{" + label_str + "}"


# Global metrics collector
_metrics: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create the global metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


def record_simulation_start() -> None:
    """Record a simulation start event."""
    collector = get_metrics_collector()
    collector.increment_counter("simulation_starts_total")


def record_simulation_end(duration: float) -> None:
    """Record a simulation end event."""
    collector = get_metrics_collector()
    collector.increment_counter("simulation_ends_total")
    collector.observe_histogram("simulation_duration_seconds", duration)


def record_timing_adjustment(layer: str, adjustment: float) -> None:
    """Record a timing adjustment."""
    collector = get_metrics_collector()
    collector.increment_counter("timing_adjustments_total", layer=layer)
    collector.observe_histogram("timing_adjustment_seconds", abs(adjustment))
