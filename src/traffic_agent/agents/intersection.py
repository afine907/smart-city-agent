"""
Intersection Agent — RL-based Traffic Signal Control

Each intersection is an autonomous agent that:
1. Observes local traffic state
2. Decides signal timing
3. Learns from experience
4. Coordinates with neighbors

This is the core RL agent implementation.
"""

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from traffic_agent.agents.base_agent import (
    Action,
    AgentState,
    BaseAgent,
    Observation,
    StepResult,
)


@dataclass
class AgentConfig:
    """Configuration for an intersection agent."""
    
    # Network architecture
    hidden_dims: List[int] = field(default_factory=lambda: [128, 64])
    
    # RL hyperparameters
    learning_rate: float = 3e-4
    gamma: float = 0.99          # Discount factor
    epsilon_start: float = 1.0   # Initial exploration
    epsilon_end: float = 0.05    # Min exploration
    epsilon_decay: float = 0.995 # Decay per episode
    batch_size: int = 64
    buffer_size: int = 100_000
    target_update_freq: int = 100 # Steps between target network updates
    
    # Reward weights
    wait_time_weight: float = 1.0
    queue_weight: float = 0.5
    throughput_weight: float = 0.3
    phase_change_penalty: float = 0.1
    balance_weight: float = 0.2
    
    # Safety constraints
    min_green: float = 10.0
    max_green: float = 60.0
    yellow_duration: float = 3.0
    
    # Coordination
    coordination_enabled: bool = True
    message_interval: float = 5.0  # Seconds between neighbor messages


class SimpleDQN:
    """
    Simplified DQN for traffic signal control.
    
    In production, use Stable-Baselines3 or similar.
    This is a self-contained implementation for learning and testing.
    """
    
    def __init__(self, state_dim: int, action_dim: int, config: AgentConfig):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.config = config
        
        # Simple 2-layer MLP (no torch dependency for now)
        self.weights1 = np.random.randn(state_dim, config.hidden_dims[0]) * 0.01
        self.bias1 = np.zeros(config.hidden_dims[0])
        self.weights2 = np.random.randn(config.hidden_dims[0], config.hidden_dims[1]) * 0.01
        self.bias2 = np.zeros(config.hidden_dims[1])
        self.weights3 = np.random.randn(config.hidden_dims[1], action_dim) * 0.01
        self.bias3 = np.zeros(action_dim)
        
        # Target network (copy)
        self.target_weights1 = self.weights1.copy()
        self.target_bias1 = self.bias1.copy()
        self.target_weights2 = self.weights2.copy()
        self.target_bias2 = self.bias2.copy()
        self.target_weights3 = self.weights3.copy()
        self.target_bias3 = self.bias3.copy()
        
        self.optimizer_state = {}  # Placeholder for optimizer state
    
    def forward(self, state: np.ndarray) -> np.ndarray:
        """Forward pass through network."""
        x = np.maximum(0, state @ self.weights1 + self.bias1)  # ReLU
        x = np.maximum(0, x @ self.weights2 + self.bias2)      # ReLU
        q_values = x @ self.weights3 + self.bias3
        return q_values
    
    def target_forward(self, state: np.ndarray) -> np.ndarray:
        """Forward pass through target network."""
        x = np.maximum(0, state @ self.target_weights1 + self.target_bias1)
        x = np.maximum(0, x @ self.target_weights2 + self.target_bias2)
        q_values = x @ self.target_weights3 + self.target_bias3
        return q_values
    
    def update_target(self) -> None:
        """Copy online weights to target network."""
        self.target_weights1 = self.weights1.copy()
        self.target_bias1 = self.bias1.copy()
        self.target_weights2 = self.weights2.copy()
        self.target_bias2 = self.bias2.copy()
        self.target_weights3 = self.weights3.copy()
        self.target_bias3 = self.bias3.copy()


