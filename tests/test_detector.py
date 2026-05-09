"""Tests for detector and scenarios modules."""

import json
import tempfile
import pytest
from pathlib import Path

from traffic_agent.simulation.detector import (
    DetectorReading,
    DetectorData,
    DetectorSimulator,
    TrendAnalyzer,
    DetectorDataReplay,
)
from traffic_agent.simulation.scenarios import (
    TrafficPhase,
    TrafficScenario,
    morning_peak,
    evening_peak,
    normal_flow,
    pedestrian_heavy,
    accident_scenario,
    bicycle_rush,
    get_scenario,
    list_scenarios,
)


class TestDetectorReading:
    def test_default_values(self):
        r = DetectorReading()
        assert r.vehicles == 0
        assert r.pedestrians == 0
        assert r.bicycles == 0
        assert r.total == 0

    def test_total(self):
        r = DetectorReading(vehicles=5, pedestrians=3, bicycles=2)
        assert r.total == 10

    def test_to_dict(self):
        r = DetectorReading(vehicles=5, pedestrians=3, bicycles=2)
        d = r.to_dict()
        assert d == {"vehicles": 5, "pedestrians": 3, "bicycles": 2}


class TestDetectorData:
    def test_totals(self):
        data = DetectorData(
            intersection_id="ix_1",
            timestamp=10.0,
            readings={
                "north": DetectorReading(5, 2, 1),
                "south": DetectorReading(3, 1, 0),
                "east": DetectorReading(2, 0, 0),
                "west": DetectorReading(1, 0, 0),
            },
        )
        assert data.total_vehicles == 11
        assert data.total_pedestrians == 3
        assert data.total_bicycles == 1

    def test_ns_ew_queue(self):
        data = DetectorData(
            intersection_id="ix_1",
            timestamp=10.0,
            readings={
                "north": DetectorReading(5),
                "south": DetectorReading(3),
                "east": DetectorReading(2),
                "west": DetectorReading(1),
            },
        )
        assert data.get_ns_queue() == 8
        assert data.get_ew_queue() == 3

    def test_to_dict(self):
        data = DetectorData(
            intersection_id="ix_1",
            timestamp=10.0,
            readings={"north": DetectorReading(5)},
        )
        d = data.to_dict()
        assert d["intersection_id"] == "ix_1"
        assert d["total_vehicles"] == 5


class TestDetectorSimulator:
    def test_read_from_simulation(self):
        sim = DetectorSimulator()
        vehicles = {
            0: [1, 2, 3],      # north: 3 vehicles
            1: [1],             # east: 1 vehicle
            2: [1, 2],          # south: 2 vehicles
            3: [],              # west: 0 vehicles
        }
        data = sim.read_from_simulation("ix_1", 10.0, vehicles)
        assert data.intersection_id == "ix_1"
        assert data.readings["north"].vehicles == 3
        assert data.readings["east"].vehicles == 1
        assert data.readings["south"].vehicles == 2
        assert data.readings["west"].vehicles == 0

    def test_read_with_pedestrians(self):
        sim = DetectorSimulator()
        data = sim.read_from_simulation(
            "ix_1", 10.0, {}, pedestrian_count=8, bicycle_count=4
        )
        assert data.total_pedestrians > 0
        assert data.total_bicycles > 0


class TestTrendAnalyzer:
    def test_initial_state(self):
        ta = TrendAnalyzer(window_size=5)
        assert ta.get_ns_trend() == []
        assert ta.get_ew_trend() == []

    def test_update_and_trend(self):
        ta = TrendAnalyzer(window_size=5)
        for i in range(5):
            data = DetectorData(
                intersection_id="ix_1",
                timestamp=float(i),
                readings={
                    "north": DetectorReading(i * 2),
                    "south": DetectorReading(i),
                    "east": DetectorReading(1),
                    "west": DetectorReading(1),
                },
            )
            ta.update(data)

        ns = ta.get_ns_trend()
        assert len(ns) == 5
        # i=4: north=8, south=4, ns_total = 8+4 = 12
        assert ns[-1] == 8 + 4

    def test_increasing_trend(self):
        ta = TrendAnalyzer(window_size=5)
        for i in range(5):
            data = DetectorData(
                intersection_id="ix_1",
                timestamp=float(i),
                readings={
                    "north": DetectorReading(i * 10),
                    "south": DetectorReading(i * 10),
                    "east": DetectorReading(1),
                    "west": DetectorReading(1),
                },
            )
            ta.update(data)

        assert ta.is_increasing("ns_total") is True
        assert ta.is_decreasing("ns_total") is False

    def test_decreasing_trend(self):
        ta = TrendAnalyzer(window_size=5)
        for i in range(5):
            data = DetectorData(
                intersection_id="ix_1",
                timestamp=float(i),
                readings={
                    "north": DetectorReading(10 - i * 2),
                    "south": DetectorReading(10 - i * 2),
                    "east": DetectorReading(1),
                    "west": DetectorReading(1),
                },
            )
            ta.update(data)

        assert ta.is_decreasing("ns_total") is True

    def test_reset(self):
        ta = TrendAnalyzer(window_size=5)
        data = DetectorData(
            intersection_id="ix_1",
            timestamp=0.0,
            readings={"north": DetectorReading(5)},
        )
        ta.update(data)
        ta.reset()
        assert ta.get_ns_trend() == []


