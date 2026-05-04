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
_network_topology: dict = {}  # Current network topology for dashboard


def get_collector() -> EventCollector:
    """Get the global event collector."""
    return _collector


def _get_vis_dir() -> Path:
    """Resolve the visualization directory."""
    vis_dir = Path(__file__).parent.parent / "visualization"
    if not vis_dir.exists():
        vis_dir = Path(__file__).parent.parent.parent / "visualization"
    return vis_dir


def _serve_html(filename: str, title: str = "Dashboard") -> HTMLResponse:
    """Serve an HTML file from the visualization directory."""
    path = _get_vis_dir() / filename
    if path.exists():
        return HTMLResponse(content=path.read_text(encoding="utf-8"))
    return HTMLResponse(content=f"<h1>{title} not found</h1>", status_code=404)


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the Tesla-style intersection dashboard."""
    return _serve_html("dashboard_tesla.html", "Dashboard")


@app.get("/dashboard/canvas", response_class=HTMLResponse)
async def serve_dashboard_canvas():
    """Serve the Canvas 2D dashboard."""
    return _serve_html("dashboard_canvas.html", "Canvas Dashboard")


@app.get("/dashboard/3d", response_class=HTMLResponse)
async def serve_dashboard_3d():
    """Serve the legacy 3D dashboard."""
    return _serve_html("dashboard_3d.html", "3D Dashboard")


@app.get("/dashboard/classic", response_class=HTMLResponse)
async def serve_dashboard_classic():
    """Serve the classic SVG dashboard."""
    return _serve_html("dashboard.html", "Classic Dashboard")


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
async def start_simulation(steps: int = 50, speed: float = 1.0, preset: str | None = None):
    """Start a simulation run."""
    global _simulation_running, _simulation_task

    if _simulation_running:
        return JSONResponse({"error": "Simulation already running"}, status_code=409)

    _simulation_running = True
    _collector.clear()

    _simulation_task = asyncio.create_task(_run_simulation(steps, speed, preset))
    return {"status": "started", "steps": steps, "speed": speed, "preset": preset}


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


@app.get("/api/network")
async def get_network():
    """Get current network topology for dashboard rendering."""
    return _network_topology


async def _run_simulation(steps: int, speed: float, preset: str | None = None):
    """Run simulation with event emission."""
    global _simulation_running, _network_topology

    try:
        from traffic_agent.simulation.engine import SimulationConfig

        config = SimulationConfig(max_steps=steps * 10)

        # Auto-detect from existing topology if no preset specified
        if not preset and _network_topology.get("type", "").startswith("osm_"):
            preset = _network_topology["type"].replace("osm_", "")

        if preset:
            from traffic_agent.simulation.osm_sim import OSMSimulation

            sim = OSMSimulation.from_preset(preset, config)
            net_type = f"osm_{preset}"
        else:
            from traffic_agent.simulation.grid import GridSimulation

            sim = GridSimulation(config=config)
            net_type = "grid_3x3"

        # Export network topology for dashboard
        if hasattr(sim, "intersections") and hasattr(sim, "segments"):
            # OSM simulation
            osm_ix = sim.osm.intersections
            _network_topology = {
                "type": net_type,
                "intersections": {
                    ix_id: {
                        "lat": osm_ix[ix_id].lat if ix_id in osm_ix else 0,
                        "lon": osm_ix[ix_id].lon if ix_id in osm_ix else 0,
                        "neighbors": sim.get_neighbors(ix_id),
                    }
                    for ix_id in sim.intersections
                },
                "segments": {
                    seg_id: {
                        "from": seg.from_id,
                        "to": seg.to_id,
                        "length": seg.length,
                        "name": seg.name,
                    }
                    for seg_id, seg in sim.segments.items()
                    if not seg_id.startswith("virtual_")
                },
            }
        else:
            # Grid simulation
            _network_topology = {
                "type": net_type,
                "intersections": {
                    ix_id: {"row": int(ix_id.split("_")[1]), "col": int(ix_id.split("_")[2])}
                    for ix_id in sim.intersections
                },
                "segments": {},
            }

        _collector.emit(
            SSEEvent(
                event_type=EventType.SIMULATION_START,
                agent_id="system",
                timestamp=time.time(),
                data={"steps": steps, "network": net_type},
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
