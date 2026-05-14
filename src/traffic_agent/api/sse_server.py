"""
SSE API Server — FastAPI server for real-time Agent reasoning visualization.

Provides SSE streaming, simulation control, and dashboard serving.
"""

# pysqlite3-binary workaround for ChromaDB (sqlite3 >= 3.35.0 required)
import sys
try:
    sys.modules['sqlite3'] = __import__('pysqlite3')
except ImportError:
    pass

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
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
_network_topology: dict = {}
_crew = None
_sim = None
_sim_state: dict = {}


def get_collector() -> EventCollector:
    """Get the global event collector."""
    return _collector


def _get_vis_dir() -> Path:
    """Resolve the visualization directory."""
    vis_dir = Path(__file__).parent.parent / "visualization"
    if not vis_dir.exists():
        vis_dir = Path(__file__).parent.parent.parent / "visualization"
    return vis_dir


def _get_dashboard_build_dir() -> Path:
    """Resolve the Vite build output directory."""
    return _get_vis_dir() / "dashboard_build"


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the React dashboard (Vite build output)."""
    build_dir = _get_dashboard_build_dir()
    index_path = build_dir / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Dashboard not built. Run: cd dashboard && npm run build</h1>", status_code=404)


# ─── Existing SSE stream (kept for backward compatibility) ────────────


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


# ─── Simulation control ──────────────────────────────────────────────


@app.post("/api/simulation/start")
async def start_simulation(
    steps: int = 50,
    speed: float = 1.0,
    preset: str | None = None,
    mode: str = "local",
):
    """Start a simulation run. mode='local' | 'crewai'."""
    global _simulation_running, _simulation_task

    if _simulation_running:
        return JSONResponse({"error": "Simulation already running"}, status_code=409)

    _simulation_running = True
    _collector.clear()

    if mode == "crewai":
        _simulation_task = asyncio.create_task(_run_crewai_simulation(steps, speed))
    else:
        _simulation_task = asyncio.create_task(_run_simulation(steps, speed, preset))
    return {"status": "started", "steps": steps, "speed": speed, "preset": preset, "mode": mode}


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


@app.get("/api/simulation/state")
async def simulation_state():
    """Get current simulation state for the dashboard."""
    return _sim_state


@app.get("/api/network")
async def get_network():
    """Get current network topology for dashboard rendering."""
    return _network_topology


# ─── CrewAI SSE stream (agent-sse-flow format) ──────────────────────


@app.get("/api/crewai/stream")
async def crewai_stream(request: Request):
    """SSE stream in agent-sse-flow format for CrewAI visualization."""
    queue: asyncio.Queue = asyncio.Queue()

    def subscriber(event: SSEEvent):
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(event)

    _collector.subscribe(subscriber)

    async def generate():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    agent_flow_event = _convert_to_agent_flow(event)
                    if agent_flow_event:
                        yield f"data: {json.dumps(agent_flow_event)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'thinking', 'message': 'keepalive'})}\n\n"
        finally:
            _collector.unsubscribe(subscriber)

    return StreamingResponse(generate(), media_type="text/event-stream")


def _convert_to_agent_flow(event: SSEEvent) -> dict | None:
    """Convert internal SSEEvent to agent-sse-flow format."""
    etype = event.event_type.value
    data = event.data

    if etype == "thinking":
        return {
            "type": "thinking",
            "message": data.get("thought", ""),
            "agentName": event.agent_id,
            "agentColor": _agent_color(event.agent_id),
        }

    if etype == "decision":
        decision = data.get("decision", {})
        layer = decision.get("layer", "unknown")
        reasoning = decision.get("reasoning", "")
        action = decision.get("action", "decision")
        phase = decision.get("phase", "")
        duration = decision.get("duration", "")

        # Tool call: the decision action
        tool_call = {
            "type": "tool_call",
            "tool": action,
            "args": {"phase": phase, "duration": duration, "layer": layer},
            "agentName": event.agent_id,
            "agentColor": _agent_color(event.agent_id),
            "duration": event.duration_ms,
        }

        # Tool result: the reasoning
        tool_result = {
            "type": "tool_result",
            "result": f"[{layer}] {reasoning}" if reasoning else f"[{layer}] {action} {phase} {duration}s",
            "duration": event.duration_ms,
        }

        # Return both as a batch (tool_call then tool_result)
        # We'll yield them separately in the stream
        return tool_call

    if etype == "conflict":
        return {
            "type": "tool_call",
            "tool": "resolve_conflict",
            "args": {"conflict_type": data.get("conflict_type", ""), "details": data.get("details", "")},
            "agentName": "coordinator",
            "agentColor": "#ff3366",
        }

    if etype == "coordination":
        return {
            "type": "message",
            "message": f"[coordination] {data.get('message', '')}",
            "agentName": event.agent_id,
            "agentColor": "#bc8cff",
        }

    if etype == "simulation_start":
        return {
            "type": "start",
            "message": f"CrewAI simulation started — {data.get('network', 'unknown')}, {data.get('steps', '?')} steps",
            "agentName": "system",
            "agentColor": "#ffcc00",
        }

    if etype == "simulation_step":
        return {
            "type": "end",
            "message": f"Step {data.get('step', '?')} complete ({data.get('duration_ms', 0):.0f}ms)",
            "duration": data.get("duration_ms", 0),
        }

    if etype == "simulation_end":
        return {
            "type": "end",
            "message": "Simulation complete",
            "cost": data.get("cost", 0),
            "tokens": data.get("tokens", 0),
            "duration": data.get("duration_ms", 0),
        }

    return None


def _agent_color(agent_id: str) -> str:
    """Deterministic color for agent based on ID."""
    colors = [
        "#3b82f6", "#00d4ff", "#00ff88", "#ffcc00", "#ff3366",
        "#bc8cff", "#ff8844", "#44ffdd", "#ff44aa", "#88aaff",
    ]
    h = sum(ord(c) for c in agent_id)
    return colors[h % len(colors)]


# ─── Local simulation loop (legacy) ─────────────────────────────────


async def _run_simulation(steps: int, speed: float, preset: str | None = None):
    """Run simulation with event emission."""
    global _simulation_running, _network_topology

    try:
        from traffic_agent.simulation.engine import SimulationConfig

        config = SimulationConfig(max_steps=steps * 10)

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

        if hasattr(sim, "intersections") and hasattr(sim, "segments"):
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
                    seg_id: {"from": seg.from_id, "to": seg.to_id, "length": seg.length, "name": seg.name}
                    for seg_id, seg in sim.segments.items()
                    if not seg_id.startswith("virtual_")
                },
            }
        else:
            _network_topology = {
                "type": net_type,
                "intersections": {
                    ix_id: {"row": int(ix_id.split("_")[1]), "col": int(ix_id.split("_")[2])}
                    for ix_id in sim.intersections
                },
                "segments": {},
            }

        _collector.emit(SSEEvent(
            event_type=EventType.SIMULATION_START,
            agent_id="system",
            timestamp=time.time(),
            data={"steps": steps, "network": net_type},
        ))

        for step in range(steps):
            if not _simulation_running:
                break

            for ix_id in sim.intersections:
                _collector.emit_thinking(
                    agent_id=ix_id,
                    thought=f"Step {step}: Analyzing traffic at {ix_id}",
                    context={"step": step, "queue": sim.intersections[ix_id].get_total_queue()},
                )

            start = time.time()
            sim.step()
            duration = (time.time() - start) * 1000

            for ix_id in sim.intersections:
                ix = sim.intersections[ix_id]
                _collector.emit_decision(
                    agent_id=ix_id,
                    decision={"phase": ix.current_phase, "step": step},
                    duration_ms=duration / max(len(sim.intersections), 1),
                )

            _collector.emit(SSEEvent(
                event_type=EventType.SIMULATION_STEP,
                agent_id="system",
                timestamp=time.time(),
                data={"step": step, "duration_ms": duration},
            ))

            await asyncio.sleep(1.0 / speed)

        _collector.emit(SSEEvent(
            event_type=EventType.SIMULATION_END,
            agent_id="system",
            timestamp=time.time(),
            data=_collector.get_metrics(),
        ))
    except Exception as e:
        _collector.emit(SSEEvent(
            event_type=EventType.SIMULATION_END,
            agent_id="system",
            timestamp=time.time(),
            data={"error": str(e)},
        ))
    finally:
        _simulation_running = False


# ─── CrewAI simulation loop ─────────────────────────────────────────


async def _run_crewai_simulation(steps: int, speed: float):
    """Run CrewAI multi-agent simulation with real LLM decisions."""
    global _simulation_running, _crew, _sim, _sim_state, _network_topology

    try:
        from traffic_agent.simulation.grid import GridSimulation
        from traffic_agent.simulation.engine import SimulationConfig
        from traffic_agent.crew.traffic_crew import TrafficControlCrew, CrewConfig
        from traffic_agent.llm.client import LLMConfig

        # Create grid simulation
        config = SimulationConfig(max_steps=steps * 10)
        sim = GridSimulation(config=config)
        _sim = sim

        # Export grid topology
        graph = sim.get_graph()
        _network_topology = {
            "type": "grid_3x3",
            "intersections": {
                ix_id: {"row": int(ix_id.split("_")[1]), "col": int(ix_id.split("_")[2])}
                for ix_id in sim.intersections
            },
            "segments": {
                f"{src}->{dst}": {"from": src, "to": dst}
                for src, neighbors in graph.items()
                for dst in neighbors
                if src < dst
            },
        }

        # Create CrewAI crew (all LLM, no rules/cache shortcuts)
        llm_config = LLMConfig()
        crew_config = CrewConfig(
            llm=llm_config,
            use_rules=False,
            use_cache=False,
            enable_timing_adjustment=True,
        )

        intersection_ids = list(sim.intersections.keys())
        crew = TrafficControlCrew(
            intersection_ids=intersection_ids,
            graph=graph,
            config=crew_config,
        )
        crew.set_engine(sim)
        _crew = crew

        # Emit start event
        _collector.emit(SSEEvent(
            event_type=EventType.SIMULATION_START,
            agent_id="system",
            timestamp=time.time(),
            data={
                "steps": steps,
                "network": "grid_3x3",
                "intersections": len(intersection_ids),
                "pipeline": "CrewAI (LLM only)",
            },
        ))

        for step in range(steps):
            if not _simulation_running:
                break

            step_start = time.time()

            # Advance simulation
            sim.step()

            # Run CrewAI pipeline (may block on LLM calls)
            loop = asyncio.get_event_loop()
            decisions = await loop.run_in_executor(None, crew.step, sim)

            step_duration = (time.time() - step_start) * 1000

            # Emit events for each decision
            for d in decisions:
                ix_id = d["intersection_id"]
                decision = d["decision"]
                layer = d["layer"]

                # Thinking event
                reasoning = getattr(decision, "reasoning", "") if hasattr(decision, "reasoning") else ""
                _collector.emit_thinking(
                    agent_id=ix_id,
                    thought=f"Step {step} | [{layer}] {reasoning or 'Processing...'}",
                    context={"step": step, "layer": layer, "intersection_id": ix_id},
                )

                # Decision event
                decision_dict = decision.to_dict() if hasattr(decision, "to_dict") else {"action": "unknown"}
                decision_dict["layer"] = layer
                _collector.emit_decision(
                    agent_id=ix_id,
                    decision=decision_dict,
                    duration_ms=step_duration / max(len(decisions), 1),
                )

            # Pipeline metrics per step
            crew_metrics = crew.get_metrics()
            _collector.emit(SSEEvent(
                event_type=EventType.METRICS,
                agent_id="system",
                timestamp=time.time(),
                data=crew_metrics,
            ))

            # Update sim state for /api/simulation/state
            first_ix = intersection_ids[0] if intersection_ids else None
            _sim_state = {
                "step": step,
                "intersections": {
                    ix_id: {
                        "phase": sim.intersections[ix_id].current_phase,
                        "queue_total": sim.intersections[ix_id].get_total_queue(),
                    }
                    for ix_id in intersection_ids
                },
                "pipeline": {
                    "layer": decisions[-1]["layer"] if decisions else "none",
                    "rule_hit_rate": crew_metrics.get("rule_hit_rate", 0),
                    "cache_hit_rate": crew_metrics.get("cache_hit_rate", 0),
                    "llm_calls": crew_metrics.get("total_llm_calls", 0),
                    "total_decisions": crew_metrics.get("total_decisions", 0),
                },
            }

            # Step event
            _collector.emit(SSEEvent(
                event_type=EventType.SIMULATION_STEP,
                agent_id="system",
                timestamp=time.time(),
                data={"step": step, "duration_ms": step_duration},
            ))

            await asyncio.sleep(1.0 / speed)

        # Final metrics
        final_metrics = crew.get_metrics()
        _collector.emit(SSEEvent(
            event_type=EventType.SIMULATION_END,
            agent_id="system",
            timestamp=time.time(),
            data=final_metrics,
        ))

    except Exception as e:
        import traceback
        traceback.print_exc()
        _collector.emit(SSEEvent(
            event_type=EventType.SIMULATION_END,
            agent_id="system",
            timestamp=time.time(),
            data={"error": str(e)},
        ))
    finally:
        _simulation_running = False
        _crew = None
        _sim = None


# ─── Static files (must be last) ────────────────────────────────────

_build_dir = _get_vis_dir() / "dashboard_build"
if _build_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_build_dir / "assets")), name="dashboard-assets")
