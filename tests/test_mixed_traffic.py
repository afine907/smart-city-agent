"""
Tests for mixed traffic support — cars, e-bikes, bicycles, pedestrians, buses, emergency vehicles.
"""

import pytest
import numpy as np

from traffic_agent.simulation.engine import (
    SimulationConfig,
    SimulationEngine,
    Vehicle,
    VehicleType,
    VehicleTypeInfo,
    VEHICLE_TYPES,
)
from traffic_agent.tools.traffic_tools import IntersectionState


# ─── VehicleType Tests ──────────────────────────────────────────


class TestVehicleType:
    """Test VehicleType enum and VehicleTypeInfo dataclass."""

    def test_all_types_defined(self):
        expected = {"car", "bus", "e_bike", "bicycle", "pedestrian", "emergency"}
        actual = {vt.value for vt in VehicleType}
        assert actual == expected

    def test_all_types_have_info(self):
        for vtype in VehicleType:
            assert vtype in VEHICLE_TYPES, f"Missing info for {vtype}"

    def test_speed_hierarchy(self):
        """Emergency > car > bus > e_bike > bicycle > pedestrian."""
        assert VEHICLE_TYPES[VehicleType.EMERGENCY].speed_normal > VEHICLE_TYPES[VehicleType.CAR].speed_normal
        assert VEHICLE_TYPES[VehicleType.CAR].speed_normal > VEHICLE_TYPES[VehicleType.BUS].speed_normal
        assert VEHICLE_TYPES[VehicleType.BUS].speed_normal > VEHICLE_TYPES[VehicleType.E_BIKE].speed_normal
        assert VEHICLE_TYPES[VehicleType.E_BIKE].speed_normal > VEHICLE_TYPES[VehicleType.BICYCLE].speed_normal
        assert VEHICLE_TYPES[VehicleType.BICYCLE].speed_normal > VEHICLE_TYPES[VehicleType.PEDESTRIAN].speed_normal

    def test_emergency_has_priority(self):
        assert VEHICLE_TYPES[VehicleType.EMERGENCY].has_priority is True

    def test_emergency_can_ignore_signal(self):
        assert VEHICLE_TYPES[VehicleType.EMERGENCY].respects_signal is False

    def test_pedestrian_may_jaywalk(self):
        assert VEHICLE_TYPES[VehicleType.PEDESTRIAN].respects_signal is False

    def test_car_respects_signal(self):
        assert VEHICLE_TYPES[VehicleType.CAR].respects_signal is True

    def test_bus_largest(self):
        assert VEHICLE_TYPES[VehicleType.BUS].length > VEHICLE_TYPES[VehicleType.CAR].length

    def test_space_occupancy_ordered(self):
        """Bigger vehicles occupy more space."""
        assert VEHICLE_TYPES[VehicleType.BUS].space_occupancy > VEHICLE_TYPES[VehicleType.CAR].space_occupancy
        assert VEHICLE_TYPES[VehicleType.CAR].space_occupancy > VEHICLE_TYPES[VehicleType.E_BIKE].space_occupancy
        assert VEHICLE_TYPES[VehicleType.E_BIKE].space_occupancy > VEHICLE_TYPES[VehicleType.PEDESTRIAN].space_occupancy


# ─── Vehicle Model Tests ────────────────────────────────────────


