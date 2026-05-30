"""
Tests for Traffic Heatmap visualization.
"""

import pytest

from traffic_agent.visualization.heatmap import (
    HeatmapCell,
    HeatmapData,
    HeatmapGenerator,
    HeatmapMetric,
)


class TestHeatmapGenerator:
    """Test heatmap generation."""

    @pytest.fixture
    def generator(self):
        return HeatmapGenerator()

    @pytest.fixture
    def sample_states(self):
        return {
            "ix_0_0": {"queue_north": 5, "queue_south": 3, "queue_east": 2, "queue_west": 1},
            "ix_0_1": {"queue_north": 10, "queue_south": 8, "queue_east": 4, "queue_west": 3},
            "ix_1_0": {"queue_north": 0, "queue_south": 0, "queue_east": 0, "queue_west": 0},
            "ix_1_1": {"queue_north": 15, "queue_south": 12, "queue_east": 8, "queue_west": 6},
        }

    @pytest.fixture
    def grid_layout(self):
        return {
            "ix_0_0": (0, 0),
            "ix_0_1": (0, 1),
            "ix_1_0": (1, 0),
            "ix_1_1": (1, 1),
        }

    def test_generate_basic(self, generator, sample_states, grid_layout):
        heatmap = generator.generate(sample_states, grid_layout)
        assert heatmap.rows == 2
        assert heatmap.cols == 2
        assert len(heatmap.cells) == 2
        assert len(heatmap.cells[0]) == 2

    def test_generate_queue_length(self, generator, sample_states, grid_layout):
        heatmap = generator.generate(
            sample_states, grid_layout, metric=HeatmapMetric.QUEUE_LENGTH
        )
        # ix_0_0: 5+3+2+1 = 11
        assert heatmap.cells[0][0].value == 11
        # ix_1_1: 15+12+8+6 = 41
        assert heatmap.cells[1][1].value == 41

    def test_generate_normalized(self, generator, sample_states, grid_layout):
        heatmap = generator.generate(sample_states, grid_layout)
        # Min value should be normalized to 0
        min_cell = min(
            (cell for row in heatmap.cells for cell in row),
            key=lambda c: c.value
        )
        assert min_cell.normalized == 0.0

        # Max value should be normalized to 1
        max_cell = max(
            (cell for row in heatmap.cells for cell in row),
            key=lambda c: c.value
        )
        assert max_cell.normalized == 1.0

    def test_generate_empty_states(self, generator, grid_layout):
        heatmap = generator.generate({}, grid_layout)
        assert heatmap.rows == 2
        assert heatmap.cols == 2
        # All values are 0
        for row in heatmap.cells:
            for cell in row:
                assert cell.value == 0.0

    def test_generate_empty_layout(self, generator, sample_states):
        heatmap = generator.generate(sample_states, {})
        assert heatmap.rows == 0
        assert heatmap.cols == 0

    def test_generate_congestion_metric(self, generator, grid_layout):
        states = {
            "ix_0_0": {"queue_north": 10, "queue_south": 0, "queue_east": 0, "queue_west": 0, "max_capacity": 40},
        }
        heatmap = generator.generate(
            states, {"ix_0_0": (0, 0)}, metric=HeatmapMetric.CONGESTION
        )
        assert heatmap.cells[0][0].value == 0.25  # 10/40

    def test_generate_wait_time_metric(self, generator, grid_layout):
        states = {
            "ix_0_0": {"avg_wait_time": 25.5},
        }
        heatmap = generator.generate(
            states, {"ix_0_0": (0, 0)}, metric=HeatmapMetric.WAIT_TIME
        )
        assert heatmap.cells[0][0].value == 25.5

    def test_to_dict(self, generator, sample_states, grid_layout):
        heatmap = generator.generate(sample_states, grid_layout)
        d = heatmap.to_dict()
        assert "metric" in d
        assert "grid" in d
        assert "min_value" in d
        assert "max_value" in d
        assert len(d["grid"]) == 2
        assert len(d["grid"][0]) == 2

    def test_timestamp_preserved(self, generator, sample_states, grid_layout):
        heatmap = generator.generate(sample_states, grid_layout, timestamp=123.45)
        assert heatmap.timestamp == 123.45


class TestHeatmapColorMapping:
    """Test color value mapping."""

    def test_value_to_color_zero(self):
        r, g, b = HeatmapGenerator.value_to_color(0.0)
        assert r == 0
        assert g == 200
        assert b == 0

    def test_value_to_color_one(self):
        r, g, b = HeatmapGenerator.value_to_color(1.0)
        assert r == 255
        assert g == 0
        assert b == 0

    def test_value_to_color_mid(self):
        r, g, b = HeatmapGenerator.value_to_color(0.5)
        assert r == 255
        assert g == 255
        assert b == 0

    def test_value_to_color_clamped(self):
        r, g, b = HeatmapGenerator.value_to_color(-0.5)
        assert r == 0
        assert g == 200
        assert b == 0

        r, g, b = HeatmapGenerator.value_to_color(1.5)
        assert r == 255
        assert g == 0
        assert b == 0


class TestHeatmapMetric:
    """Test metric enum."""

    def test_metric_values(self):
        assert HeatmapMetric.QUEUE_LENGTH.value == "queue_length"
        assert HeatmapMetric.WAIT_TIME.value == "wait_time"
        assert HeatmapMetric.VEHICLE_COUNT.value == "vehicle_count"
        assert HeatmapMetric.CONGESTION.value == "congestion"
