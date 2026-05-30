"""
Tests for Simulation Control module.
"""

import time
import pytest

from traffic_agent.simulation.control import (
    SimulationController,
    SimulationState,
)


class TestSimulationController:
    """Test SimulationController."""

    def test_initial_state(self):
        controller = SimulationController()
        assert controller.state == SimulationState.IDLE
        assert controller.current_step == 0

    def test_start_and_complete(self):
        controller = SimulationController()
        steps_run = []

        def run_fn(step):
            steps_run.append(step)

        controller.start(run_fn, total_steps=5)
        controller.wait(timeout=2.0)

        assert len(steps_run) == 5
        assert controller.state == SimulationState.IDLE

    def test_pause_and_resume(self):
        controller = SimulationController()
        steps_run = []

        def run_fn(step):
            steps_run.append(step)
            time.sleep(0.01)  # Small delay to allow pause

        controller.start(run_fn, total_steps=100)
        time.sleep(0.05)  # Let a few steps run

        controller.pause()
        assert controller.state == SimulationState.PAUSED
        count_at_pause = len(steps_run)

        time.sleep(0.1)  # Should not advance while paused
        assert len(steps_run) == count_at_pause

        controller.resume()
        assert controller.state == SimulationState.RUNNING

        controller.stop()
        controller.wait(timeout=1.0)

    def test_stop(self):
        controller = SimulationController()
        steps_run = []

        def run_fn(step):
            steps_run.append(step)
            time.sleep(0.01)

        controller.start(run_fn, total_steps=100)
        time.sleep(0.05)

        controller.stop()
        controller.wait(timeout=1.0)

        assert controller.state == SimulationState.STOPPED
        assert len(steps_run) < 100

    def test_step_when_paused(self):
        controller = SimulationController()
        steps_run = []

        def run_fn(step):
            steps_run.append(step)

        controller.start(run_fn, total_steps=100)
        time.sleep(0.05)

        controller.pause()
        controller.step()
        time.sleep(0.1)

        # Should have run exactly one more step
        controller.stop()
        controller.wait(timeout=1.0)

    def test_get_status(self):
        controller = SimulationController()
        status = controller.get_status()

        assert status["state"] == "idle"
        assert status["current_step"] == 0
        assert status["progress"] == 0.0

    def test_callbacks(self):
        controller = SimulationController()
        states = []

        def on_state(state):
            states.append(state)

        def run_fn(step):
            pass

        controller.start(run_fn, total_steps=3, on_state_change=on_state)
        controller.wait(timeout=1.0)

        assert SimulationState.RUNNING in states

    def test_cannot_start_while_running(self):
        controller = SimulationController()

        def run_fn(step):
            time.sleep(0.1)

        controller.start(run_fn, total_steps=100)

        with pytest.raises(RuntimeError):
            controller.start(run_fn, total_steps=100)

        controller.stop()
        controller.wait(timeout=1.0)
