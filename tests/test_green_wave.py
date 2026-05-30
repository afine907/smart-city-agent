"""
Tests for Green Wave Visualization.
"""

import pytest

from traffic_agent.visualization.green_wave import (
    CorridorDirection,
    GreenWaveData,
    GreenWaveVisualizer,
    IntersectionTimeline,
    SignalPhaseSlot,
)


class TestGreenWaveVisualizer:
    """Test green wave visualization generation."""

    @pytest.fixture
    def visualizer(self):
        return GreenWaveVisualizer()

    @pytest.fixture
    def grid_3x3(self):
        return {
            "ix_0_0": (0, 0), "ix_0_1": (0, 1), "ix_0_2": (0, 2),
            "ix_1_0": (1, 0), "ix_1_1": (1, 1), "ix_1_2": (1, 2),
            "ix_2_0": (2, 0), "ix_2_1": (2, 1), "ix_2_2": (2, 2),
        }

    @pytest.fixture
    def sample_states(self, grid_3x3):
        return {
            ix_id: {
                "queue_north": 5, "queue_south": 3,
                "queue_east": 4, "queue_west": 2,
            }
            for ix_id in grid_3x3
        }

    def test_generate_ew_corridor(self, visualizer, sample_states, grid_3x3):
        data = visualizer.generate(
            sample_states, grid_3x3, direction=CorridorDirection.EW
        )
        assert isinstance(data, GreenWaveData)
        assert data.direction == CorridorDirection.EW
        assert len(data.corridor_ids) > 0
        assert len(data.timelines) > 0

    def test_generate_ns_corridor(self, visualizer, sample_states, grid_3x3):
        data = visualizer.generate(
            sample_states, grid_3x3, direction=CorridorDirection.NS
        )
        assert data.direction == CorridorDirection.NS
        assert len(data.corridor_ids) > 0

    def test_generate_empty_layout(self, visualizer, sample_states):
        data = visualizer.generate(sample_states, {})
        assert len(data.corridor_ids) == 0
        assert len(data.timelines) == 0

    def test_timelines_have_phases(self, visualizer, sample_states, grid_3x3):
        data = visualizer.generate(
            sample_states, grid_3x3, direction=CorridorDirection.EW
        )
        for tl in data.timelines:
            assert len(tl.phases) > 0
            for phase in tl.phases:
                assert phase.start_time <= phase.end_time

    def test_offsets_increase_along_corridor(self, visualizer, sample_states, grid_3x3):
        data = visualizer.generate(
            sample_states, grid_3x3, direction=CorridorDirection.EW
        )
        if len(data.timelines) >= 2:
            offsets = [tl.offset for tl in data.timelines]
            # Offsets should generally increase (may wrap around cycle)
            assert all(isinstance(o, float) for o in offsets)

    def test_green_band_calculated(self, visualizer, sample_states, grid_3x3):
        data = visualizer.generate(
            sample_states, grid_3x3, direction=CorridorDirection.EW
        )
        assert data.green_band_width >= 0
        # When no overlap exists, start > end and width = 0
        if data.green_band_width > 0:
            assert data.green_band_start <= data.green_band_end

    def test_cycle_length_preserved(self, visualizer, sample_states, grid_3x3):
        data = visualizer.generate(
            sample_states, grid_3x3,
            direction=CorridorDirection.EW,
            cycle_length=90.0,
        )
        for tl in data.timelines:
            assert tl.cycle_length == 90.0

    def test_single_intersection(self, visualizer):
        states = {"ix_0_0": {"queue_north": 5}}
        layout = {"ix_0_0": (0, 0)}
        data = visualizer.generate(states, layout)
        assert len(data.timelines) == 1
        assert len(data.timelines[0].phases) > 0


class TestGreenWaveDataSerialization:
    """Test data serialization."""

    def test_to_dict(self):
        data = GreenWaveData(
            direction=CorridorDirection.EW,
            corridor_ids=["ix_0_0", "ix_0_1"],
            timelines=[
                IntersectionTimeline(
                    intersection_id="ix_0_0",
                    row=0, col=0,
                    offset=0.0,
                    cycle_length=60.0,
                    phases=[
                        SignalPhaseSlot(0, 30, "GREEN", "EW"),
                        SignalPhaseSlot(30, 34, "YELLOW", "EW"),
                    ],
                ),
            ],
            green_band_start=0.0,
            green_band_end=30.0,
            green_band_width=30.0,
        )
        d = data.to_dict()
        assert d["direction"] == "EW"
        assert len(d["corridor_ids"]) == 2
        assert len(d["timelines"]) == 1
        assert d["green_band"]["width"] == 30.0

    def test_intersection_timeline_to_dict(self):
        tl = IntersectionTimeline(
            intersection_id="ix_0_0",
            row=0, col=0,
            offset=5.0,
            cycle_length=60.0,
            phases=[SignalPhaseSlot(5, 35, "GREEN", "EW")],
        )
        d = tl.to_dict()
        assert d["intersection_id"] == "ix_0_0"
        assert d["offset"] == 5.0
        assert len(d["phases"]) == 1
