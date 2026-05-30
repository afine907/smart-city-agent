"""
Simulation Control — Pause, resume, and step-through simulation.

Provides fine-grained control over simulation execution for
debugging and analysis purposes.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class SimulationState(Enum):
    """Simulation execution state."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    STEPPING = "stepping"


@dataclass
class SimulationController:
    """
    Controls simulation execution with pause/resume/step capabilities.

    Usage:
        controller = SimulationController()
        controller.start(simulation_run_function)

        # Pause after 100 steps
        controller.pause()
        # Resume
        controller.resume()
        # Step one step at a time
        controller.step()
    """

    state: SimulationState = SimulationState.IDLE
    current_step: int = 0
    target_step: int | None = None
    _speed_multiplier: float = 1.0

    # Threading
    _thread: threading.Thread | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _pause_event: threading.Event = field(default_factory=threading.Event)
    _stop_event: threading.Event = field(default_factory=threading.Event)
    _step_event: threading.Event = field(default_factory=threading.Event)

    # Callbacks
    _on_step: Callable[[int], None] | None = None
    _on_state_change: Callable[[SimulationState], None] | None = None

    def __post_init__(self):
        self._pause_event.set()  # Start in non-paused state

    @property
    def speed_multiplier(self) -> float:
        return self._speed_multiplier

    @speed_multiplier.setter
    def speed_multiplier(self, value: float) -> None:
        if value <= 0:
            raise ValueError(f"speed_multiplier must be positive, got {value}")
        self._speed_multiplier = value

    def start(
        self,
        run_fn: Callable[[int], None],
        total_steps: int,
        on_step: Callable[[int], None] | None = None,
        on_state_change: Callable[[SimulationState], None] | None = None,
    ) -> None:
        """
        Start simulation in a background thread.

        Args:
            run_fn: Function that takes step number and runs one step
            total_steps: Total number of steps to run
            on_step: Callback after each step
            on_state_change: Callback when state changes
        """
        with self._lock:
            if self.state == SimulationState.RUNNING:
                raise RuntimeError("Simulation is already running")

            self._on_step = on_step
            self._on_state_change = on_state_change
            self._stop_event.clear()
            self._pause_event.set()
            self.current_step = 0
            self.target_step = total_steps

            self._thread = threading.Thread(
                target=self._run_loop,
                args=(run_fn, total_steps),
                daemon=True,
            )
            self._set_state(SimulationState.RUNNING)
            self._thread.start()

    def pause(self) -> None:
        """Pause the simulation."""
        with self._lock:
            if self.state != SimulationState.RUNNING:
                return
            self._pause_event.clear()
            self._set_state(SimulationState.PAUSED)

    def resume(self) -> None:
        """Resume the simulation."""
        with self._lock:
            if self.state != SimulationState.PAUSED:
                return
            self._pause_event.set()
            self._set_state(SimulationState.RUNNING)

    def step(self) -> None:
        """Execute a single step (when paused)."""
        with self._lock:
            if self.state != SimulationState.PAUSED:
                return
            self._step_event.set()
            self._set_state(SimulationState.STEPPING)

    def stop(self) -> None:
        """Stop the simulation."""
        with self._lock:
            self._stop_event.set()
            self._pause_event.set()  # Unblock if paused
            self._set_state(SimulationState.STOPPED)

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for simulation to complete."""
        if self._thread is None:
            return True
        self._thread.join(timeout=timeout)
        return not self._thread.is_alive()

    def _run_loop(self, run_fn: Callable[[int], None], total_steps: int) -> None:
        """Main simulation loop."""
        try:
            for step in range(total_steps):
                # Check for stop
                if self._stop_event.is_set():
                    break

                # Wait if paused (blocks until resumed or step)
                self._pause_event.wait()

                # Check if we should execute a single step
                if self._step_event.is_set():
                    self._step_event.clear()
                    # Execute one step
                    run_fn(step)
                    self.current_step = step + 1
                    if self._on_step:
                        self._on_step(step)
                    # Pause again after step
                    self._pause_event.clear()
                    with self._lock:
                        self._set_state(SimulationState.PAUSED)
                    continue

                # Normal execution
                run_fn(step)
                self.current_step = step + 1

                if self._on_step:
                    self._on_step(step)

                # Speed control
                if self._speed_multiplier < 1.0:
                    time.sleep(0.01 / self._speed_multiplier)

        except Exception:
            with self._lock:
                self._set_state(SimulationState.STOPPED)
            raise
        finally:
            if not self._stop_event.is_set():
                with self._lock:
                    self._set_state(SimulationState.IDLE)

    def _set_state(self, new_state: SimulationState) -> None:
        """Update state and notify callback."""
        self.state = new_state
        if self._on_state_change:
            self._on_state_change(new_state)

    def get_status(self) -> dict[str, Any]:
        """Get current controller status."""
        return {
            "state": self.state.value,
            "current_step": self.current_step,
            "target_step": self.target_step,
            "speed_multiplier": self.speed_multiplier,
            "progress": (
                self.current_step / self.target_step
                if self.target_step and self.target_step > 0
                else 0.0
            ),
        }
