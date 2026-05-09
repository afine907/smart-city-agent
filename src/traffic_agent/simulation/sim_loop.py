"""
Simulation Loop — End-to-end timing adjustment simulation.

Ties together:
- Signal controller (baseline timing + adjustment)
- Detector simulator (traffic detection)
- Decision pipeline (rules → cache → LLM)
- Vehicle generation and movement
- Metrics collection

This is the main entry point for running a single-intersection
simulation with AI-assisted timing adjustment.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from traffic_agent.llm.parser import TimingAdjustment
from traffic_agent.simulation.detector import DetectorData, DetectorReading, DetectorSimulator, TrendAnalyzer
from traffic_agent.simulation.signal_controller import (
    SignalController,
    SignalState,
    crossroad_plan,
    tjunction_plan,
)
from traffic_agent.simulation.scenarios import TrafficScenario, get_scenario


@dataclass
class StepResult:
    """Result of a single simulation step."""
    step: int
    timestamp: float
    signal_state: Dict
    detector_data: Dict
    adjustment: Optional[Dict] = None
    vehicles_generated: int = 0
    vehicles_completed: int = 0
    queue_sizes: Dict[str, int] = field(default_factory=dict)


@dataclass
class SimulationReport:
    """Final report from a simulation run."""
    total_steps: int
    total_time: float
    total_vehicles_generated: int
    total_vehicles_completed: int
    avg_wait_time: float
    max_wait_time: float
    throughput: float
    adjustments_made: int
    llm_adjustments: int
    rule_adjustments: int
    zero_adjustments: int
    pipeline_stats: Dict
    adjustment_log: List[Dict]


class TimingSimulation:
    """
    Single-intersection timing adjustment simulation.

    Combines a signal controller, detector simulator, and decision pipeline
    to simulate traffic flow with AI-assisted signal timing.

    Usage:
        sim = TimingSimulation(
            intersection_type="crossroad",
            scenario_name="morning_peak",
            pipeline=pipeline,  # optional, for LLM decisions
        )
        report = sim.run(steps=500)
    """

    def __init__(
        self,
        intersection_type: str = "crossroad",
        scenario_name: str = "normal",
        pipeline=None,
        seed: Optional[int] = None,
        ns_green: Optional[float] = None,
        ew_green: Optional[float] = None,
    ):
        """
        Args:
            intersection_type: "crossroad" or "tjunction"
            scenario_name: name of the traffic scenario
            pipeline: TimingDecisionPipeline instance (None = fixed timing only)
            seed: random seed for reproducibility
            ns_green: override NS green duration
            ew_green: override EW green duration
        """
        self.intersection_type = intersection_type
        self.pipeline = pipeline
        self.seed = seed

        if seed is not None:
            np.random.seed(seed)

        # Create signal plan
        if intersection_type == "tjunction":
            self.plan = tjunction_plan(
                ns_green=ns_green or 45.0,
                ew_green=ew_green or 35.0,
            )
        else:
            self.plan = crossroad_plan(
                ns_green=ns_green or 60.0,
                ew_green=ew_green or 90.0,
            )

        self.controller = SignalController(self.plan)
        self.detector = DetectorSimulator()
        self.trend = TrendAnalyzer(window_size=5)
        self.scenario = get_scenario(scenario_name, intersection_type)

        # Vehicle tracking
        self._vehicles: Dict[str, List[Dict]] = {
            "north": [], "south": [], "east": [], "west": []
        }
        self._approach_map = {0: "north", 1: "east", 2: "south", 3: "west"}
        self._vehicle_counter = 0
        self._total_generated = 0
        self._total_completed = 0
        self._total_wait_time = 0.0

        # Adjustment tracking
        self._adjustment_log: List[Dict] = []
        self._recent_adjustments: List[Dict] = []

        # Step tracking
        self._step = 0
        self._time = 0.0

    def step(self) -> StepResult:
        """Advance simulation by one step (1 second)."""
        self._step += 1
        self._time += 1.0

        # 1. Get current traffic phase from scenario
        traffic_phase = self.scenario.get_phase_at_step(self._step)
        if traffic_phase is None:
            traffic_phase = self.scenario.phases[-1]

        # 2. Generate vehicles
        generated = self._generate_vehicles(traffic_phase)

        # 3. Update detector
        detector_data = self.detector.read_from_simulation(
            intersection_id="ix_1",
            timestamp=self._time,
            vehicles_by_approach={i: self._vehicles[d] for i, d in self._approach_map.items()},
        )

        # 4. Update trend
        self.trend.update(detector_data)

        # 5. Get signal state
        signal_state = self.controller.get_state()

        # 6. Decide adjustment (only during green phases, once per green phase)
        adjustment = None
        if self.controller.is_green and signal_state.phase_remaining > 15:
            adjustment = self._decide_adjustment(detector_data, signal_state)

        # 7. Advance signal
        self.controller.step(1.0)

        # 8. Process vehicles (complete if green, wait if red)
        completed = self._process_vehicles()

        # 9. Collect queue sizes
        queue_sizes = {
            d: len(vehicles) for d, vehicles in self._vehicles.items()
        }

        return StepResult(
            step=self._step,
            timestamp=self._time,
            signal_state=signal_state.to_dict(),
            detector_data=detector_data.to_dict(),
            adjustment=adjustment.to_dict() if adjustment else None,
            vehicles_generated=generated,
            vehicles_completed=completed,
            queue_sizes=queue_sizes,
        )

    def run(self, steps: int = 500, verbose: bool = False) -> SimulationReport:
        """
        Run the simulation for a given number of steps.

        Args:
            steps: number of simulation steps
            verbose: print progress every 50 steps

        Returns:
            SimulationReport with final metrics
        """
        for i in range(steps):
            result = self.step()
            if verbose and (i + 1) % 50 == 0:
                self._print_progress(result)

        return self._generate_report()

    def _decide_adjustment(
        self,
        detector_data: DetectorData,
        signal_state: SignalState,
    ) -> Optional[TimingAdjustment]:
        """Decide whether to adjust the current green phase."""
        if self.pipeline is None:
            return None

        adjustment = self.pipeline.decide(
            detector_data=detector_data.to_dict(),
            signal_state=signal_state.to_dict(),
            trend=self.trend.get_trend(),
            intersection_id="ix_1",
            intersection_type=self.intersection_type,
        )

        # Apply non-zero adjustments
        if adjustment.adjustment != 0:
            applied = self.controller.apply_adjustment(adjustment.adjustment)
            if applied:
                self._adjustment_log.append({
                    "step": self._step,
                    "phase": signal_state.current_phase,
                    "adjustment": adjustment.adjustment,
                    "reason": adjustment.reasoning,
                    "source": adjustment.source,
                    "confidence": adjustment.confidence,
                })
                self._recent_adjustments.append({
                    "phase": signal_state.current_phase,
                    "adjustment": adjustment.adjustment,
                    "reason": adjustment.reasoning,
                })
                if len(self._recent_adjustments) > 5:
                    self._recent_adjustments = self._recent_adjustments[-5:]

        return adjustment

    def _generate_vehicles(self, traffic_phase) -> int:
        """Generate vehicles based on traffic phase parameters."""
        generated = 0

        for approach_idx, direction in self._approach_map.items():
            rate = traffic_phase.get_arrival_rate(direction)
            if np.random.random() < rate:
                self._vehicle_counter += 1
                self._total_generated += 1
                generated += 1
                self._vehicles[direction].append({
                    "id": f"v_{self._vehicle_counter}",
                    "approach": approach_idx,
                    "entry_time": self._time,
                    "waiting": False,
                })

            # Pedestrians
            if np.random.random() < traffic_phase.pedestrian_rate:
                self._vehicle_counter += 1
                self._vehicles[direction].append({
                    "id": f"ped_{self._vehicle_counter}",
                    "approach": approach_idx,
                    "entry_time": self._time,
                    "waiting": False,
                    "is_pedestrian": True,
                })

            # Bicycles
            if np.random.random() < traffic_phase.bicycle_rate:
                self._vehicle_counter += 1
                self._vehicles[direction].append({
                    "id": f"bike_{self._vehicle_counter}",
                    "approach": approach_idx,
                    "entry_time": self._time,
                    "waiting": False,
                    "is_bicycle": True,
                })

        return generated

    def _process_vehicles(self) -> int:
        """Process vehicles: complete if green, wait if red."""
        completed = 0

        for approach_idx, direction in self._approach_map.items():
            has_green = self.controller.has_green_for(approach_idx)
            to_remove = []

            for i, v in enumerate(self._vehicles[direction]):
                if has_green:
                    # Vehicle passes through
                    wait = self._time - v["entry_time"]
                    self._total_wait_time += wait
                    self._total_completed += 1
                    completed += 1
                    to_remove.append(i)
                else:
                    v["waiting"] = True

            # Remove completed vehicles (reverse order)
            for i in sorted(to_remove, reverse=True):
                self._vehicles[direction].pop(i)

        return completed

    def _generate_report(self) -> SimulationReport:
        """Generate final simulation report."""
        pipeline_stats = {}
        if self.pipeline:
            pipeline_stats = self.pipeline.get_stats()

        llm_count = sum(1 for a in self._adjustment_log if a["source"] == "llm")
        rule_count = sum(1 for a in self._adjustment_log if a["source"] == "rule")
        zero_count = sum(1 for a in self._adjustment_log if a["adjustment"] == 0)

        avg_wait = self._total_wait_time / max(1, self._total_completed)
        max_wait = 0.0
        if self._total_completed > 0:
            # Estimate max wait from adjustment log
            max_wait = max((abs(a["adjustment"]) * 2 for a in self._adjustment_log), default=0.0)

        return SimulationReport(
            total_steps=self._step,
            total_time=self._time,
            total_vehicles_generated=self._total_generated,
            total_vehicles_completed=self._total_completed,
            avg_wait_time=avg_wait,
            max_wait_time=max_wait,
            throughput=self._total_completed / max(1, self._time),
            adjustments_made=len(self._adjustment_log),
            llm_adjustments=llm_count,
            rule_adjustments=rule_count,
            zero_adjustments=zero_count,
            pipeline_stats=pipeline_stats,
            adjustment_log=self._adjustment_log,
        )

    def _print_progress(self, result: StepResult):
        """Print simulation progress."""
        queues = result.queue_sizes
        total_q = sum(queues.values())
        adj = result.adjustment
        adj_str = f"adj={adj['adjustment']:+d}" if adj else "no-adj"
        print(
            f"Step {result.step:4d} | "
            f"Phase: {result.signal_state['current_phase']:12s} | "
            f"Queue: N={queues.get('north',0):2d} S={queues.get('south',0):2d} "
            f"E={queues.get('east',0):2d} W={queues.get('west',0):2d} "
            f"Total={total_q:3d} | "
            f"Gen={result.vehicles_generated} Compl={result.vehicles_completed} | "
            f"{adj_str}"
        )

    def export_log(self, path: str) -> None:
        """Export adjustment log to JSON file."""
        log_data = {
            "intersection_type": self.intersection_type,
            "scenario": self.scenario.name,
            "total_steps": self._step,
            "adjustments": self._adjustment_log,
            "pipeline_stats": self.pipeline.get_stats() if self.pipeline else {},
        }
        Path(path).write_text(json.dumps(log_data, ensure_ascii=False, indent=2), encoding="utf-8")
