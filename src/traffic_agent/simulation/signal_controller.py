"""
Signal Controller — Baseline timing plan with ±10s LLM adjustment.

Models a real-world traffic signal that operates on a fixed baseline plan,
with an AI adjustment layer that can modify phase durations by ±10s.

Core concept:
- The signal runs on a FIXED baseline plan (e.g., NS 60s, EW 90s)
- LLM/rule engine can suggest adjustments to the current phase's remaining time
- Adjustments are clamped to [-10, +10] for safety
- Minimum green time is always enforced (15s)
- Maximum green time is always enforced (90s)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Constants
ADJUSTMENT_MIN = -10
ADJUSTMENT_MAX = 10
MIN_GREEN_TIME = 15.0
MAX_GREEN_TIME = 90.0
DEFAULT_YELLOW = 3.0
DEFAULT_ALL_RED = 2.0


@dataclass
class PhaseConfig:
    """Configuration for a single signal phase."""
    name: str
    green_approaches: List[int]  # which approaches get green: 0=N, 1=E, 2=S, 3=W
    green_duration: float        # baseline green duration in seconds
    yellow: float = DEFAULT_YELLOW
    all_red: float = DEFAULT_ALL_RED


@dataclass
class SignalPlan:
    """A complete signal timing plan for an intersection."""
    name: str
    phases: List[PhaseConfig]
    intersection_type: str = "crossroad"  # "crossroad" or "tjunction"


@dataclass
class SignalState:
    """Current state of the signal controller."""
    current_phase: str
    phase_elapsed: float        # seconds elapsed in current phase
    phase_duration: float       # total duration of current phase (base + adjustment)
    base_duration: float        # baseline duration before adjustment
    adjustment: int = 0         # current adjustment in seconds (-10 to +10)
    cycle_count: int = 0        # number of complete cycles
    phase_index: int = 0        # index in the phase sequence

    @property
    def phase_remaining(self) -> float:
        """Seconds remaining in the current phase."""
        return max(0.0, self.phase_duration - self.phase_elapsed)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_phase": self.current_phase,
            "phase_elapsed": round(self.phase_elapsed, 1),
            "phase_duration": round(self.phase_duration, 1),
            "base_duration": round(self.base_duration, 1),
            "phase_remaining": round(self.phase_remaining, 1),
            "adjustment": self.adjustment,
            "cycle_count": self.cycle_count,
            "phase_index": self.phase_index,
        }


# ─── Predefined Signal Plans ────────────────────────────────────

def crossroad_plan(
    ns_green: float = 60.0,
    ew_green: float = 90.0,
    yellow: float = DEFAULT_YELLOW,
    all_red: float = DEFAULT_ALL_RED,
) -> SignalPlan:
    """Standard crossroad signal plan: NS → NS_YELLOW → ALL_RED → EW → EW_YELLOW → ALL_RED."""
    return SignalPlan(
        name="crossroad_default",
        intersection_type="crossroad",
        phases=[
            PhaseConfig("NS_GREEN", [0, 2], ns_green, yellow, all_red),
            PhaseConfig("NS_YELLOW", [], yellow, yellow, 0.0),
            PhaseConfig("ALL_RED_1", [], all_red, 0.0, all_red),
            PhaseConfig("EW_GREEN", [1, 3], ew_green, yellow, all_red),
            PhaseConfig("EW_YELLOW", [], yellow, yellow, 0.0),
            PhaseConfig("ALL_RED_2", [], all_red, 0.0, all_red),
        ],
    )


def tjunction_plan(
    ns_green: float = 45.0,
    ew_green: float = 35.0,
    yellow: float = DEFAULT_YELLOW,
    all_red: float = DEFAULT_ALL_RED,
) -> SignalPlan:
    """T-junction signal plan: NS → NS_YELLOW → ALL_RED → EW → EW_YELLOW."""
    return SignalPlan(
        name="tjunction_default",
        intersection_type="tjunction",
        phases=[
            PhaseConfig("NS_GREEN", [0, 2], ns_green, yellow, all_red),
            PhaseConfig("NS_YELLOW", [], yellow, yellow, 0.0),
            PhaseConfig("ALL_RED", [], all_red, 0.0, all_red),
            PhaseConfig("EW_GREEN", [1], ew_green, yellow, all_red),
            PhaseConfig("EW_YELLOW", [], yellow, yellow, 0.0),
        ],
    )


class SignalController:
    """
    Controls a traffic signal with baseline timing and LLM adjustment.

    Usage:
        plan = crossroad_plan()
        controller = SignalController(plan)

        # Each simulation step:
        controller.step(1.0)  # advance 1 second
        state = controller.get_state()

        # When LLM suggests an adjustment:
        controller.apply_adjustment(8)  # extend current green by 8s
    """

    def __init__(self, plan: SignalPlan):
        self.plan = plan
        self._phase_index: int = 0
        self._phase_elapsed: float = 0.0
        self._adjustment: int = 0
        self._adjustment_applied: bool = False  # only one adjustment per green phase
        self._cycle_count: int = 0

    @property
    def current_phase(self) -> PhaseConfig:
        return self.plan.phases[self._phase_index]

    @property
    def is_green(self) -> bool:
        """Check if current phase is a green phase (has green approaches)."""
        return len(self.current_phase.green_approaches) > 0

    @property
    def green_approaches(self) -> List[int]:
        """Get the approaches that have green in the current phase."""
        return self.current_phase.green_approaches

    def get_state(self) -> SignalState:
        """Get the current signal state."""
        phase = self.current_phase
        base_dur = self._get_phase_duration(phase)
        actual_dur = base_dur + self._adjustment if self.is_green else base_dur

        return SignalState(
            current_phase=phase.name,
            phase_elapsed=self._phase_elapsed,
            phase_duration=actual_dur,
            base_duration=base_dur,
            adjustment=self._adjustment if self.is_green else 0,
            cycle_count=self._cycle_count,
            phase_index=self._phase_index,
        )

    def get_plan_info(self) -> Dict[str, Any]:
        """Get the baseline plan information."""
        return {
            "name": self.plan.name,
            "type": self.plan.intersection_type,
            "phases": [
                {
                    "name": p.name,
                    "duration": self._get_phase_duration(p),
                    "green_approaches": p.green_approaches,
                }
                for p in self.plan.phases
            ],
        }

    def step(self, dt: float) -> bool:
        """
        Advance the signal by dt seconds.

        Returns True if the phase changed.
        """
        self._phase_elapsed += dt
        phase = self.current_phase

        # Calculate effective duration
        effective_duration = self._get_phase_duration(phase)
        if self.is_green and self._adjustment != 0:
            adjusted = effective_duration + self._adjustment
            # Enforce min/max green only when there's an adjustment
            effective_duration = max(MIN_GREEN_TIME, min(MAX_GREEN_TIME, adjusted))

        # Check if phase should end
        if self._phase_elapsed >= effective_duration:
            self._advance_phase()
            return True

        return False

    def apply_adjustment(self, adjustment: int) -> bool:
        """
        Apply an adjustment to the current green phase's remaining time.

        Args:
            adjustment: seconds to adjust (-10 to +10)

        Returns:
            True if adjustment was applied, False if rejected.
        """
        # Only allow adjustments during green phases
        if not self.is_green:
            return False

        # Only one adjustment per green phase
        if self._adjustment_applied:
            return False

        # Clamp adjustment
        adjustment = max(ADJUSTMENT_MIN, min(ADJUSTMENT_MAX, adjustment))

        # Check that the resulting duration is within bounds
        base_dur = self._get_phase_duration(self.current_phase)
        new_dur = base_dur + adjustment
        if new_dur < MIN_GREEN_TIME:
            adjustment = int(MIN_GREEN_TIME - base_dur)
        elif new_dur > MAX_GREEN_TIME:
            adjustment = int(MAX_GREEN_TIME - base_dur)

        self._adjustment = adjustment
        self._adjustment_applied = True
        return True

    def reset(self) -> None:
        """Reset the controller to initial state."""
        self._phase_index = 0
        self._phase_elapsed = 0.0
        self._adjustment = 0
        self._adjustment_applied = False
        self._cycle_count = 0

    def has_green_for(self, approach: int) -> bool:
        """Check if a specific approach has green light."""
        return approach in self.current_phase.green_approaches

    def _get_phase_duration(self, phase: PhaseConfig) -> float:
        """Get the base duration of a phase."""
        if phase.name.endswith("_YELLOW"):
            return phase.yellow
        elif phase.name.startswith("ALL_RED"):
            return phase.all_red
        else:
            return phase.green_duration

    def _advance_phase(self) -> None:
        """Advance to the next phase in the cycle."""
        self._phase_index = (self._phase_index + 1) % len(self.plan.phases)
        self._phase_elapsed = 0.0
        self._adjustment = 0
        self._adjustment_applied = False

        # Track cycle completion
        if self._phase_index == 0:
            self._cycle_count += 1