class ReplayBuffer:
    """Experience replay buffer for DQN training."""
    
    def __init__(self, capacity: int):
        self.buffer = deque(maxlen=capacity)
    
    def push(self, state: np.ndarray, action: int, reward: float,
             next_state: np.ndarray, done: bool) -> None:
        self.buffer.append((state, action, reward, next_state, done))
    
    def sample(self, batch_size: int) -> Tuple:
        batch = random.sample(self.buffer, batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        return (
            np.array(states),
            np.array(actions),
            np.array(rewards, dtype=np.float32),
            np.array(next_states),
            np.array(dones, dtype=np.float32),
        )
    
    def __len__(self) -> int:
        return len(self.buffer)


class IntersectionAgent(BaseAgent):
    """
    RL agent for a single intersection.
    
    Uses DQN with experience replay and target network.
    
    State space:
        - Queue lengths per approach (N)
        - Vehicle counts per approach (N)
        - Arrival rates per approach (N)
        - Current phase (1)
        - Phase duration (1)
        - Time since change (1)
        - Pedestrian waiting per approach (N)
        - Emergency flag (1)
        Total: 4N + 3
    
    Action space:
        - Phase selection (discrete: 0 to P-1)
        - Duration is determined by policy (continuous)
    """
    
    def __init__(self, agent_id: str, config: Optional[AgentConfig] = None,
                 num_approaches: int = 4, num_phases: int = 4):
        super().__init__(agent_id, config or AgentConfig())
        
        self.num_approaches = num_approaches
        self.num_phases = num_phases
        self.state_dim = 4 * num_approaches + 4  # 4 arrays of N + 4 scalars
        self.action_dim = num_phases
        
        # RL components
        self.q_network = SimpleDQN(self.state_dim, self.action_dim, self.config)
        self.replay_buffer = ReplayBuffer(self.config.buffer_size)
        self.epsilon = self.config.epsilon_start
        
        # Current observation (for act())
        self._current_obs: Optional[Observation] = None
        self._last_phase: int = 0
        
        # Metrics
        self._episode_wait_times: List[float] = []
        self._episode_throughput: int = 0
        
        self.state = AgentState.READY
    
    def observe(self, observation: Observation) -> None:
        """Store current observation for action selection."""
        self._current_obs = observation
    
    def act(self) -> Action:
        """
        Select traffic signal action using epsilon-greedy policy.
        
        Returns:
            Action with phase and duration
        """
        if self._current_obs is None:
            return self._safe_default_action()
        
        obs = self._current_obs
        
        # Epsilon-greedy exploration
        if random.random() < self.epsilon:
            phase = random.randint(0, self.num_phases - 1)
            duration = self._calculate_duration(obs, phase)
        else:
            # Greedy action
            state = obs.to_numpy()
            q_values = self.q_network.forward(state)
            phase = int(np.argmax(q_values))
            duration = self._calculate_duration(obs, phase)
        
        # Emergency override
        if obs.emergency_pending and obs.emergency_approach is not None:
            phase = self._emergency_phase(obs.emergency_approach)
            duration = self.config.min_green
            return Action(
                phase=phase,
                duration=duration,
                min_green=self.config.min_green,
                max_green=self.config.max_green,
                emergency_override=True,
            )
        
        self._last_phase = phase
        return Action(
            phase=phase,
            duration=duration,
            min_green=self.config.min_green,
            max_green=self.config.max_green,
        )
    
    def learn(self, observation: Observation, action: Action, 
              reward: float, next_observation: Observation, done: bool) -> None:
        """Store experience and learn from batch."""
        state = observation.to_numpy()
        next_state = next_observation.to_numpy()
        
        self.replay_buffer.push(
            state, action.phase, reward, next_state, done
        )
        
        # Learn from batch if enough data
        if len(self.replay_buffer) >= self.config.batch_size:
            self._train_step()
        
        # Update metrics
        self._total_reward += reward
        self._step_count += 1
    
    def reset(self) -> None:
        """Reset for new episode."""
        super().reset()
        self.epsilon = max(
            self.config.epsilon_end,
            self.epsilon * self.config.epsilon_decay,
        )
        self._current_obs = None
        self._last_phase = 0
        self._episode_wait_times = []
        self._episode_throughput = 0
    
    def save(self, path: str) -> None:
        """Save agent state."""
        import json
        state = {
            "agent_id": self.agent_id,
            "epsilon": self.epsilon,
            "episode_count": self._episode_count,
            "weights": {
                "w1": self.q_network.weights1.tolist(),
                "b1": self.q_network.bias1.tolist(),
                "w2": self.q_network.weights2.tolist(),
                "b2": self.q_network.bias2.tolist(),
                "w3": self.q_network.weights3.tolist(),
                "b3": self.q_network.bias3.tolist(),
            },
        }
        with open(path, "w") as f:
            json.dump(state, f)
    
    def load(self, path: str) -> None:
        """Load agent state."""
        import json
        with open(path, "r") as f:
            state = json.load(f)
        
        self.epsilon = state["epsilon"]
        self._episode_count = state["episode_count"]
        self.q_network.weights1 = np.array(state["weights"]["w1"])
        self.q_network.bias1 = np.array(state["weights"]["b1"])
        self.q_network.weights2 = np.array(state["weights"]["w2"])
        self.q_network.bias2 = np.array(state["weights"]["b2"])
        self.q_network.weights3 = np.array(state["weights"]["w3"])
        self.q_network.bias3 = np.array(state["weights"]["b3"])
    
    def get_metrics(self) -> Dict[str, float]:
        """Return extended metrics."""
        base = super().get_metrics()
        base.update({
            "agent/epsilon": self.epsilon,
            "agent/buffer_size": len(self.replay_buffer),
            "agent/avg_wait_episode": (
                np.mean(self._episode_wait_times) 
                if self._episode_wait_times else 0.0
            ),
        })
        return base
    
    # ─── Private Methods ───────────────────────────────────────
    
    def _calculate_duration(self, obs: Observation, phase: int) -> float:
        """
        Calculate green duration based on demand.
        
        Simple heuristic: more vehicles = longer green.
        """
        # Base duration from queue length
        if phase < len(obs.queue_lengths):
            queue = obs.queue_lengths[phase]
        else:
            queue = 0
        
        # Scale: 10s for empty, up to 60s for 20+ vehicles
        duration = self.config.min_green + (queue / 20.0) * (
            self.config.max_green - self.config.min_green
        )
        
        return max(self.config.min_green, min(self.config.max_green, duration))
    
    def _emergency_phase(self, approach: int) -> int:
        """Return phase that gives green to emergency approach."""
        # Simple mapping: approach i → phase i
        return approach % self.num_phases
    
    def _safe_default_action(self) -> Action:
        """Return safe default when no observation available."""
        return Action(
            phase=self._last_phase,
            duration=self.config.min_green,
            min_green=self.config.min_green,
            max_green=self.config.max_green,
        )
    
    def _train_step(self) -> None:
        """Perform one training step on a batch."""
        # Sample batch
        states, actions, rewards, next_states, dones = \
            self.replay_buffer.sample(self.config.batch_size)
        
        # Compute target Q values
        next_q_values = self.q_network.target_forward(next_states)
        max_next_q = np.max(next_q_values, axis=1)
        targets = rewards + (1 - dones) * self.config.gamma * max_next_q
        
        # Current Q values
        current_q = self.q_network.forward(states)
        
        # Simple gradient update (placeholder — use autograd in production)
        # This is a simplified update for demonstration
        pass
    
    def _compute_reward(self, obs: Observation, action: Action,
                        next_obs: Observation) -> float:
        """
        Compute reward for the (s, a, s') transition.
        
        Multi-objective reward function:
        R = -α·wait_time - β·queue + γ·throughput - δ·phase_changes + ζ·balance
        """
        # Wait time reduction (negative = good)
        wait_change = np.sum(next_obs.queue_lengths) - np.sum(obs.queue_lengths)
        wait_reward = -self.config.wait_time_weight * wait_change
        
        # Queue balance (penalize uneven queues)
        if np.sum(next_obs.queue_lengths) > 0:
            balance = 1.0 - np.std(next_obs.queue_lengths) / (
                np.mean(next_obs.queue_lengths) + 1e-6
            )
        else:
            balance = 1.0
        balance_reward = self.config.balance_weight * balance
        
        # Phase change penalty
        phase_penalty = 0.0
        if action.phase != obs.current_phase:
            phase_penalty = -self.config.phase_change_penalty
        
        return wait_reward + balance_reward + phase_penalty
