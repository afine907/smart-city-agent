"""
Tests for SSE Visualization — Events, API, and Runner.
"""

import json
import time

import pytest

from traffic_agent.visualization.events import (
    EventCollector,
    EventType,
    SSEEvent,
)


class TestSSEEvent:
    """Test SSEEvent dataclass."""

    def test_creation(self):
        event = SSEEvent(
            event_type=EventType.THINKING,
            agent_id="ix_0_0",
            timestamp=100.0,
            data={"thought": "Analyzing traffic"},
        )
        assert event.event_type == EventType.THINKING
        assert event.agent_id == "ix_0_0"
        assert event.timestamp == 100.0
        assert event.data["thought"] == "Analyzing traffic"
        assert event.duration_ms is None

    def test_to_dict(self):
        event = SSEEvent(
            event_type=EventType.DECISION,
            agent_id="ix_0_1",
            timestamp=200.0,
            data={"phase": 0},
            duration_ms=15.5,
        )
        d = event.to_dict()
        assert d["event_type"] == "decision"
        assert d["agent_id"] == "ix_0_1"
        assert d["duration_ms"] == 15.5

    def test_to_sse(self):
        event = SSEEvent(
            event_type=EventType.CONFLICT,
            agent_id="ix_1_1",
            timestamp=300.0,
            data={"conflict_type": "phase_mismatch"},
        )
        sse = event.to_sse()
        assert sse.startswith("event: conflict\n")
        assert "data:" in sse
        assert sse.endswith("\n\n")
        # Verify JSON in data line is valid
        data_line = [line for line in sse.split("\n") if line.startswith("data:")][0]
        json_str = data_line[5:].strip()
        parsed = json.loads(json_str)
        assert parsed["agent_id"] == "ix_1_1"

    def test_event_types(self):
        assert EventType.THINKING.value == "thinking"
        assert EventType.DECISION.value == "decision"
        assert EventType.CONFLICT.value == "conflict"
        assert EventType.COORDINATION.value == "coordination"
        assert EventType.METRICS.value == "metrics"


class TestEventCollector:
    """Test EventCollector."""

    def test_creation(self):
        collector = EventCollector()
        assert collector.count == 0
        assert len(collector.events) == 0

    def test_emit(self):
        collector = EventCollector()
        event = SSEEvent(
            event_type=EventType.THINKING,
            agent_id="ix_0_0",
            timestamp=time.time(),
            data={"thought": "test"},
        )
        collector.emit(event)
        assert collector.count == 1
        assert collector.events[0].agent_id == "ix_0_0"

    def test_subscribe(self):
        collector = EventCollector()
        received = []

        def callback(event):
            received.append(event)

        collector.subscribe(callback)
        collector.emit_thinking("ix_0_0", "hello")
        assert len(received) == 1
        assert received[0].data["thought"] == "hello"

    def test_unsubscribe(self):
        collector = EventCollector()
        received = []

        def callback(event):
            received.append(event)

        collector.subscribe(callback)
        collector.emit_thinking("ix_0_0", "hello")
        collector.unsubscribe(callback)
        collector.emit_thinking("ix_0_0", "world")
        assert len(received) == 1  # Only first event

    def test_clear(self):
        collector = EventCollector()
        collector.emit_thinking("ix_0_0", "test")
        assert collector.count == 1
        collector.clear()
        assert collector.count == 0

    def test_get_events_filter_type(self):
        collector = EventCollector()
        collector.emit_thinking("ix_0_0", "think")
        collector.emit_decision("ix_0_0", {"phase": 0}, 10.0)
        collector.emit_decision("ix_0_1", {"phase": 1}, 15.0)

        decisions = collector.get_events(event_type=EventType.DECISION)
        assert len(decisions) == 2
        assert all(e.event_type == EventType.DECISION for e in decisions)

    def test_get_events_filter_agent(self):
        collector = EventCollector()
        collector.emit_thinking("ix_0_0", "a")
        collector.emit_thinking("ix_0_1", "b")
        collector.emit_thinking("ix_0_0", "c")

        events = collector.get_events(agent_id="ix_0_0")
        assert len(events) == 2
        assert all(e.agent_id == "ix_0_0" for e in events)

    def test_get_metrics(self):
        collector = EventCollector()
        collector.emit_thinking("ix_0_0", "t1")
        collector.emit_thinking("ix_0_1", "t2")
        collector.emit_decision("ix_0_0", {"phase": 0}, 20.0)
        collector.emit_decision("ix_0_1", {"phase": 1}, 40.0)
        collector.emit_conflict("ix_0_0", "phase_mismatch", "oops")

        m = collector.get_metrics()
        assert m["total_events"] == 5
        assert m["total_decisions"] == 2
        assert m["total_conflicts"] == 1
        assert m["total_thinking"] == 2
        assert m["avg_decision_ms"] == 30.0
        assert m["unique_agents"] == 2

    def test_convenience_methods(self):
        collector = EventCollector()

        e1 = collector.emit_thinking("ix_0_0", "hello", {"step": 1})
        assert e1.event_type == EventType.THINKING
        assert e1.data["context"]["step"] == 1

        e2 = collector.emit_decision("ix_0_1", {"phase": 0}, 25.0)
        assert e2.duration_ms == 25.0

        e3 = collector.emit_conflict("ix_1_1", "excessive_green", "too long")
        assert e3.data["conflict_type"] == "excessive_green"

        e4 = collector.emit_coordination("ix_0_0", "ix_0_1", "sync please")
        assert e4.data["target_id"] == "ix_0_1"

        assert collector.count == 4

    def test_subscriber_error_ignored(self):
        collector = EventCollector()

        def bad_callback(event):
            raise RuntimeError("boom")

        collector.subscribe(bad_callback)
        # Should not raise
        collector.emit_thinking("ix_0_0", "test")
        assert collector.count == 1

    def test_get_events_limit(self):
        collector = EventCollector()
        for i in range(10):
            collector.emit_thinking(f"ix_{i}", f"t{i}")

        events = collector.get_events(limit=3)
        assert len(events) == 3


