"""
Tests for FastAPI SSE Server — integration tests using TestClient.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client for the API."""
    # Reset global state before each test
    import traffic_agent.api.sse_server as srv
    srv._simulation_running = False
    srv._simulation_task = None
    srv._collector.clear()
    srv._sim_state = {}
    srv._network_topology = {}
    srv._crew = None
    srv._sim = None

    from traffic_agent.api.sse_server import app
    return TestClient(app)


class TestDashboardEndpoint:
    """Test dashboard serving."""

    def test_dashboard_endpoint(self, client):
        response = client.get("/")
        # Should return HTML or 404 if not built
        assert response.status_code in (200, 404)


class TestSimulationAPI:
    """Test simulation control endpoints."""

    def test_get_status(self, client):
        response = client.get("/api/simulation/status")
        assert response.status_code == 200
        data = response.json()
        assert "running" in data
        assert data["running"] is False

    def test_get_state(self, client):
        response = client.get("/api/simulation/state")
        assert response.status_code == 200

    def test_start_simulation(self, client):
        response = client.post(
            "/api/simulation/start",
            params={"steps": 5, "mode": "local"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert data["steps"] == 5

    def test_start_stop_flow(self, client):
        """Test start and stop simulation flow."""
        import traffic_agent.api.sse_server as srv

        # Manually set running state to test conflict
        srv._simulation_running = True
        response = client.post(
            "/api/simulation/start",
            params={"steps": 5, "mode": "local"},
        )
        assert response.status_code == 409

        # Reset and test stop
        srv._simulation_running = False
        response = client.post("/api/simulation/stop")
        assert response.status_code == 409

    def test_stop_no_simulation(self, client):
        response = client.post("/api/simulation/stop")
        assert response.status_code == 409


class TestEventAPI:
    """Test event endpoints."""

    def test_event_history_empty(self, client):
        response = client.get("/api/events/history")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert isinstance(data["events"], list)

    def test_event_metrics(self, client):
        response = client.get("/api/events/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "total_events" in data

    def test_event_history_with_limit(self, client):
        response = client.get("/api/events/history", params={"limit": 10})
        assert response.status_code == 200


class TestNetworkAPI:
    """Test network endpoint."""

    def test_get_network(self, client):
        response = client.get("/api/network")
        assert response.status_code == 200
