"""
Traffic Heatmap — generates heatmap data for traffic flow visualization.

Converts simulation state into a 2D grid of traffic density values
suitable for rendering as a heatmap overlay on the dashboard.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HeatmapMetric(str, Enum):
    """Metrics that can be visualized as a heatmap."""
    QUEUE_LENGTH = "queue_length"
    WAIT_TIME = "wait_time"
    VEHICLE_COUNT = "vehicle_count"
    CONGESTION = "congestion"


@dataclass
class HeatmapCell:
    """A single cell in the heatmap grid."""
    row: int
    col: int
    value: float
    normalized: float = 0.0  # 0.0 to 1.0


@dataclass
class HeatmapData:
    """Complete heatmap data for visualization."""
    metric: HeatmapMetric
    rows: int
    cols: int
    cells: list[list[HeatmapCell]] = field(default_factory=list)
    min_value: float = 0.0
    max_value: float = 0.0
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "metric": self.metric.value,
            "rows": self.rows,
            "cols": self.cols,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "timestamp": self.timestamp,
            "grid": [
                [cell.normalized for cell in row]
                for row in self.cells
            ],
        }


class HeatmapGenerator:
    """
    Generates heatmap data from simulation state.

    Maps intersection queue lengths, wait times, or vehicle counts
    onto a 2D grid for color-coded visualization.

    Usage:
        generator = HeatmapGenerator()
        heatmap = generator.generate(states, metric="queue_length")
    """

    # Color stops for heatmap rendering (green → yellow → red)
    COLOR_STOPS = [
        (0.0, (0, 200, 0)),     # Green: low traffic
        (0.5, (255, 255, 0)),   # Yellow: moderate
        (1.0, (255, 0, 0)),     # Red: heavy traffic
    ]

    def generate(
        self,
        intersection_states: dict[str, dict[str, Any]],
        grid_layout: dict[str, tuple[int, int]],
        metric: HeatmapMetric = HeatmapMetric.QUEUE_LENGTH,
        timestamp: float = 0.0,
    ) -> HeatmapData:
        """
        Generate heatmap data from intersection states.

        Args:
            intersection_states: Dict of intersection_id → state data
            grid_layout: Dict of intersection_id → (row, col) position
            metric: Which metric to visualize
            timestamp: Simulation timestamp

        Returns:
            HeatmapData with normalized values for rendering
        """
        if not grid_layout:
            return HeatmapData(
                metric=metric, rows=0, cols=0, timestamp=timestamp
            )

        # Determine grid dimensions
        max_row = max(pos[0] for pos in grid_layout.values()) + 1
        max_col = max(pos[1] for pos in grid_layout.values()) + 1

        # Initialize grid with zeros
        grid = [[0.0] * max_col for _ in range(max_row)]

        # Fill grid with metric values
        for ix_id, (row, col) in grid_layout.items():
            if ix_id in intersection_states:
                state = intersection_states[ix_id]
                grid[row][col] = self._extract_metric(state, metric)

        # Find min/max for normalization
        all_values = [v for row in grid for v in row]
        min_val = min(all_values) if all_values else 0.0
        max_val = max(all_values) if all_values else 1.0
        value_range = max_val - min_val if max_val > min_val else 1.0

        # Build cells with normalized values
        cells = []
        for r in range(max_row):
            row_cells = []
            for c in range(max_col):
                value = grid[r][c]
                normalized = (value - min_val) / value_range
                row_cells.append(HeatmapCell(
                    row=r, col=c, value=value, normalized=normalized
                ))
            cells.append(row_cells)

        return HeatmapData(
            metric=metric,
            rows=max_row,
            cols=max_col,
            cells=cells,
            min_value=min_val,
            max_value=max_val,
            timestamp=timestamp,
        )

    def _extract_metric(self, state: dict[str, Any], metric: HeatmapMetric) -> float:
        """Extract the specified metric value from intersection state."""
        if metric == HeatmapMetric.QUEUE_LENGTH:
            return (
                state.get("queue_north", 0)
                + state.get("queue_south", 0)
                + state.get("queue_east", 0)
                + state.get("queue_west", 0)
            )
        elif metric == HeatmapMetric.WAIT_TIME:
            return state.get("avg_wait_time", 0.0)
        elif metric == HeatmapMetric.VEHICLE_COUNT:
            return state.get("vehicle_count", 0)
        elif metric == HeatmapMetric.CONGESTION:
            # Congestion = queue / capacity (normalized 0-1)
            queue = (
                state.get("queue_north", 0)
                + state.get("queue_south", 0)
                + state.get("queue_east", 0)
                + state.get("queue_west", 0)
            )
            capacity = state.get("max_capacity", 40)  # default 10 per direction
            return min(1.0, queue / max(1, capacity))
        return 0.0

    @staticmethod
    def value_to_color(normalized: float) -> tuple[int, int, int]:
        """Convert a normalized value (0-1) to an RGB color using gradient."""
        normalized = max(0.0, min(1.0, normalized))

        # Find the two color stops to interpolate between
        stops = HeatmapGenerator.COLOR_STOPS
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= normalized <= t1:
                # Linear interpolation
                ratio = (normalized - t0) / (t1 - t0) if t1 > t0 else 0
                r = int(c0[0] + (c1[0] - c0[0]) * ratio)
                g = int(c0[1] + (c1[1] - c0[1]) * ratio)
                b = int(c0[2] + (c1[2] - c0[2]) * ratio)
                return (r, g, b)

        # Fallback to last color
        return stops[-1][1]
