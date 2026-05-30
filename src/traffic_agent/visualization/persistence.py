"""
Event Persistence — Store and retrieve simulation events.

Provides SQLite-based persistence for simulation events,
allowing historical analysis and replay.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class EventStore:
    """SQLite-based event storage."""

    def __init__(self, db_path: str | Path = ":memory:"):
        """
        Initialize event store.

        Args:
            db_path: Path to SQLite database file, or ":memory:" for in-memory
        """
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent write performance
        self.conn.execute("PRAGMA journal_mode=WAL")
        try:
            self._create_tables()
        except Exception:
            self.conn.close()
            raise

    def _create_tables(self) -> None:
        """Create database tables."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                agent_id TEXT,
                data TEXT,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_timestamp
            ON events(timestamp)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_type
            ON events(event_type)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_agent
            ON events(agent_id)
        """)

        self.conn.commit()

    def store_event(
        self,
        timestamp: float,
        event_type: str,
        agent_id: str | None = None,
        data: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> int:
        """
        Store an event.

        Args:
            timestamp: Event timestamp
            event_type: Type of event
            agent_id: Optional agent ID
            data: Optional event data
            commit: Whether to commit immediately (set False for batch inserts)

        Returns:
            Event ID
        """
        cursor = self.conn.execute(
            "INSERT INTO events (timestamp, event_type, agent_id, data) VALUES (?, ?, ?, ?)",
            (timestamp, event_type, agent_id, json.dumps(data) if data else None),
        )
        if commit:
            self.conn.commit()
        return cursor.lastrowid

    def flush(self) -> None:
        """Flush pending writes to disk."""
        self.conn.commit()

    def get_events(
        self,
        event_type: str | None = None,
        agent_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Retrieve events with optional filtering.

        Args:
            event_type: Filter by event type
            agent_id: Filter by agent ID
            since: Minimum timestamp
            until: Maximum timestamp
            limit: Maximum number of results

        Returns:
            List of event dictionaries
        """
        query = "SELECT * FROM events WHERE 1=1"
        params: list[Any] = []

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)

        if since is not None:
            query += " AND timestamp >= ?"
            params.append(since)

        if until is not None:
            query += " AND timestamp <= ?"
            params.append(until)

        query += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        params.append(limit)

        cursor = self.conn.execute(query, params)
        rows = cursor.fetchall()

        return [
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "event_type": row["event_type"],
                "agent_id": row["agent_id"],
                "data": json.loads(row["data"]) if row["data"] else None,
            }
            for row in rows
        ]

    def get_event_count(
        self,
        event_type: str | None = None,
        agent_id: str | None = None,
    ) -> int:
        """Get count of events matching filters."""
        query = "SELECT COUNT(*) as count FROM events WHERE 1=1"
        params: list[Any] = []

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)

        cursor = self.conn.execute(query, params)
        return cursor.fetchone()["count"]

    def get_agents(self) -> list[str]:
        """Get list of unique agent IDs."""
        cursor = self.conn.execute(
            "SELECT DISTINCT agent_id FROM events WHERE agent_id IS NOT NULL"
        )
        return [row["agent_id"] for row in cursor.fetchall()]

    def get_event_types(self) -> list[str]:
        """Get list of unique event types."""
        cursor = self.conn.execute(
            "SELECT DISTINCT event_type FROM events"
        )
        return [row["event_type"] for row in cursor.fetchall()]

    def clear(self) -> None:
        """Clear all events."""
        self.conn.execute("DELETE FROM events")
        self.conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
