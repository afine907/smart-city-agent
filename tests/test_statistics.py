"""
Tests for Traffic Statistics module.
"""

import json
import pytest

from traffic_agent.optimization.statistics import (
    StatisticsCollector,
    TrafficStatistics,
)


class TestTrafficStatistics:
    """Test TrafficStatistics data class."""

    def test_default_values(self):
        stats = TrafficStatistics()
        assert stats.total_generated == 0
        assert stats.total_completed == 0
        assert stats.avg_wait_time == 0.0

    def test_to_dict(self):
        stats = TrafficStatistics(
            total_generated=100,
            total_completed=95,
            completion_rate=0.95,
            avg_wait_time=5.5,
        )
        d = stats.to_dict()
        assert d["vehicles"]["generated"] == 100
        assert d["vehicles"]["completed"] == 95
        assert d["wait_time"]["avg"] == 5.5

    def test_to_json(self):
        stats = TrafficStatistics(total_generated=50)
        j = stats.to_json()
        data = json.loads(j)
        assert data["vehicles"]["generated"] == 50

    def test_save(self, tmp_path):
        stats = TrafficStatistics(total_generated=50)
        path = tmp_path / "stats.json"
        stats.save(path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["vehicles"]["generated"] == 50

    def test_format_summary(self):
        stats = TrafficStatistics(
            duration=100.0,
            total_generated=50,
            total_completed=45,
            completion_rate=0.9,
            avg_queue_length=3.5,
            max_queue_length=10,
            avg_wait_time=5.0,
            throughput_per_second=0.45,
        )
        summary = stats.format_summary()
        assert "Traffic Statistics Summary" in summary
        assert "100.0s" in summary
        assert "50 generated" in summary


class TestStatisticsCollector:
    """Test StatisticsCollector."""

    def test_empty_collector(self):
        collector = StatisticsCollector()
        stats = collector.compute()
        assert stats.total_generated == 0
        assert stats.total_completed == 0

    def test_record_vehicles(self):
        collector = StatisticsCollector()
        collector.record_vehicle_generated()
        collector.record_vehicle_generated()
        collector.record_vehicle_completed()

        stats = collector.compute()
        assert stats.total_generated == 2
        assert stats.total_completed == 1
        assert stats.completion_rate == 0.5

    def test_record_queue(self):
        collector = StatisticsCollector()
        for i in range(10):
            collector.record_queue(i, timestamp=float(i))

        stats = collector.compute()
        assert stats.avg_queue_length == 4.5
        assert stats.max_queue_length == 9
        assert stats.start_time == 0.0
        assert stats.end_time == 9.0

    def test_record_wait(self):
        collector = StatisticsCollector()
        for i in range(10):
            collector.record_wait(float(i))

        stats = collector.compute()
        assert stats.avg_wait_time == 4.5
        assert stats.max_wait_time == 9.0

    def test_record_adjustments(self):
        collector = StatisticsCollector()
        collector.record_adjustment(5.0)
        collector.record_adjustment(-3.0)

        stats = collector.compute()
        assert stats.total_adjustments == 2
        assert stats.avg_adjustment == 1.0

    def test_record_phase_changes(self):
        collector = StatisticsCollector()
        collector.record_phase_change()
        collector.record_phase_change()

        stats = collector.compute()
        assert stats.total_phase_changes == 2

    def test_throughput_calculation(self):
        collector = StatisticsCollector()
        collector.record_queue(0, timestamp=0.0)
        collector.record_queue(0, timestamp=10.0)
        for _ in range(20):
            collector.record_vehicle_completed()

        stats = collector.compute()
        assert stats.duration == 10.0
        assert stats.throughput_per_second == 2.0
        assert stats.throughput_per_minute == 120.0