class TestDetectorDataReplay:
    def test_from_json(self):
        data = [
            {
                "intersection_id": "ix_1",
                "timestamp": 0.0,
                "readings": {
                    "north": {"vehicles": 5, "pedestrians": 2, "bicycles": 1},
                    "south": {"vehicles": 3, "pedestrians": 0, "bicycles": 0},
                    "east": {"vehicles": 2, "pedestrians": 1, "bicycles": 0},
                    "west": {"vehicles": 1, "pedestrians": 0, "bicycles": 0},
                },
            },
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name

        replay = DetectorDataReplay.from_json(path)
        assert len(replay) == 1

        reading = replay.next()
        assert reading is not None
        assert reading.intersection_id == "ix_1"
        assert reading.readings["north"].vehicles == 5

    def test_reset(self):
        data = [{"intersection_id": "ix_1", "timestamp": 0.0, "readings": {}}]
        replay = DetectorDataReplay(data)
        replay.next()
        assert replay.next() is None

        replay.reset()
        assert replay.next() is not None


class TestTrafficScenarios:
    def test_morning_peak(self):
        s = morning_peak()
        assert s.name == "morning_peak"
        assert s.name_cn == "早高峰"
        assert s.total_steps == 300
        assert s.intersection_type == "crossroad"

    def test_evening_peak(self):
        s = evening_peak()
        assert s.name == "evening_peak"
        assert s.total_steps == 300

    def test_normal_flow(self):
        s = normal_flow()
        assert s.name == "normal"
        assert s.total_steps == 300

    def test_get_phase_at_step(self):
        s = morning_peak()
        # Phase 1: steps 0-49
        assert s.get_phase_at_step(0).name == "ramp_up"
        assert s.get_phase_at_step(49).name == "ramp_up"
        # Phase 2: steps 50-199
        assert s.get_phase_at_step(50).name == "peak"
        assert s.get_phase_at_step(199).name == "peak"
        # Phase 3: steps 200-299
        assert s.get_phase_at_step(200).name == "ramp_down"

    def test_traffic_phase_arrival_rate(self):
        phase = TrafficPhase(
            name="test",
            duration_steps=100,
            arrival_rates={"north": 0.5, "south": 0.3},
            direction_bias={"north": 2.0},
        )
        assert phase.get_arrival_rate("north") == 1.0  # 0.5 * 2.0
        assert phase.get_arrival_rate("south") == 0.3   # no bias

    def test_get_scenario(self):
        s = get_scenario("accident", "tjunction")
        assert s.intersection_type == "tjunction"
        assert s.name == "accident"

    def test_get_scenario_unknown(self):
        with pytest.raises(ValueError, match="Unknown scenario"):
            get_scenario("nonexistent")

    def test_list_scenarios(self):
        scenarios = list_scenarios()
        assert len(scenarios) >= 6
        names = [s["name"] for s in scenarios]
        assert "morning_peak" in names
        assert "accident" in names

    def test_tjunction_scenarios(self):
        for name in ["morning_peak", "normal", "accident"]:
            s = get_scenario(name, "tjunction")
            assert s.intersection_type == "tjunction"

    def test_accident_scenario(self):
        s = accident_scenario()
        assert s.total_steps == 300
        accident_phase = s.phases[1]
        assert accident_phase.emergency_rate == 0.03

    def test_pedestrian_heavy(self):
        s = pedestrian_heavy()
        assert s.phases[0].pedestrian_rate == 0.15

    def test_bicycle_rush(self):
        s = bicycle_rush()
        assert s.phases[0].bicycle_rate == 0.1
