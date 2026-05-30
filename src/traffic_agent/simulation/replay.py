"""
Signal Replay — Record and replay signal timing decisions.

Records all signal timing decisions during a simulation run,
then allows replaying them for analysis and visualization.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TimingRecord:
    """A single timing decision record."""

    step: int
    timestamp: float
    phase: str
    phase_duration: float
    base_duration: float
    adjustment: float
    reasoning: str
    layer: str  # "rule", "cache", "llm", "fixed"
    queue_north: int = 0
    queue_south: int = 0
    queue_east: int = 0
    queue_west: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "timestamp": self.timestamp,
            "phase": self.phase,
            "phase_duration": self.phase_duration,
            "base_duration": self.base_duration,
            "adjustment": self.adjustment,
            "reasoning": self.reasoning,
            "layer": self.layer,
            "queues": {
                "north": self.queue_north,
                "south": self.queue_south,
                "east": self.queue_east,
                "west": self.queue_west,
            },
        }


@dataclass
class ReplayData:
    """Complete replay data for a simulation run."""

    intersection_id: str
    intersection_type: str
    scenario: str
    total_steps: int
    records: list[TimingRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intersection_id": self.intersection_id,
            "intersection_type": self.intersection_type,
            "scenario": self.scenario,
            "total_steps": self.total_steps,
            "total_records": len(self.records),
            "records": [r.to_dict() for r in self.records],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> ReplayData:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        records = [
            TimingRecord(
                step=r["step"],
                timestamp=r["timestamp"],
                phase=r["phase"],
                phase_duration=r["phase_duration"],
                base_duration=r["base_duration"],
                adjustment=r["adjustment"],
                reasoning=r["reasoning"],
                layer=r["layer"],
                queue_north=r["queues"]["north"],
                queue_south=r["queues"]["south"],
                queue_east=r["queues"]["east"],
                queue_west=r["queues"]["west"],
            )
            for r in data["records"]
        ]
        return cls(
            intersection_id=data["intersection_id"],
            intersection_type=data["intersection_type"],
            scenario=data["scenario"],
            total_steps=data["total_steps"],
            records=records,
        )

    def get_adjustments(self) -> list[TimingRecord]:
        """Get only records with non-zero adjustments."""
        return [r for r in self.records if r.adjustment != 0]

    def get_by_layer(self, layer: str) -> list[TimingRecord]:
        """Get records by decision layer."""
        return [r for r in self.records if r.layer == layer]

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics."""
        if not self.records:
            return {}

        adjustments = [r.adjustment for r in self.records]
        return {
            "total_records": len(self.records),
            "total_adjustments": len([a for a in adjustments if a != 0]),
            "avg_adjustment": sum(adjustments) / len(adjustments),
            "max_adjustment": max(adjustments),
            "min_adjustment": min(adjustments),
            "by_layer": {
                layer: len(self.get_by_layer(layer))
                for layer in ["fixed", "rule", "cache", "llm"]
            },
        }


class ReplayRecorder:
    """Records timing decisions during simulation."""

    def __init__(
        self,
        intersection_id: str = "center",
        intersection_type: str = "crossroad",
        scenario: str = "normal",
    ):
        self.data = ReplayData(
            intersection_id=intersection_id,
            intersection_type=intersection_type,
            scenario=scenario,
            total_steps=0,
        )

    def record(
        self,
        step: int,
        timestamp: float,
        phase: str,
        phase_duration: float,
        base_duration: float,
        adjustment: float,
        reasoning: str,
        layer: str,
        queues: dict[str, int] | None = None,
    ) -> None:
        """Record a timing decision."""
        queues = queues or {}
        record = TimingRecord(
            step=step,
            timestamp=timestamp,
            phase=phase,
            phase_duration=phase_duration,
            base_duration=base_duration,
            adjustment=adjustment,
            reasoning=reasoning,
            layer=layer,
            queue_north=queues.get("north", 0),
            queue_south=queues.get("south", 0),
            queue_east=queues.get("east", 0),
            queue_west=queues.get("west", 0),
        )
        self.data.records.append(record)

    def finish(self, total_steps: int) -> ReplayData:
        """Mark recording as complete."""
        self.data.total_steps = total_steps
        return self.data
