"""
Tests for Prometheus Metrics module.
"""

import pytest

from traffic_agent.api.metrics import (
    MetricsCollector,
    get_metrics_collector,
    record_simulation_end,
    record_simulation_start,
    record_timing_adjustment,
)


class TestMetricsCollector:
    """Test MetricsCollector."""

    def test_counter(self):
        collector = MetricsCollector()
        collector.increment_counter("test_counter")
        collector.increment_counter("test_counter")

        assert collector.get_counter("test_counter") == 2

    def test_counter_with_labels(self):
        collector = MetricsCollector()
        collector.increment_counter("test_counter", method="GET")
        collector.increment_counter("test_counter", method="POST")

        assert collector.get_counter("test_counter", method="GET") == 1
        assert collector.get_counter("test_counter", method="POST") == 1

    def test_gauge(self):
        collector = MetricsCollector()
        collector.set_gauge("test_gauge", 42.0)

        assert collector.get_gauge("test_gauge") == 42.0

    def test_histogram(self):
        collector = MetricsCollector()
        collector.observe_histogram("test_histogram", 1.0)
        collector.observe_histogram("test_histogram", 2.0)
        collector.observe_histogram("test_histogram", 3.0)

        stats = collector.get_histogram("test_histogram")
        assert stats["count"] == 3
        assert stats["sum"] == 6.0
        assert stats["avg"] == 2.0
        assert stats["min"] == 1.0
        assert stats["max"] == 3.0

    def test_histogram_empty(self):
        collector = MetricsCollector()
        stats = collector.get_histogram("nonexistent")
        assert stats["count"] == 0

    def test_to_prometheus(self):
        collector = MetricsCollector()
        collector.increment_counter("requests_total", endpoint="/api")
        collector.set_gauge("active_connections", 5.0)

        output = collector.to_prometheus()
        assert "requests_total" in output
        assert "active_connections" in output
        assert "# TYPE requests_total counter" in output
        assert "# TYPE active_connections gauge" in output

    def test_prometheus_histogram(self):
        collector = MetricsCollector()
        collector.observe_histogram("request_duration", 0.5)
        collector.observe_histogram("request_duration", 1.5)

        output = collector.to_prometheus()
        assert "request_duration_bucket" in output
        assert "request_duration_sum" in output
        assert "request_duration_count" in output

    def test_reset(self):
        collector = MetricsCollector()
        collector.increment_counter("test")
        collector.set_gauge("test", 1.0)

        collector.reset()
        assert collector.get_counter("test") == 0
        assert collector.get_gauge("test") == 0


class TestGlobalCollector:
    """Test global metrics collector."""

    @pytest.fixture(autouse=True)
    def reset_global_collector(self):
        """Reset global collector before each test."""
        import traffic_agent.api.metrics as metrics_module
        metrics_module._metrics = None
        yield
        metrics_module._metrics = None

    def test_get_collector(self):
        collector = get_metrics_collector()
        assert isinstance(collector, MetricsCollector)

    def test_record_simulation_start(self):
        record_simulation_start()
        collector = get_metrics_collector()
        assert collector.get_counter("simulation_starts_total") > 0

    def test_record_simulation_end(self):
        record_simulation_end(10.0)
        collector = get_metrics_collector()
        assert collector.get_counter("simulation_ends_total") > 0

    def test_record_timing_adjustment(self):
        record_timing_adjustment("rule", 5.0)
        collector = get_metrics_collector()
        assert collector.get_counter("timing_adjustments_total", layer="rule") > 0
