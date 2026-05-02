"""
Base Agent Interface

All traffic signal agents must implement this interface.
Follows Google's "Design for failure" principle — agents can crash
and be restarted without affecting the simulation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from traffic_agent.tools.traffic_tools import IntersectionState


class AgentState(Enum):
    """Agent lifecycle states."""
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    TERMINATED = "terminated"


@dataclass
class AgentDecision:
    """Decision made by an agent."""
    phase: str                    # NS_GREEN / EW_GREEN
    duration: int                 # seconds
    reasoning: str
    confidence: float = 0.7
    action: str = "extend_green"  # extend_green / switch_phase / emergency

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "duration": self.duration,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "action": self.action,
        }


class BaseAgent(ABC):
    """
    Abstract base class for all traffic signal agents.

    Lifecycle:
        1. __init__() — configure agent
        2. reset() — prepare for new episode
        3. observe() — receive environment state
        4. decide() — decide signal timing
        5. save()/load() — persistence
    """

    def __init__(self, agent_id: str, config: Optional[Dict[str, Any]] = None):
        self.agent_id = agent_id
        self.config = config or {}
        self.state = AgentState.INITIALIZING
        self._decision_count = 0
        self._total_confidence = 0.0

    @abstractmethod
    def observe(self, observation: IntersectionState) -> None:
        """
        Process environment observation.

        Called before decide(). Agent should update internal state
        based on what it sees in the environment.
        """
        pass

    @abstractmethod
    def decide(self, observation: IntersectionState,
               neighbors: Optional[Dict[str, IntersectionState]] = None) -> AgentDecision:
        """
        Decide signal timing based on current observation.

        Must return a valid AgentDecision. If agent fails to decide,
        should return a safe default (e.g., current phase extension).
        """
        pass

    def reset(self) -> None:
        """Reset agent for new episode."""
        self._decision_count = 0
        self._total_confidence = 0.0

    @abstractmethod
    def save(self, path: str) -> None:
        """Save agent state to disk."""
        pass

    @abstractmethod
    def load(self, path: str) -> None:
        """Load agent state from disk."""
        pass

    def get_metrics(self) -> Dict[str, Any]:
        """Return agent performance metrics."""
        return {
            "agent_id": self.agent_id,
            "decision_count": self._decision_count,
            "avg_confidence": (
                self._total_confidence / max(1, self._decision_count)
            ),
        }

    @property
    def is_ready(self) -> bool:
        return self.state == AgentState.READY

    @property
    def is_running(self) -> bool:
        return self.state == AgentState.RUNNING
