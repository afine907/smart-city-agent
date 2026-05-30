"""
Tests for Signal Replay module.
"""

import json
import pytest

from traffic_agent.simulation.replay import (
    ReplayData,
    ReplayRecorder,
    TimingRecord,
)


class TestTimingRecord:
    """Test TimingRecord data class."""

    def test_to_dict(self):
        record = TimingRecord(
            step=1,
            timestamp=1.0,
            phase="NS_GREEN",
            phase_duration=30.0,
            base_duration=30.0,
            adjustment=0.0,
            reasoning="test",
            layer="fixed",
        )
        d = record.to_dict()
        assert d["step"] == 1
        assert d["phase"] == "NS_GREEN"
        assert d["layer"] == "fixed"


class TestReplayData:
    """Test ReplayData container."""

    def test_empty_data(self):
        data = ReplayData(
            intersection_id="test",
            intersection_type="crossroad",
            scenario="normal",
            total_steps=0,
        )
        assert len(data.records) == 0
        assert data.get_adjustments() == []

    def test_add_records(self):
        data = ReplayData(
            intersection_id="test",
            intersection_type="crossroad",
            scenario="normal",
            total_steps=10,
        )
        data.records.append(
            TimingRecord(
                step=1, timestamp=1.0, phase="NS_GREEN",
                phase_duration=30.0, base_duration=30.0,
                adjustment=5.0, reasoning="high traffic", layer="rule",
            )
        )
        assert len(data.records) == 1
        assert len(data.get_adjustments()) == 1

    def test_get_by_layer(self):
        data = ReplayData(
            intersection_id="test",
            intersection_type="crossroad",
            scenario="normal",
            total_steps=10,
        )
        data.records = [
            TimingRecord(step=1, timestamp=1.0, phase="NS_GREEN",
                        phase_duration=30.0, base_duration=30.0,
                        adjustment=0.0, reasoning="", layer="fixed"),
            TimingRecord(step=2, timestamp=2.0, phase="NS_GREEN",
                        phase_duration=35.0, base_duration=30.0,
                        adjustment=5.0, reasoning="", layer="rule"),
            TimingRecord(step=3, timestamp=3.0, phase="NS_GREEN",
                        phase_duration=25.0, base_duration=30.0,
                        adjustment=-5.0, reasoning="", layer="rule"),
        ]
        assert len(data.get_by_layer("fixed")) == 1
        assert len(data.get_by_layer("rule")) == 2

    def test_to_json_and_load(self, tmp_path):
        data = ReplayData(
            intersection_id="test",
            intersection_type="crossroad",
            scenario="normal",
            total_steps=5,
        )
        data.records = [
            TimingRecord(step=1, timestamp=1.0, phase="NS_GREEN",
                        phase_duration=30.0, base_duration=30.0,
                        adjustment=0.0, reasoning="test", layer="fixed"),
        ]

        # Save and reload
        path = tmp_path / "replay.json"
        data.save(path)
        loaded = ReplayData.load(path)

        assert loaded.intersection_id == "test"
        assert len(loaded.records) == 1
        assert loaded.records[0].layer == "fixed"

    def test_get_summary(self):
        data = ReplayData(
            intersection_id="test",
            intersection_type="crossroad",
            scenario="normal",
            total_steps=5,
        )
        data.records = [
            TimingRecord(step=i, timestamp=float(i), phase="NS_GREEN",
                        phase_duration=30.0, base_duration=30.0,
                        adjustment=float(i - 2), reasoning="", layer="rule")
            for i in range(5)
        ]
        summary = data.get_summary()
        assert summary["total_records"] == 5
        assert summary["total_adjustments"] == 4  # steps 0,1,3,4 have non-zero


class TestReplayRecorder:
    """Test ReplayRecorder."""

    def test_recording(self):
        recorder = ReplayRecorder(
            intersection_id="center",
            intersection_type="crossroad",
            scenario="morning_peak",
        )

        for i in range(10):
            recorder.record(
                step=i,
                timestamp=float(i),
                phase="NS_GREEN",
                phase_duration=30.0,
                base_duration=30.0,
                adjustment=float(i % 5),
                reasoning="test",
                layer="rule" if i % 3 == 0 else "fixed",
            )

        data = recorder.finish(10)
        assert data.total_steps == 10
        assert len(data.records) == 10
        assert len(data.get_by_layer("rule")) == 4
