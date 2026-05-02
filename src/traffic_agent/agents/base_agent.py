"""
Base Agent Interface

All traffic signal agents must implement this interface.
Follows Google's "Design for failure" principle — agents can crash
and be restarted without affecting the simulation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class AgentState(Enum):
    """Agent lifecycle states."""
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    TERMINATED = "terminated"


@dataclass
class Observation:
    """
    Agent observation from the environment.
    
    Standardized format for all agents to consume.
    """
    intersection_id: str
    timestamp: float
    
    # Per-approach features
    queue_lengths: np.ndarray          # [N] vehicles waiting per approach
    vehicle_counts: np.ndarray         # [N] total vehicles per approach
    arrival_rates: np.ndarray          # [N] vehicles/sec per approach
    
    # Intersection state
    current_phase: int                 # Active signal phase index
    phase_duration: float              # Seconds in current phase
    time_since_change: float           # Seconds since last phase change
    
    # Pedestrian
    pedestrian_waiting: np.ndarray     # [N] pedestrians per crosswalk
    
    # Emergency
    emergency_pending: bool = False
    emergency_approach: Optional[int] = None
    
    # Neighbor info (for coordination)
    neighbor_states: Dict[str, Any] = field(default_factory=dict)
    
    def to_numpy(self) -> np.ndarray:
        """Flatten observation to numpy array for RL input."""
        parts = [
            self.queue_lengths,
            self.vehicle_counts,
            self.arrival_rates,
            np.array([self.current_phase]),
            np.array([self.phase_duration]),
            np.array([self.time_since_change]),
            self.pedestrian_waiting,
            np.array([float(self.emergency_pending)]),
        ]
        return np.concatenate([p.flatten() for p in parts]).astype(np.float32)


@dataclass
class Action:
    """
    Agent action — signal timing decision.
    
    Attributes:
        phase: Which signal phase to activate
        duration: How long to hold this phase (seconds)
        min_green: Minimum green time (safety constraint)
        max_green: Maximum green time (efficiency constraint)
    """
    phase: int
    duration: float
    min_green: float = 10.0
    max_green: float = 60.0
    emergency_override: bool = False
    
    def __post_init__(self):
        """Enforce safety constraints."""
        self.duration = max(self.min_green, min(self.max_green, self.duration))


@dataclass
class StepResult:
    """Result of one environment step."""
    observation: Observation
    reward: float
    done: bool
    info: Dict[str, Any]


class BaseAgent(ABC):
    """
    Abstract base class for all traffic signal agents.
    
    Lifecycle:
        1. __init__() — configure agent
        2. reset() — prepare for new episode
        3. observe() — receive environment state
        4. act() — decide signal timing
        5. learn() — update policy from experience
        6. save()/load() — persistence
    
    Google Design Principles Applied:
    - Every method is idempotent where possible
    - All state transitions are logged
    - Errors don't propagate (agent stays alive)
    """
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        self.agent_id = agent_id
        self.config = config
        self.state = AgentState.INITIALIZING
        self._episode_count = 0
        self._total_reward = 0.0
        self._step_count = 0
        
    @abstractmethod
    def observe(self, observation: Observation) -> None:
        """
        Process environment observation.
        
        Called before act(). Agent should update internal state
        based on what it sees in the environment.
        """
        pass
    
    @abstractmethod
    def act(self) -> Action:
        """
        Select action based on current observation.
        
        Must return a valid Action. If agent fails to decide,
        should return a safe default (e.g., current phase extension).
        """
        pass
    
    @abstractmethod
    def learn(self, observation: Observation, action: Action, 
              reward: float, next_observation: Observation, done: bool) -> None:
        """
        Update policy from experience tuple (s, a, r, s', done).
        
        Called after each step during training.
        During inference, this is a no-op.
        """
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """
        Reset agent for new episode.
        
        Clear episode-specific state (buffers, counters).
        Keep learned parameters.
        """
        self._episode_count += 1
        self._total_reward = 0.0
        self._step_count = 0
    
    @abstractmethod
    def save(self, path: str) -> None:
        """Save agent state to disk."""
        pass
    
    @abstractmethod
    def load(self, path: str) -> None:
        """Load agent state from disk."""
        pass
    
    def get_metrics(self) -> Dict[str, float]:
        """Return agent performance metrics."""
        return {
            "agent/episode_count": self._episode_count,
            "agent/total_reward": self._total_reward,
            "agent/step_count": self._step_count,
            "agent/avg_reward": (
                self._total_reward / max(1, self._step_count)
            ),
        }
    
    @property
    def is_ready(self) -> bool:
        return self.state == AgentState.READY
    
    @property
    def is_running(self) -> bool:
        return self.state == AgentState.RUNNING