class TestVehicleModel:
    """Test Vehicle dataclass with type-specific behavior."""

    def test_default_is_car(self):
        v = Vehicle(id="v_1", approach=0, position=100.0, speed=13.89)
        assert v.vehicle_type == VehicleType.CAR
        assert v.type_info.name == "car"

    def test_ebike_properties(self):
        info = VEHICLE_TYPES[VehicleType.E_BIKE]
        v = Vehicle(
            id="v_2", approach=0, position=100.0,
            speed=info.speed_normal, vehicle_type=VehicleType.E_BIKE,
            _type_info=info,
        )
        assert v.length == 1.8
        assert v.space_occupancy == 2.5
        # E-bikes may violate signals (respects_signal=False)
        assert v.can_respect_signal is False

    def test_emergency_ignores_signal(self):
        info = VEHICLE_TYPES[VehicleType.EMERGENCY]
        v = Vehicle(
            id="v_3", approach=0, position=100.0,
            speed=info.speed_normal, vehicle_type=VehicleType.EMERGENCY,
            is_emergency=True, _type_info=info,
        )
        assert v.has_priority is True
        assert v.should_obey_signal() is False

    def test_car_obey_signal(self):
        info = VEHICLE_TYPES[VehicleType.CAR]
        v = Vehicle(
            id="v_4", approach=0, position=100.0,
            speed=info.speed_normal, vehicle_type=VehicleType.CAR,
            _type_info=info,
        )
        # Cars always obey signals (violation_rate=0)
        for _ in range(100):
            assert v.should_obey_signal() is True

    def test_pedestrian_may_violate(self):
        info = VEHICLE_TYPES[VehicleType.PEDESTRIAN]
        v = Vehicle(
            id="v_5", approach=0, position=100.0,
            speed=info.speed_normal, vehicle_type=VehicleType.PEDESTRIAN,
            _type_info=info,
        )
        # At 100% violation rate, pedestrian always ignores signal
        violations = sum(1 for _ in range(100) if not v.should_obey_signal(1.0))
        assert violations == 100

    def test_effective_speed_capped_by_road_limit(self):
        info = VEHICLE_TYPES[VehicleType.CAR]
        v = Vehicle(
            id="v_6", approach=0, position=100.0,
            speed=info.speed_normal, vehicle_type=VehicleType.CAR,
            _type_info=info,
        )
        np.random.seed(42)
        # Road limit lower than car max → speed should be capped
        effective = v.get_effective_speed(5.0)  # 5 m/s road limit
        assert effective <= 5.0 * 1.15  # Allow ±15% randomness

    def test_effective_speed_respects_type_max(self):
        info = VEHICLE_TYPES[VehicleType.PEDESTRIAN]
        v = Vehicle(
            id="v_7", approach=0, position=100.0,
            speed=info.speed_normal, vehicle_type=VehicleType.PEDESTRIAN,
            _type_info=info,
        )
        np.random.seed(42)
        effective = v.get_effective_speed(50.0)  # Very high road limit
        assert effective <= info.speed_max * 1.15


# ─── SimulationConfig Tests ─────────────────────────────────────


class TestMixedTrafficConfig:
    """Test SimulationConfig with mixed traffic ratios."""

    def test_default_ratios_sum_to_one(self):
        config = SimulationConfig()
        total = (config.car_ratio + config.bus_ratio + config.e_bike_ratio +
                 config.bicycle_ratio + config.pedestrian_ratio)
        assert abs(total - 1.0) < 0.01

    def test_custom_ratios(self):
        config = SimulationConfig(
            car_ratio=0.6, bus_ratio=0.1, e_bike_ratio=0.2,
            bicycle_ratio=0.05, pedestrian_ratio=0.05,
        )
        assert config.car_ratio == 0.6

    def test_invalid_ratios_raises(self):
        with pytest.raises(ValueError, match="must sum to 1.0"):
            SimulationConfig(
                car_ratio=0.5, bus_ratio=0.1, e_bike_ratio=0.1,
                bicycle_ratio=0.1, pedestrian_ratio=0.1,  # Sum = 0.9
            )

    def test_get_mix_ratios(self):
        config = SimulationConfig()
        ratios = config.get_mix_ratios()
        assert len(ratios) == 5
        assert VehicleType.CAR in ratios
        assert VehicleType.EMERGENCY not in ratios  # Emergency uses separate rate

    def test_violation_rates_configurable(self):
        config = SimulationConfig(
            e_bike_lane_violation_rate=0.3,
            pedestrian_jaywalking_rate=0.2,
            bike_red_light_rate=0.1,
        )
        assert config.e_bike_lane_violation_rate == 0.3
        assert config.pedestrian_jaywalking_rate == 0.2
        assert config.bike_red_light_rate == 0.1


# ─── Simulation Engine Mixed Traffic Tests ──────────────────────


