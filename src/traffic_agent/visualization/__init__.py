"""Visualization module — SSE events and dashboard for Agent reasoning."""

from traffic_agent.visualization.events import EventCollector, EventType, SSEEvent
from traffic_agent.visualization.runner import SimulationRunner

__all__ = ["EventCollector", "EventType", "SSEEvent", "SimulationRunner"]
