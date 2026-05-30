"""
Tests for Event Persistence module.
"""

import pytest

from traffic_agent.visualization.persistence import EventStore


class TestEventStore:
    """Test EventStore."""

    def test_store_and_retrieve(self):
        with EventStore() as store:
            event_id = store.store_event(
                timestamp=1.0,
                event_type="test",
                agent_id="agent1",
                data={"key": "value"},
            )

            events = store.get_events()
            assert len(events) == 1
            assert events[0]["event_type"] == "test"
            assert events[0]["data"]["key"] == "value"

    def test_filter_by_type(self):
        with EventStore() as store:
            store.store_event(1.0, "type_a")
            store.store_event(2.0, "type_b")
            store.store_event(3.0, "type_a")

            events = store.get_events(event_type="type_a")
            assert len(events) == 2

    def test_filter_by_agent(self):
        with EventStore() as store:
            store.store_event(1.0, "test", agent_id="agent1")
            store.store_event(2.0, "test", agent_id="agent2")
            store.store_event(3.0, "test", agent_id="agent1")

            events = store.get_events(agent_id="agent1")
            assert len(events) == 2

    def test_filter_by_time(self):
        with EventStore() as store:
            store.store_event(1.0, "test")
            store.store_event(2.0, "test")
            store.store_event(3.0, "test")
            store.store_event(4.0, "test")

            events = store.get_events(since=2.0, until=3.0)
            assert len(events) == 2

    def test_limit(self):
        with EventStore() as store:
            for i in range(10):
                store.store_event(float(i), "test")

            events = store.get_events(limit=5)
            assert len(events) == 5

    def test_event_count(self):
        with EventStore() as store:
            store.store_event(1.0, "type_a")
            store.store_event(2.0, "type_b")
            store.store_event(3.0, "type_a")

            assert store.get_event_count() == 3
            assert store.get_event_count(event_type="type_a") == 2

    def test_get_agents(self):
        with EventStore() as store:
            store.store_event(1.0, "test", agent_id="agent1")
            store.store_event(2.0, "test", agent_id="agent2")
            store.store_event(3.0, "test", agent_id="agent1")

            agents = store.get_agents()
            assert len(agents) == 2
            assert "agent1" in agents
            assert "agent2" in agents

    def test_get_event_types(self):
        with EventStore() as store:
            store.store_event(1.0, "type_a")
            store.store_event(2.0, "type_b")

            types = store.get_event_types()
            assert len(types) == 2

    def test_clear(self):
        with EventStore() as store:
            store.store_event(1.0, "test")
            store.store_event(2.0, "test")

            assert store.get_event_count() == 2

            store.clear()
            assert store.get_event_count() == 0

    def test_file_persistence(self, tmp_path):
        db_path = tmp_path / "test.db"

        # Store events
        with EventStore(db_path) as store:
            store.store_event(1.0, "test", data={"key": "value"})

        # Reopen and verify
        with EventStore(db_path) as store:
            events = store.get_events()
            assert len(events) == 1
            assert events[0]["data"]["key"] == "value"

    def test_ordering(self):
        with EventStore() as store:
            store.store_event(3.0, "test")
            store.store_event(1.0, "test")
            store.store_event(2.0, "test")

            events = store.get_events()
            # Should be ordered by timestamp DESC
            assert events[0]["timestamp"] == 3.0
            assert events[1]["timestamp"] == 2.0
            assert events[2]["timestamp"] == 1.0
