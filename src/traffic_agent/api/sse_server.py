"""
SSE API Server — FastAPI server for real-time Agent reasoning visualization.

Provides SSE streaming, simulation control, and dashboard serving.
"""

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from traffic_agent.visualization.events import EventCollector, EventType, SSEEvent

app = FastAPI(title="LLM Traffic Controller — Dashboard", version="0.1.0")

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
_collector = EventCollector()
_simulation_running = False
_simulation_task: asyncio.Task | None = None


def get_collector() -> EventCollector:
    """Get the global event collector."""
    return _collector


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the dashboard HTML page."""
    dashboard_path = Path(__file__).parent.parent.parent / "visualization" / "dashboard.html"
    if not dashboard_path.exists():
        dashboard_path = Path(__file__).parent.parent / "visualization" / "dashboard.html"
    if dashboard_path.exists():
        return HTMLResponse(content=dashboard_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Dashboard not found</h1>", status_code=404)


@app.get("/api/events/stream")
async def event_stream(request: Request):
    """SSE stream endpoint — real-time events."""

    async def generate() -> AsyncGenerator:
        queue: asyncio.Queue = asyncio.Queue()

        def subscriber(event: SSEEvent):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

        _collector.subscribe(subscriber)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {
                        "event": event.event_type.value,
                        "data": json.dumps(event.to_dict()),
                    }
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"event": "keepalive", "data": "{}"}
        finally:
            _collector.unsubscribe(subscriber)

    return EventSourceResponse(generate())


@app.get("/api/events/history")
async def event_history(
    event_type: str | None = None,
    agent_id: str | None = None,
    limit: int = 100,
):
    """Get historical events with optional filtering."""
    et = None
    if event_type:
        try:
            et = EventType(event_type)
        except ValueError:
            return JSONResponse({"error": f"Invalid event type: {event_type}"}, status_code=400)

    events = _collector.get_events(event_type=et, agent_id=agent_id, limit=limit)
    return {"events": [e.to_dict() for e in events], "total": _collector.count}


@app.get("/api/events/metrics")
async def event_metrics():
    """Get aggregated metrics."""
    return _collector.get_metrics()


@app.post("/api/simulation/start")
async def start_simulation(steps: int = 50, speed: float = 1.0):
    """Start a simulation run."""
    global _simulation_running, _simulation_task

    if _simulation_running:
        return JSONResponse({"error": "Simulation already running"}, status_code=409)

    _simulation_running = True
    _collector.clear()

    _simulation_task = asyncio.create_task(_run_simulation(steps, speed))
    return {"status": "started", "steps": steps, "speed": speed}


@app.post("/api/simulation/stop")
async def stop_simulation():
    """Stop the running simulation."""
    global _simulation_running, _simulation_task

    if not _simulation_running:
        return JSONResponse({"error": "No simulation running"}, status_code=409)

    _simulation_running = False
    if _simulation_task:
        _simulation_task.cancel()
        _simulation_task = None

    return {"status": "stopped"}


@app.get("/api/simulation/status")
async def simulation_status():
    """Get current simulation status."""
    return {
        "running": _simulation_running,
        "events_collected": _collector.count,
        "metrics": _collector.get_metrics(),
    }


async def _run_simulation(steps: int, speed: float):
    """Run simulation with event emission."""
    global _simulation_running

    try:
        from traffic_agent.simulation.engine import SimulationConfig
        from traffic_agent.simulation.grid import GridSimulation

        config = SimulationConfig(max_steps=steps * 10)
        sim = GridSimulation(config=config)

        _collector.emit(
            SSEEvent(
                event_type=EventType.SIMULATION_START,
                agent_id="system",
                timestamp=time.time(),
                data={"steps": steps, "grid_size": "3x3"},
            )
        )

        for step in range(steps):
            if not _simulation_running:
                break

            # Emit thinking for each intersection
            for ix_id in sim.intersections:
                _collector.emit_thinking(
                    agent_id=ix_id,
                    thought=f"Step {step}: Analyzing traffic at {ix_id}",
                    context={
                        "step": step,
                        "queue": sim.intersections[ix_id].get_total_queue(),
                    },
                )

            # Simulate step
            start = time.time()
            sim.step()
            duration = (time.time() - start) * 1000

            # Emit decision events
            for ix_id in sim.intersections:
                ix = sim.intersections[ix_id]
                _collector.emit_decision(
                    agent_id=ix_id,
                    decision={"phase": ix.current_phase, "step": step},
                    duration_ms=duration / len(sim.intersections),
                )

            # Emit step metrics
            _collector.emit(
                SSEEvent(
                    event_type=EventType.SIMULATION_STEP,
                    agent_id="system",
                    timestamp=time.time(),
                    data={"step": step, "duration_ms": duration},
                )
            )

            await asyncio.sleep(1.0 / speed)

        _collector.emit(
            SSEEvent(
                event_type=EventType.SIMULATION_END,
                agent_id="system",
                timestamp=time.time(),
                data=_collector.get_metrics(),
            )
        )
    except Exception as e:
        _collector.emit(
            SSEEvent(
                event_type=EventType.SIMULATION_END,
                agent_id="system",
                timestamp=time.time(),
                data={"error": str(e)},
            )
        )
    finally:
        _simulation_running = False
