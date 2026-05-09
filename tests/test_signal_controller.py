"""Tests for signal controller module."""

import pytest
from traffic_agent.simulation.signal_controller import (
    SignalController,
    SignalPlan,
    PhaseConfig,
    SignalState,
    crossroad_plan,
    tjunction_plan,
    ADJUSTMENT_MIN,
    ADJUSTMENT_MAX,
    MIN_GREEN_TIME,
    MAX_GREEN_TIME,
)


class TestPhaseConfig:
    def test_create_phase(self):
        phase = PhaseConfig("NS_GREEN", [0, 2], 60.0)
        assert phase.name == "NS_GREEN"
        assert phase.green_approaches == [0, 2]
        assert phase.green_duration == 60.0
        assert phase.yellow == 3.0
        assert phase.all_red == 2.0


class TestSignalPlans:
    def test_crossroad_plan(self):
        plan = crossroad_plan()
        assert plan.intersection_type == "crossroad"
        assert len(plan.phases) == 6
        assert plan.phases[0].name == "NS_GREEN"
        assert plan.phases[3].name == "EW_GREEN"

    def test_crossroad_custom_timing(self):
        plan = crossroad_plan(ns_green=45.0, ew_green=75.0)
        assert plan.phases[0].green_duration == 45.0
        assert plan.phases[3].green_duration == 75.0

    def test_tjunction_plan(self):
        plan = tjunction_plan()
        assert plan.intersection_type == "tjunction"
        assert len(plan.phases) == 5
        assert plan.phases[0].name == "NS_GREEN"
        assert plan.phases[3].name == "EW_GREEN"

    def test_tjunction_ew_has_one_approach(self):
        plan = tjunction_plan()
        # EW phase for T-junction should only have approach 1 (east)
        ew_phase = plan.phases[3]
        assert ew_phase.green_approaches == [1]