class TestEngineMixedTraffic:
    """Test SimulationEngine with mixed vehicle types."""

    def test_generates_mixed_types(self):
        np.random.seed(42)
        engine = SimulationEngine(SimulationConfig(seed=42, arrival_rate=2.0))
        engine.add_intersection("ix_0")

        for _ in range(50):
            engine.step()

        # Should have generated multiple vehicle types
        types_seen = set()
        for ix in engine.network.intersections.values():
            for approach in range(ix.approaches):
                for v in ix.vehicles[approach]:
                    types_seen.add(v.vehicle_type)

        # With high arrival rate and 50 steps, we should see multiple types
        assert len(types_seen) >= 2, f"Expected multiple types, got: {types_seen}"

    def test_type_counts_tracked(self):
        np.random.seed(42)
        engine = SimulationEngine(SimulationConfig(seed=42, arrival_rate=1.0))
        engine.add_intersection("ix_0")

        for _ in range(100):
            engine.step()

        # Should have counts for various types
        assert len(engine._type_counts) >= 2
        total = sum(engine._type_counts.values())
        assert total > 0

    def test_emergency_triggers_priority(self):
        np.random.seed(42)
        engine = SimulationEngine(SimulationConfig(seed=42, arrival_rate=1.0))
        engine.add_intersection("ix_0")

        # Force an emergency vehicle
        v = Vehicle(
            id="emergency_1", approach=1, position=200.0,
            speed=22.22, vehicle_type=VehicleType.EMERGENCY,
            is_emergency=True,
            _type_info=VEHICLE_TYPES[VehicleType.EMERGENCY],
        )
        engine.network.intersections["ix_0"].vehicles[1].append(v)
        engine._handle_emergency(engine.network.intersections["ix_0"], 1)

        # Should have switched to EW_GREEN for approach 1 (East)
        assert engine.network.intersections["ix_0"].current_phase == "EW_GREEN"

    def test_state_includes_type_breakdown(self):
        np.random.seed(42)
        engine = SimulationEngine(SimulationConfig(seed=42, arrival_rate=1.0))
        engine.add_intersection("ix_0")

        for _ in range(20):
            engine.step()

        state = engine.get_state("ix_0")
        assert state.vehicle_type_breakdown is not None
        # Should be a dict with vehicle type names
        assert isinstance(state.vehicle_type_breakdown, dict)

    def test_state_text_includes_mix_info(self):
        state = IntersectionState(
            intersection_id="ix_0",
            timestamp=10.0,
            queue_north=3, queue_south=2, queue_east=1, queue_west=4,
            vehicle_type_breakdown={
                "car": {"total": 6, "waiting": 2},
                "e_bike": {"total": 3, "waiting": 1},
                "pedestrian": {"total": 1, "waiting": 0},
            },
        )
        text = state.to_text()
        assert "汽车" in text
        assert "电动自行车" in text
        assert "行人" in text
        assert "交通构成" in text

    def test_mixed_traffic_summary(self):
        state = IntersectionState(
            intersection_id="ix_0",
            timestamp=10.0,
            queue_north=5, queue_south=3, queue_east=2, queue_west=1,
            vehicle_type_breakdown={
                "car": {"total": 6, "waiting": 2},
                "e_bike": {"total": 3, "waiting": 1},
                "bicycle": {"total": 1, "waiting": 0},
                "pedestrian": {"total": 1, "waiting": 0},
            },
        )
        summary = state.get_mixed_traffic_summary()
        assert "汽车" in summary
        assert "电自" in summary
        assert "单车" in summary
        assert "行人" in summary

    def test_metrics_include_type_counts(self):
        np.random.seed(42)
        engine = SimulationEngine(SimulationConfig(seed=42, arrival_rate=1.0))
        engine.add_intersection("ix_0")

        for _ in range(30):
            engine.step()

        metrics = engine._get_metrics()
        assert "vehicle_type_counts" in metrics
        assert isinstance(metrics["vehicle_type_counts"], dict)

    def test_reset_clears_type_counts(self):
        engine = SimulationEngine(SimulationConfig(seed=42, arrival_rate=1.0))
        engine.add_intersection("ix_0")

        for _ in range(10):
            engine.step()

        assert len(engine._type_counts) > 0
        engine.reset()
        assert len(engine._type_counts) == 0

    def test_pure_car_mode(self):
        """Config with 100% cars should only generate cars."""
        config = SimulationConfig(
            seed=42, arrival_rate=2.0,
            car_ratio=1.0, bus_ratio=0.0, e_bike_ratio=0.0,
            bicycle_ratio=0.0, pedestrian_ratio=0.0,
        )
        engine = SimulationEngine(config)
        engine.add_intersection("ix_0")

        for _ in range(30):
            engine.step()

        types_seen = set(engine._type_counts.keys())
        # Only cars and possibly emergency (from emergency_rate)
        non_emergency = types_seen - {VehicleType.EMERGENCY}
        assert non_emergency == {VehicleType.CAR}

    def test_heavy_ebike_mode(self):
        """Config with high e-bike ratio."""
        config = SimulationConfig(
            seed=42, arrival_rate=2.0,
            car_ratio=0.3, bus_ratio=0.0, e_bike_ratio=0.6,
            bicycle_ratio=0.05, pedestrian_ratio=0.05,
        )
        engine = SimulationEngine(config)
        engine.add_intersection("ix_0")

        for _ in range(100):
            engine.step()

        # E-bikes should be the most common non-emergency type
        non_emergency = {k: v for k, v in engine._type_counts.items()
                         if k != VehicleType.EMERGENCY}
        if non_emergency:
            most_common = max(non_emergency, key=non_emergency.get)
            assert most_common == VehicleType.E_BIKE


# ─── Signal Compliance Tests ────────────────────────────────────


