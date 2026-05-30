"""
SSE Events — Event collection and emission for Agent reasoning visualization.

Captures thinking, decisions, conflicts, and coordination during simulation runs.
"""

from __future__ import annotations


import contextlib
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """Types of SSE events emitted during simulation."""

    THINKING = "thinking"
    DECISION = "decision"
    CONFLICT = "conflict"
    COORDINATION = "coordination"
    METRICS = "metrics"
    SIMULATION_START = "simulation_start"
    SIMULATION_STEP = "simulation_step"
    SIMULATION_END = "simulation_end"


@dataclass
class SSEEvent:
    """A single SSE event emitted by an agent or simulation."""

    event_type: EventType
    agent_id: str
    timestamp: float
    data: dict[str, Any]
    duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = {
            "event_type": self.event_type.value,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp,
            "data": self.data,
        }
        if self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        return d

    def to_sse(self) -> str:
        """Format as SSE text stream."""
        return f"event: {self.event_type.value}\ndata: {json.dumps(self.to_dict())}\n\n"


class EventCollector:
    """Collects SSE events during simulation runs."""

    def __init__(self) -> None:
        self._events: list[SSEEvent] = []
        self._subscribers: list[Any] = []
        self._start_time: float | None = None

    @property
    def events(self) -> list[SSEEvent]:
        """All collected events."""
        return list(self._events)

    @property
    def count(self) -> int:
        """Number of collected events."""
        return len(self._events)

    def emit(self, event: SSEEvent) -> None:
        """Emit an event — store it and notify subscribers."""
        self._events.append(event)
        for sub in self._subscribers:
            try:
                sub(event)
            except Exception:
                pass  # Don't let subscriber errors break simulation

    def subscribe(self, callback: Any) -> None:
        """Subscribe to new events."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Any) -> None:
        """Unsubscribe from events."""
        self._subscribers = [s for s in self._subscribers if s is not callback]

    def clear(self) -> None:
        """Clear all collected events."""
        self._events.clear()

    def get_events(
        self,
        event_type: EventType | None = None,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[SSEEvent]:
        """Get filtered events."""
        result = self._events
        if event_type:
            result = [e for e in result if e.event_type == event_type]
        if agent_id:
            result = [e for e in result if e.agent_id == agent_id]
        return result[-limit:]

    def get_metrics(self) -> dict[str, Any]:
        """Get aggregated metrics from collected events."""
        decisions = [e for e in self._events if e.event_type == EventType.DECISION]
        conflicts = [e for e in self._events if e.event_type == EventType.CONFLICT]
        thinking = [e for e in self._events if e.event_type == EventType.THINKING]

        durations = [e.duration_ms for e in decisions if e.duration_ms is not None]
        avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "total_events": len(self._events),
            "total_decisions": len(decisions),
            "total_conflicts": len(conflicts),
            "total_thinking": len(thinking),
            "avg_decision_ms": round(avg_duration, 2),
            "unique_agents": len(set(e.agent_id for e in self._events)),
        }

    def emit_thinking(self, agent_id: str, thought: str, context: dict | None = None) -> SSEEvent:
        """Convenience: emit a thinking event."""
        event = SSEEvent(
            event_type=EventType.THINKING,
            agent_id=agent_id,
            timestamp=time.time(),
            data={"thought": thought, "context": context or {}},
        )
        self.emit(event)
        return event

    def emit_decision(
        self, agent_id: str, decision: dict[str, Any], duration_ms: float
    ) -> SSEEvent:
        """Convenience: emit a decision event."""
        event = SSEEvent(
            event_type=EventType.DECISION,
            agent_id=agent_id,
            timestamp=time.time(),
            data={"decision": decision},
            duration_ms=duration_ms,
        )
        self.emit(event)
        return event

    def emit_conflict(self, agent_id: str, conflict_type: str, details: str) -> SSEEvent:
        """Convenience: emit a conflict event."""
        event = SSEEvent(
            event_type=EventType.CONFLICT,
            agent_id=agent_id,
            timestamp=time.time(),
            data={"conflict_type": conflict_type, "details": details},
        )
        self.emit(event)
        return event

    def emit_coordination(self, agent_id: str, target_id: str, message: str) -> SSEEvent:
        """Convenience: emit a coordination event."""
        event = SSEEvent(
            event_type=EventType.COORDINATION,
            agent_id=agent_id,
            timestamp=time.time(),
            data={"target_id": target_id, "message": message},
        )
        self.emit(event)
        return event
