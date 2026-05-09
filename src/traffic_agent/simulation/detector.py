"""
Detector Model — Simulate traffic detection sensors at intersections.

Models vehicle detectors, pedestrian push-buttons, and bicycle detectors
that provide real-time data to the LLM decision pipeline.

Supports:
- Simulating detector data from a list of vehicles
- Loading real detector data from CSV/JSON for replay
- Computing traffic trends over a sliding window
"""

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional


@dataclass
class DetectorReading:
    """Single direction's detector reading."""
    vehicles: int = 0
    pedestrians: int = 0
    bicycles: int = 0

    @property
    def total(self) -> int:
        return self.vehicles + self.pedestrians + self.bicycles

    def to_dict(self) -> Dict[str, int]:
        return {
            "vehicles": self.vehicles,
            "pedestrians": self.pedestrians,
            "bicycles": self.bicycles,
        }


@dataclass
class DetectorData:
    """Complete detector data for an intersection at a point in time."""
    intersection_id: str
    timestamp: float
    readings: Dict[str, DetectorReading]  # "north", "south", "east", "west"

    @property
    def total_vehicles(self) -> int:
        return sum(r.vehicles for r in self.readings.values())

    @property
    def total_pedestrians(self) -> int:
        return sum(r.pedestrians for r in self.readings.values())

    @property
    def total_bicycles(self) -> int:
        return sum(r.bicycles for r in self.readings.values())

    def get_ns_queue(self) -> int:
        """Get combined north-south vehicle queue."""
        return (
            self.readings.get("north", DetectorReading()).vehicles
            + self.readings.get("south", DetectorReading()).vehicles
        )

    def get_ew_queue(self) -> int:
        """Get combined east-west vehicle queue."""
        return (
            self.readings.get("east", DetectorReading()).vehicles
            + self.readings.get("west", DetectorReading()).vehicles
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intersection_id": self.intersection_id,
            "timestamp": round(self.timestamp, 1),
            "readings": {k: v.to_dict() for k, v in self.readings.items()},
            "total_vehicles": self.total_vehicles,
            "total_pedestrians": self.total_pedestrians,
            "total_bicycles": self.total_bicycles,
        }


class DetectorSimulator:
    """
    Generates detector data from simulation state.

    In a real system, this would read from physical sensors.
    In simulation, it counts vehicles waiting at each approach.
    """

    DIRECTIONS = ["north", "east", "south", "west"]

    def read_from_simulation(
        self,
        intersection_id: str,
        timestamp: float,
        vehicles_by_approach: Dict[int, list],
        pedestrian_count: int = 0,
        bicycle_count: int = 0,
    ) -> DetectorData:
        """
        Generate detector data from simulation vehicles.

        Args:
            intersection_id: ID of the intersection
            timestamp: current simulation time
            vehicles_by_approach: {approach: [vehicle_list]}
            pedestrian_count: total pedestrians waiting (split evenly)
            bicycle_count: total bicycles waiting (split evenly)
        """
        readings = {}
        ped_per_dir = pedestrian_count // 4
        bike_per_dir = bicycle_count // 4

        for i, direction in enumerate(self.DIRECTIONS):
            vehicle_count = len(vehicles_by_approach.get(i, []))
            # Add some pedestrians/bicycles to the first two directions for realism
            ped = ped_per_dir + (1 if i < 2 and pedestrian_count > 0 else 0)
            bike = bike_per_dir + (1 if i < 1 and bicycle_count > 0 else 0)
            readings[direction] = DetectorReading(
                vehicles=vehicle_count,
                pedestrians=ped,
                bicycles=bike,
            )

        return DetectorData(
            intersection_id=intersection_id,
            timestamp=timestamp,
            readings=readings,
        )

    def read_from_complex_intersection(
        self,
        intersection_id: str,
        timestamp: float,
        lanes: Dict[int, Dict[str, Any]],
        pedestrian_waits: int = 0,
    ) -> DetectorData:
        """
        Generate detector data from ComplexIntersection's lane structure.

        Args:
            intersection_id: ID of the intersection
            timestamp: current simulation time
            lanes: {approach: {lane_type: Lane}}
            pedestrian_waits: number of pedestrians waiting
        """
        readings = {}
        ped_per_dir = pedestrian_waits // 4

        for i, direction in enumerate(self.DIRECTIONS):
            vehicle_count = sum(
                lanes.get(i, {}).get(lt, type("", (), {"queue": 0})()).queue
                for lt in ["left", "through", "right"]
            )
            readings[direction] = DetectorReading(
                vehicles=vehicle_count,
                pedestrians=ped_per_dir + (1 if i < 2 and pedestrian_waits > 0 else 0),
                bicycles=0,
            )

        return DetectorData(
            intersection_id=intersection_id,
            timestamp=timestamp,
            readings=readings,
        )