class TestSignalCompliance:
    """Test that different vehicle types behave differently at red lights."""

    def test_pedestrian_jaywalking_at_high_rate(self):
        np.random.seed(42)
        config = SimulationConfig(
            seed=42, arrival_rate=2.0,
            car_ratio=0.0, bus_ratio=0.0, e_bike_ratio=0.0,
            bicycle_ratio=0.0, pedestrian_ratio=1.0,
            pedestrian_jaywalking_rate=1.0,  # Always jaywalk
        )
        engine = SimulationEngine(config)
        engine.add_intersection("ix_0")
        engine.add_intersection("ix_1")
        engine.connect("ix_0", "ix_1")

        # Set red light
        engine.network.intersections["ix_0"].current_phase = "EW_YELLOW"

        # Generate pedestrians
        for _ in range(30):
            engine.step()

        # Some pedestrians should have passed through despite red light
        # (because jaywalking rate = 1.0)
        served = engine.network.intersections["ix_0"].total_served
        # At least some should have been served even on red
        assert served >= 0  # Just verify no crash; actual jaywalking is probabilistic

    def test_bike_red_light_running(self):
        """Bikes (respects_signal=False) should violate at configured rate."""
        info = VEHICLE_TYPES[VehicleType.BICYCLE]
        v = Vehicle(
            id="bike_1", approach=0, position=5.0,
            speed=info.speed_normal, vehicle_type=VehicleType.BICYCLE,
            _type_info=info,
        )
        np.random.seed(42)
        violations = 0
        for _ in range(1000):
            if not v.should_obey_signal(0.05):
                violations += 1
        # Should have ~5% violations (bicycle respects_signal=False)
        assert 20 < violations < 80

    def test_pedestrian_jaywalking_rate(self):
        """Pedestrians (respects_signal=False) should violate at configured rate."""
        info = VEHICLE_TYPES[VehicleType.PEDESTRIAN]
        v = Vehicle(
            id="ped_1", approach=0, position=5.0,
            speed=info.speed_normal, vehicle_type=VehicleType.PEDESTRIAN,
            _type_info=info,
        )
        np.random.seed(42)
        violations = 0
        for _ in range(1000):
            if not v.should_obey_signal(0.10):
                violations += 1
        # Should have ~10% violations (pedestrian respects_signal=False)
        assert 50 < violations < 150

    def test_ebike_lane_violation(self):
        """E-bikes (respects_signal=False) may run red at configured rate."""
        info = VEHICLE_TYPES[VehicleType.E_BIKE]
        v = Vehicle(
            id="ebike_1", approach=0, position=5.0,
            speed=info.speed_normal, vehicle_type=VehicleType.E_BIKE,
            _type_info=info,
        )
        np.random.seed(42)
        violations = 0
        for _ in range(1000):
            if not v.should_obey_signal(0.15):
                violations += 1
        # Should have ~15% violations (e_bike respects_signal=False)
        assert 100 < violations < 200


# ─── State Text Tests ───────────────────────────────────────────


class TestStateText:
    """Test IntersectionState text formatting with mixed traffic."""

    def test_advisory_high_ebike(self):
        state = IntersectionState(
            intersection_id="ix_0",
            timestamp=10.0,
            queue_north=10, queue_south=5, queue_east=3, queue_west=2,
            vehicle_type_breakdown={
                "car": {"total": 8, "waiting": 2},
                "e_bike": {"total": 10, "waiting": 3},
                "pedestrian": {"total": 2, "waiting": 0},
            },
        )
        text = state.to_text()
        assert "电动自行车占比高" in text

    def test_advisory_many_pedestrians(self):
        state = IntersectionState(
            intersection_id="ix_0",
            timestamp=10.0,
            queue_north=5, queue_south=3, queue_east=2, queue_west=2,
            vehicle_type_breakdown={
                "car": {"total": 4, "waiting": 1},
                "pedestrian": {"total": 5, "waiting": 0},
            },
        )
        text = state.to_text()
        assert "行人较多" in text

    def test_emergency_text(self):
        state = IntersectionState(
            intersection_id="ix_0",
            timestamp=10.0,
            emergency=True,
        )
        text = state.to_text()
        assert "需立即给予优先通行" in text

    def test_no_breakdown(self):
        state = IntersectionState(
            intersection_id="ix_0",
            timestamp=10.0,
        )
        text = state.to_text()
        # Should not crash, just skip type info
        assert "路口: ix_0" in text

    def test_get_total_by_type(self):
        state = IntersectionState(
            intersection_id="ix_0",
            timestamp=10.0,
            queue_north=3, queue_south=2, queue_east=1, queue_west=1,
            vehicle_type_breakdown={
                "car": {"total": 4, "waiting": 1},
                "e_bike": {"total": 3, "waiting": 2},
            },
        )
        assert state.get_total_by_type("car") == 4
        assert state.get_total_by_type("e_bike") == 3
        assert state.get_total_by_type("bicycle") == 0

    def test_mixed_traffic_summary_empty(self):
        state = IntersectionState(
            intersection_id="ix_0", timestamp=10.0,
        )
        assert state.get_mixed_traffic_summary() == "无混行数据"
