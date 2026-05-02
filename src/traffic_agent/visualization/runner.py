"""
Simulation Runner — Ties GridSimulation + EventCollector for SSE visualization.
"""

import time

from traffic_agent.simulation.engine import SimulationConfig
from traffic_agent.simulation.grid import GridSimulation
from traffic_agent.visualization.events import EventCollector, EventType, SSEEvent


class SimulationRunner:
    """Runs GridSimulation with SSE event emission."""

    def __init__(
        self,
        config: SimulationConfig | None = None,
        collector: EventCollector | None = None,
    ):
        self.config = config or SimulationConfig()
        self.collector = collector or EventCollector()
        self.simulation: GridSimulation | None = None
        self._running = False

    def setup(self) -> None:
        """Initialize the simulation."""
        self.simulation = GridSimulation(config=self.config)
        self.collector.emit(
            SSEEvent(
                event_type=EventType.SIMULATION_START,
                agent_id="system",
                timestamp=time.time(),
                data={"grid_size": "3x3", "config": {"max_steps": self.config.max_steps}},
            )
        )

    def step(self) -> float:
        """Run one simulation step with event emission. Returns duration in ms."""
        if not self.simulation:
            raise RuntimeError("Simulation not setup. Call setup() first.")

        # Emit thinking events
        for ix_id in self.simulation.intersections:
            self.collector.emit_thinking(
                agent_id=ix_id,
                thought=f"Analyzing traffic at {ix_id}",
                context={"time": self.simulation.time},
            )

        # Run step
        start = time.time()
        self.simulation.step()
        duration_ms = (time.time() - start) * 1000

        # Emit decision events
        n_intersections = len(self.simulation.intersections)
        for ix_id in self.simulation.intersections:
            ix = self.simulation.intersections[ix_id]
            self.collector.emit_decision(
                agent_id=ix_id,
                decision={"phase": ix.current_phase, "time": self.simulation.time},
                duration_ms=duration_ms / max(n_intersections, 1),
            )

        return duration_ms

    def run(self, steps: int = 50) -> None:
        """Run multiple steps."""
        if not self.simulation:
            self.setup()

        self._running = True
        for _i in range(steps):
            if not self._running:
                break
            self.step()

        self.collector.emit(
            SSEEvent(
                event_type=EventType.SIMULATION_END,
                agent_id="system",
                timestamp=time.time(),
                data=self.collector.get_metrics(),
            )
        )
        self._running = False

    def stop(self) -> None:
        """Stop the simulation."""
        self._running = False

    @property
    def metrics(self) -> dict:
        """Get current metrics."""
        return self.collector.get_metrics()