class TrendAnalyzer:
    """
    Computes traffic volume trends over a sliding window.

    Tracks the number of vehicles detected per cycle (or per N seconds)
    and provides trend data for the LLM.
    """

    def __init__(self, window_size: int = 5):
        """
        Args:
            window_size: number of samples to keep in the trend window
        """
        self.window_size = window_size
        self._history: Dict[str, Deque[int]] = {
            "north": deque(maxlen=window_size),
            "south": deque(maxlen=window_size),
            "east": deque(maxlen=window_size),
            "west": deque(maxlen=window_size),
            "ns_total": deque(maxlen=window_size),
            "ew_total": deque(maxlen=window_size),
        }
        self._current_cycle: Dict[str, int] = {
            "north": 0, "south": 0, "east": 0, "west": 0,
        }
        self._cycle_phase: str = ""

    def update(self, data: DetectorData) -> None:
        """
        Update with new detector data.

        Accumulates readings during green phases and records a sample
        when the phase changes (indicating a new cycle).
        """
        # Detect phase change by checking if NS/EW balance shifted
        ns = data.get_ns_queue()
        ew = data.get_ew_queue()

        for direction in ["north", "south", "east", "west"]:
            reading = data.readings.get(direction, DetectorReading())
            self._current_cycle[direction] += reading.vehicles

        # Record a sample when we have enough accumulation
        # (simplified: record every call, let the window handle smoothing)
        self._history["north"].append(data.readings.get("north", DetectorReading()).vehicles)
        self._history["south"].append(data.readings.get("south", DetectorReading()).vehicles)
        self._history["east"].append(data.readings.get("east", DetectorReading()).vehicles)
        self._history["west"].append(data.readings.get("west", DetectorReading()).vehicles)
        self._history["ns_total"].append(ns)
        self._history["ew_total"].append(ew)

    def get_trend(self) -> Dict[str, List[int]]:
        """Get the current trend data for all directions."""
        return {k: list(v) for k, v in self._history.items()}

    def get_ns_trend(self) -> List[int]:
        """Get north-south combined trend."""
        return list(self._history["ns_total"])

    def get_ew_trend(self) -> List[int]:
        """Get east-west combined trend."""
        return list(self._history["ew_total"])

    def get_direction_trend(self, direction: str) -> List[int]:
        """Get trend for a specific direction."""
        return list(self._history.get(direction, deque()))

    def is_increasing(self, direction: str = "ns_total", threshold: float = 0.3) -> bool:
        """Check if traffic is trending upward for a direction."""
        data = list(self._history.get(direction, deque()))
        if len(data) < 3:
            return False
        recent = data[-3:]
        increases = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i - 1])
        return increases / (len(recent) - 1) >= threshold

    def is_decreasing(self, direction: str = "ns_total", threshold: float = 0.3) -> bool:
        """Check if traffic is trending downward for a direction."""
        data = list(self._history.get(direction, deque()))
        if len(data) < 3:
            return False
        recent = data[-3:]
        decreases = sum(1 for i in range(1, len(recent)) if recent[i] < recent[i - 1])
        return decreases / (len(recent) - 1) >= threshold

    def reset(self) -> None:
        """Reset all trend data."""
        for key in self._history:
            self._history[key].clear()
        for key in self._current_cycle:
            self._current_cycle[key] = 0


class DetectorDataReplay:
    """
    Replay detector data from a JSON/CSV file.

    Useful for testing with real-world detector logs.
    """

    def __init__(self, data: List[Dict[str, Any]]):
        """
        Args:
            data: list of DetectorData dicts, each with timestamp and readings
        """
        self._data = data
        self._index = 0

    @classmethod
    def from_json(cls, path: str) -> "DetectorDataReplay":
        """Load detector data from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "readings" in data:
            data = [data]
        return cls(data)

    @classmethod
    def from_csv(cls, path: str) -> "DetectorDataReplay":
        """
        Load detector data from a CSV file.

        Expected columns: timestamp, north_vehicles, south_vehicles, east_vehicles,
        west_vehicles, north_pedestrians, south_pedestrians, east_pedestrians, west_pedestrians
        """
        import csv

        data = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                readings = {}
                for direction in ["north", "south", "east", "west"]:
                    readings[direction] = DetectorReading(
                        vehicles=int(row.get(f"{direction}_vehicles", 0)),
                        pedestrians=int(row.get(f"{direction}_pedestrians", 0)),
                        bicycles=int(row.get(f"{direction}_bicycles", 0)),
                    )
                data.append({
                    "intersection_id": row.get("intersection_id", "replay"),
                    "timestamp": float(row.get("timestamp", 0)),
                    "readings": readings,
                })
        return cls(data)

    def next(self) -> Optional[DetectorData]:
        """Get the next detector reading."""
        if self._index >= len(self._data):
            return None
        item = self._data[self._index]
        self._index += 1

        readings = {}
        for direction, values in item.get("readings", {}).items():
            if isinstance(values, dict):
                readings[direction] = DetectorReading(**values)
            else:
                readings[direction] = values

        return DetectorData(
            intersection_id=item.get("intersection_id", "replay"),
            timestamp=item.get("timestamp", 0),
            readings=readings,
        )

    def reset(self) -> None:
        """Reset replay to the beginning."""
        self._index = 0

    def __len__(self) -> int:
        return len(self._data)
