"""
Green Wave Visualization — visualizes signal coordination along corridors.

Generates timeline data showing signal phases and offsets for
green wave coordination along NS and EW corridors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CorridorDirection(str, Enum):
    """Corridor direction."""
    NS = "NS"
    EW = "EW"


@dataclass
class SignalPhaseSlot:
    """A single phase slot in the signal timeline."""
    start_time: float
    end_time: float
    phase: str  # "GREEN", "YELLOW", "RED"
    direction: str  # "NS" or "EW"


@dataclass
class IntersectionTimeline:
    """Signal timeline for a single intersection."""
    intersection_id: str
    row: int
    col: int
    offset: float  # Phase offset in seconds
    cycle_length: float  # Full cycle length in seconds
    phases: list[SignalPhaseSlot] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intersection_id": self.intersection_id,
            "row": self.row,
            "col": self.col,
            "offset": self.offset,
            "cycle_length": self.cycle_length,
            "phases": [
                {
                    "start": p.start_time,
                    "end": p.end_time,
                    "phase": p.phase,
                    "direction": p.direction,
                }
                for p in self.phases
            ],
        }


@dataclass
class GreenWaveData:
    """Complete green wave visualization data."""
    direction: CorridorDirection
    corridor_ids: list[str]
    timelines: list[IntersectionTimeline] = field(default_factory=list)
    green_band_start: float = 0.0
    green_band_end: float = 0.0
    green_band_width: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction.value,
            "corridor_ids": self.corridor_ids,
            "timelines": [t.to_dict() for t in self.timelines],
            "green_band": {
                "start": self.green_band_start,
                "end": self.green_band_end,
                "width": self.green_band_width,
            },
        }


class GreenWaveVisualizer:
    """
    Generates green wave visualization data.

    Creates timeline diagrams showing how signal phases are offset
    along a corridor to create a "green wave" for platoons of vehicles.

    Usage:
        viz = GreenWaveVisualizer()
        data = viz.generate(intersection_states, graph, direction="EW")
    """

    def generate(
        self,
        intersection_states: dict[str, dict[str, Any]],
        grid_layout: dict[str, tuple[int, int]],
        direction: CorridorDirection = CorridorDirection.EW,
        cycle_length: float = 60.0,
        ns_green: float = 30.0,
        ew_green: float = 30.0,
        yellow: float = 4.0,
        all_red: float = 2.0,
    ) -> GreenWaveData:
        """
        Generate green wave visualization data for a corridor.

        Args:
            intersection_states: Current state of each intersection
            grid_layout: Grid positions (row, col) for each intersection
            direction: Corridor direction (NS or EW)
            cycle_length: Full signal cycle length in seconds
            ns_green: Green duration for NS direction
            ew_green: Green duration for EW direction
            yellow: Yellow duration
            all_red: All-red clearance duration

        Returns:
            GreenWaveData with timelines and green band info
        """
        # Get corridor intersections in order
        corridor_ids = self._get_corridor_ids(grid_layout, direction)

        if not corridor_ids:
            return GreenWaveData(
                direction=direction, corridor_ids=[]
            )

        # Generate timelines for each intersection
        timelines = []
        for i, ix_id in enumerate(corridor_ids):
            row, col = grid_layout[ix_id]
            state = intersection_states.get(ix_id, {})

            # Calculate offset based on position in corridor
            offset = self._calculate_offset(
                i, direction, cycle_length, ns_green, ew_green
            )

            # Generate phase slots
            phases = self._generate_phases(
                cycle_length, ns_green, ew_green, yellow, all_red, offset
            )

            timelines.append(IntersectionTimeline(
                intersection_id=ix_id,
                row=row,
                col=col,
                offset=offset,
                cycle_length=cycle_length,
                phases=phases,
            ))

        # Calculate green band
        green_band = self._calculate_green_band(
            timelines, direction, cycle_length, ns_green, ew_green
        )

        return GreenWaveData(
            direction=direction,
            corridor_ids=corridor_ids,
            timelines=timelines,
            green_band_start=green_band[0],
            green_band_end=green_band[1],
            green_band_width=green_band[2],
        )

    def _get_corridor_ids(
        self,
        grid_layout: dict[str, tuple[int, int]],
        direction: CorridorDirection,
    ) -> list[str]:
        """Get intersection IDs along a corridor in order."""
        if not grid_layout:
            return []

        if direction == CorridorDirection.EW:
            # Group by row, take middle row
            rows: dict[int, list[tuple[int, str]]] = {}
            for ix_id, (row, col) in grid_layout.items():
                rows.setdefault(row, []).append((col, ix_id))

            if not rows:
                return []

            # Use the row with the most intersections
            best_row = max(rows.keys(), key=lambda r: len(rows[r]))
            return [ix_id for col, ix_id in sorted(rows[best_row])]
        else:
            # Group by col, take middle col
            cols: dict[int, list[tuple[int, str]]] = {}
            for ix_id, (row, col) in grid_layout.items():
                cols.setdefault(col, []).append((row, ix_id))

            if not cols:
                return []

            best_col = max(cols.keys(), key=lambda c: len(cols[c]))
            return [ix_id for row, ix_id in sorted(cols[best_col])]

    def _calculate_offset(
        self,
        position: int,
        direction: CorridorDirection,
        cycle_length: float,
        ns_green: float,
        ew_green: float,
    ) -> float:
        """Calculate phase offset for green wave effect."""
        # Travel time between intersections (assuming 40 km/h, 200m spacing)
        travel_time = 18.0  # seconds

        # Offset increases with position along corridor
        offset = position * travel_time

        # Wrap to cycle length
        return offset % cycle_length

    def _generate_phases(
        self,
        cycle_length: float,
        ns_green: float,
        ew_green: float,
        yellow: float,
        all_red: float,
        offset: float,
    ) -> list[SignalPhaseSlot]:
        """Generate phase slots for one cycle."""
        phases = []
        t = offset

        # NS green
        phases.append(SignalPhaseSlot(
            start_time=t,
            end_time=t + ns_green,
            phase="GREEN",
            direction="NS",
        ))
        t += ns_green

        # NS yellow
        phases.append(SignalPhaseSlot(
            start_time=t,
            end_time=t + yellow,
            phase="YELLOW",
            direction="NS",
        ))
        t += yellow

        # All red
        phases.append(SignalPhaseSlot(
            start_time=t,
            end_time=t + all_red,
            phase="RED",
            direction="ALL",
        ))
        t += all_red

        # EW green
        phases.append(SignalPhaseSlot(
            start_time=t,
            end_time=t + ew_green,
            phase="GREEN",
            direction="EW",
        ))
        t += ew_green

        # EW yellow
        phases.append(SignalPhaseSlot(
            start_time=t,
            end_time=t + yellow,
            phase="YELLOW",
            direction="EW",
        ))
        t += yellow

        # All red
        phases.append(SignalPhaseSlot(
            start_time=t,
            end_time=t + all_red,
            phase="RED",
            direction="ALL",
        ))

        return phases

    def _calculate_green_band(
        self,
        timelines: list[IntersectionTimeline],
        direction: CorridorDirection,
        cycle_length: float,
        ns_green: float,
        ew_green: float,
    ) -> tuple[float, float, float]:
        """Calculate the green band (time window where all intersections are green)."""
        if not timelines:
            return (0.0, 0.0, 0.0)

        # Find the green windows for each intersection
        green_windows = []
        for tl in timelines:
            for phase in tl.phases:
                if phase.phase == "GREEN" and phase.direction == direction.value:
                    green_windows.append((phase.start_time, phase.end_time))
                    break

        if not green_windows:
            return (0.0, 0.0, 0.0)

        # Green band is the intersection of all green windows
        band_start = max(w[0] for w in green_windows)
        band_end = min(w[1] for w in green_windows)
        band_width = max(0.0, band_end - band_start)

        return (band_start, band_end, band_width)