class TestSimulationRunner:
    """Test SimulationRunner integration."""

    def test_setup(self):
        from traffic_agent.visualization.runner import SimulationRunner

        runner = SimulationRunner()
        runner.setup()
        assert runner.simulation is not None
        # Should have emitted SIMULATION_START
        assert runner.collector.count >= 1
        start_events = runner.collector.get_events(event_type=EventType.SIMULATION_START)
        assert len(start_events) == 1

    def test_step(self):
        from traffic_agent.visualization.runner import SimulationRunner

        runner = SimulationRunner()
        runner.setup()
        runner.step()
        # Should have thinking + decision events for each intersection
        assert runner.collector.count > 1
        decisions = runner.collector.get_events(event_type=EventType.DECISION)
        assert len(decisions) == 9  # 3x3 grid

    def test_run(self):
        from traffic_agent.visualization.runner import SimulationRunner

        runner = SimulationRunner()
        runner.run(steps=3)
        # Should have start + 3*(thinking+decision) + end events
        assert runner.collector.count > 27  # 3 steps * 9 intersections * 2 event types + start/end
        end_events = runner.collector.get_events(event_type=EventType.SIMULATION_END)
        assert len(end_events) == 1

    def test_metrics(self):
        from traffic_agent.visualization.runner import SimulationRunner

        runner = SimulationRunner()
        runner.run(steps=2)
        m = runner.metrics
        assert m["total_decisions"] == 18  # 2 steps * 9 intersections
        assert m["unique_agents"] == 10  # 9 intersections + "system"


class TestSSEServer:
    """Test FastAPI SSE server endpoints."""

    @pytest.fixture(autouse=True)
    def _reset_simulation(self):
        """Reset global simulation state between tests."""

        import traffic_agent.api.sse_server as srv

        srv._simulation_running = False
        if srv._simulation_task:
            srv._simulation_task.cancel()
            srv._simulation_task = None
        # Small delay to let any pending tasks finish
        import time

        time.sleep(0.05)
        yield
        srv._simulation_running = False
        if srv._simulation_task:
            srv._simulation_task.cancel()
            srv._simulation_task = None
        time.sleep(0.05)

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from traffic_agent.api.sse_server import app, get_collector

        get_collector().clear()
        return TestClient(app)

    def test_dashboard(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_event_history_empty(self, client):
        response = client.get("/api/events/history")
        assert response.status_code == 200
        data = response.json()
        assert data["events"] == []
        assert data["total"] == 0

    def test_event_history_with_events(self, client):
        from traffic_agent.api.sse_server import get_collector

        collector = get_collector()
        collector.emit_thinking("ix_0_0", "test thought")
        collector.emit_decision("ix_0_0", {"phase": 0}, 10.0)

        response = client.get("/api/events/history")
        data = response.json()
        assert data["total"] == 2

    def test_event_history_filter(self, client):
        from traffic_agent.api.sse_server import get_collector

        collector = get_collector()
        collector.emit_thinking("ix_0_0", "t")
        collector.emit_decision("ix_0_0", {"phase": 0}, 10.0)

        response = client.get("/api/events/history?event_type=decision")
        data = response.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "decision"

    def test_metrics(self, client):
        from traffic_agent.api.sse_server import get_collector

        collector = get_collector()
        collector.emit_thinking("ix_0_0", "t")
        collector.emit_decision("ix_0_0", {"phase": 0}, 15.0)

        response = client.get("/api/events/metrics")
        data = response.json()
        assert data["total_events"] == 2
        assert data["total_decisions"] == 1

    def test_simulation_status(self, client):
        response = client.get("/api/simulation/status")
        data = response.json()
        assert data["running"] is False
        assert "metrics" in data

    def test_simulation_start_stop(self, client):
        from unittest.mock import patch

        # Mock the background task to avoid async issues in test
        with patch("traffic_agent.api.sse_server._run_simulation") as mock_run:
            mock_run.return_value = None
            response = client.post("/api/simulation/start?steps=5&speed=10")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "started"

            response = client.post("/api/simulation/stop")
            assert response.status_code == 200

    def test_simulation_start_conflict(self, client):
        import asyncio
        from unittest.mock import patch

        # Create a long-running task mock
        async def slow_sim(*args, **kwargs):
            await asyncio.sleep(100)

        with patch("traffic_agent.api.sse_server._run_simulation", side_effect=slow_sim):
            client.post("/api/simulation/start?steps=1000&speed=1")

            status = client.get("/api/simulation/status").json()
            assert status["running"] is True

            response = client.post("/api/simulation/start?steps=5&speed=10")
            assert response.status_code == 409

            client.post("/api/simulation/stop")