class TestSignalController:
    def test_initial_state(self):
        ctrl = SignalController(crossroad_plan())
        state = ctrl.get_state()
        assert state.current_phase == "NS_GREEN"
        assert state.phase_elapsed == 0.0
        assert state.adjustment == 0
        assert state.cycle_count == 0

    def test_step_advances_time(self):
        ctrl = SignalController(crossroad_plan())
        ctrl.step(1.0)
        state = ctrl.get_state()
        assert state.phase_elapsed == 1.0

    def test_phase_transitions(self):
        plan = crossroad_plan(ns_green=10.0, ew_green=10.0)
        ctrl = SignalController(plan)

        # NS_GREEN is 10s
        for _ in range(10):
            changed = ctrl.step(1.0)
        assert changed  # should transition at 10s
        assert ctrl.get_state().current_phase == "NS_YELLOW"

    def test_full_cycle(self):
        plan = crossroad_plan(ns_green=10.0, ew_green=10.0)
        ctrl = SignalController(plan)

        # Run through one full cycle
        phases_seen = [ctrl.get_state().current_phase]
        for _ in range(200):  # enough steps for a full cycle
            if ctrl.step(1.0):
                phases_seen.append(ctrl.get_state().current_phase)
            if ctrl.get_state().cycle_count > 0:
                break

        # Should see all phases
        assert "NS_GREEN" in phases_seen
        assert "NS_YELLOW" in phases_seen
        assert "EW_GREEN" in phases_seen
        assert "EW_YELLOW" in phases_seen

    def test_apply_adjustment_extend(self):
        ctrl = SignalController(crossroad_plan(ns_green=60.0))
        assert ctrl.is_green

        # Extend green by 8 seconds
        result = ctrl.apply_adjustment(8)
        assert result is True
        state = ctrl.get_state()
        assert state.adjustment == 8
        assert state.phase_duration == 68.0  # 60 + 8

    def test_apply_adjustment_shorten(self):
        ctrl = SignalController(crossroad_plan(ns_green=60.0))
        result = ctrl.apply_adjustment(-5)
        assert result is True
        state = ctrl.get_state()
        assert state.adjustment == -5
        assert state.phase_duration == 55.0  # 60 - 5

    def test_adjustment_clamped(self):
        ctrl = SignalController(crossroad_plan(ns_green=60.0))
        ctrl.apply_adjustment(100)  # try to extend too much
        assert ctrl.get_state().adjustment == ADJUSTMENT_MAX

        ctrl2 = SignalController(crossroad_plan(ns_green=60.0))
        ctrl2.apply_adjustment(-100)  # try to shorten too much
        assert ctrl2.get_state().adjustment == ADJUSTMENT_MIN

    def test_adjustment_respects_min_green(self):
        ctrl = SignalController(crossroad_plan(ns_green=20.0))
        # Try to shorten below MIN_GREEN_TIME (15s)
        ctrl.apply_adjustment(-10)
        # 20 - 10 = 10, which is < 15, so adjustment should be clamped
        assert ctrl.get_state().phase_duration >= MIN_GREEN_TIME

    def test_adjustment_respects_max_green(self):
        ctrl = SignalController(crossroad_plan(ns_green=85.0))
        # Try to extend above MAX_GREEN_TIME (90s)
        ctrl.apply_adjustment(10)
        # 85 + 10 = 95, which is > 90, so adjustment should be clamped
        assert ctrl.get_state().phase_duration <= MAX_GREEN_TIME

    def test_only_one_adjustment_per_green_phase(self):
        ctrl = SignalController(crossroad_plan(ns_green=60.0))
        assert ctrl.apply_adjustment(5) is True
        assert ctrl.apply_adjustment(5) is False  # second attempt rejected

    def test_no_adjustment_during_yellow(self):
        plan = crossroad_plan(ns_green=10.0, ew_green=10.0)
        ctrl = SignalController(plan)

        # Advance to NS_YELLOW
        for _ in range(10):
            ctrl.step(1.0)
        assert ctrl.get_state().current_phase == "NS_YELLOW"
        assert ctrl.is_green is False

        # Adjustment should be rejected
        assert ctrl.apply_adjustment(5) is False

    def test_adjustment_resets_on_phase_change(self):
        plan = crossroad_plan(ns_green=10.0, ew_green=10.0)
        ctrl = SignalController(plan)

        ctrl.apply_adjustment(5)
        assert ctrl.get_state().adjustment == 5

        # Advance past NS_GREEN
        for _ in range(15):
            ctrl.step(1.0)

        # Should be in a new phase with no adjustment
        assert ctrl.get_state().adjustment == 0

    def test_green_approaches(self):
        ctrl = SignalController(crossroad_plan())
        assert ctrl.green_approaches == [0, 2]  # NS

    def test_has_green_for(self):
        ctrl = SignalController(crossroad_plan())
        assert ctrl.has_green_for(0) is True   # North
        assert ctrl.has_green_for(2) is True   # South
        assert ctrl.has_green_for(1) is False  # East
        assert ctrl.has_green_for(3) is False  # West

    def test_cycle_count(self):
        plan = crossroad_plan(ns_green=5.0, ew_green=5.0)
        ctrl = SignalController(plan)

        # Run for multiple cycles
        for _ in range(500):
            ctrl.step(0.5)

        assert ctrl.get_state().cycle_count > 0

    def test_reset(self):
        ctrl = SignalController(crossroad_plan())
        ctrl.step(10.0)
        ctrl.apply_adjustment(5)

        ctrl.reset()
        state = ctrl.get_state()
        assert state.phase_elapsed == 0.0
        assert state.adjustment == 0
        assert state.cycle_count == 0

    def test_plan_info(self):
        ctrl = SignalController(crossroad_plan())
        info = ctrl.get_plan_info()
        assert info["type"] == "crossroad"
        assert len(info["phases"]) == 6

    def test_phase_remaining(self):
        ctrl = SignalController(crossroad_plan(ns_green=60.0))
        ctrl.step(20.0)
        state = ctrl.get_state()
        assert state.phase_remaining == 40.0

    def test_phase_remaining_with_adjustment(self):
        ctrl = SignalController(crossroad_plan(ns_green=60.0))
        ctrl.step(20.0)
        ctrl.apply_adjustment(10)
        state = ctrl.get_state()
        # remaining = (60 + 10) - 20 = 50
        assert state.phase_remaining == 50.0
