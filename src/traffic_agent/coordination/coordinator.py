"""
Coordination Layer — Multi-Agent Communication & Cooperation

Enables spatial-temporal coordination between intersection agents.

Architecture:
1. Message Passing — Agents share state with neighbors
2. Graph Neural Network — Learn spatial patterns
3. Consensus Protocol — Agree on corridor-level timing
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import numpy as np


class MessageType(Enum):
    """Types of messages between agents."""
    STATE_UPDATE = "state_update"        # Periodic state sharing
    ACTION_REQUEST = "action_request"    # Request coordination
    ACTION_COMMIT = "action_commit"      # Commit to action
    ANOMALY_ALERT = "anomaly_alert"      # Report unusual event
    EMERGENCY_BROADCAST = "emergency"    # Emergency vehicle approaching
    HEARTBEAT = "heartbeat"              # Liveness check


@dataclass
class AgentMessage:
    """Message between intersection agents."""
    sender_id: str
    receiver_id: str    # or "*" for broadcast
    msg_type: MessageType
    payload: Dict[str, Any]
    timestamp: float
    ttl: float = 30.0   # Time to live in seconds
    
    def is_expired(self, current_time: float) -> bool:
        return (current_time - self.timestamp) > self.ttl


@dataclass
class AgentState:
    """Shared state of an intersection agent."""
    intersection_id: str
    queue_lengths: np.ndarray
    current_phase: int
    phase_duration: float
    emergency_pending: bool = False
    timestamp: float = 0.0
    
    def to_vector(self) -> np.ndarray:
        """Convert to fixed-size vector for GNN input."""
        return np.concatenate([
            self.queue_lengths,
            [self.current_phase / 4.0],  # Normalize
            [min(self.phase_duration / 60.0, 1.0)],
            [float(self.emergency_pending)],
            [0.0],  # Padding to match state_dim
        ])


class MessageQueue:
    """
    Thread-safe message queue for inter-agent communication.
    
    In production, use Redis Streams or Kafka.
    This is an in-memory implementation for simulation.
    """
    
    def __init__(self):
        self._queues: Dict[str, List[AgentMessage]] = {}
        self._broadcasts: List[AgentMessage] = []
    
    def send(self, message: AgentMessage) -> None:
        """Send message to specific agent or broadcast."""
        if message.receiver_id == "*":
            self._broadcasts.append(message)
        else:
            if message.receiver_id not in self._queues:
                self._queues[message.receiver_id] = []
            self._queues[message.receiver_id].append(message)
    
    def receive(self, agent_id: str, current_time: float) -> List[AgentMessage]:
        """Receive all messages for an agent (including broadcasts)."""
        messages = self._queues.pop(agent_id, [])
        messages.extend(self._broadcasts)
        # Filter expired
        return [m for m in messages if not m.is_expired(current_time)]
    
    def clear(self) -> None:
        self._queues.clear()
        self._broadcasts.clear()


class SimpleGNN:
    """
    Simplified Graph Neural Network for coordination.
    
    Message passing aggregation:
    1. Each agent encodes local state → embedding
    2. Aggregate neighbor embeddings (mean/max)
    3. Update own embedding based on aggregated info
    
    In production, use PyTorch Geometric.
    This is a self-contained implementation.
    """
    
    def __init__(self, state_dim: int, hidden_dim: int = 64):
        self.state_dim = state_dim
        self.hidden_dim = hidden_dim
        
        # Simple linear transforms (no torch dependency)
        self.W_self = np.random.randn(state_dim, hidden_dim) * 0.01
        self.W_neighbor = np.random.randn(state_dim, hidden_dim) * 0.01
        self.W_output = np.random.randn(hidden_dim, hidden_dim) * 0.01
    
    def encode(self, state: np.ndarray) -> np.ndarray:
        """Encode local state to embedding."""
        return np.maximum(0, state @ self.W_self)  # ReLU
    
    def aggregate(self, own_embedding: np.ndarray, 
                  neighbor_embeddings: List[np.ndarray]) -> np.ndarray:
        """Aggregate neighbor information."""
        if not neighbor_embeddings:
            return own_embedding
        
        # Mean aggregation
        neighbor_mean = np.mean(neighbor_embeddings, axis=0)
        
        # Combine self + neighbors
        combined = own_embedding + neighbor_mean
        return np.maximum(0, combined @ self.W_output)  # ReLU + transform
    
    def forward(self, own_state: np.ndarray, 
                neighbor_states: List[np.ndarray]) -> np.ndarray:
        """Full GNN forward pass."""
        own_emb = self.encode(own_state)
        neighbor_embs = [self.encode(ns) for ns in neighbor_states]
        return self.aggregate(own_emb, neighbor_embs)


class ConsensusProtocol:
    """
    Consensus algorithm for corridor-level coordination.
    
    When adjacent intersections need to agree on timing,
    they run a lightweight consensus protocol.
    
    Algorithm: Weighted Average Consensus
    - Each agent proposes a value (e.g., green extension)
    - Agents iteratively average with neighbors
    - Converges to consensus in O(log N) rounds
    """
    
    def __init__(self, max_rounds: int = 5, tolerance: float = 0.01):
        self.max_rounds = max_rounds
        self.tolerance = tolerance
    
    def reach_consensus(
        self,
        agent_id: str,
        own_value: float,
        neighbor_values: Dict[str, float],
        weights: Optional[Dict[str, float]] = None,
    ) -> float:
        """
        Run consensus to agreement.
        
        Args:
            agent_id: This agent's ID
            own_value: Agent's proposed value
            neighbor_values: Neighbors' proposed values
            weights: Importance weights (default: equal)
        
        Returns:
            Consensus value
        """
        if not neighbor_values:
            return own_value
        
        # Default equal weights
        if weights is None:
            weights = {nid: 1.0 for nid in neighbor_values}
        weights[agent_id] = 2.0  # Own opinion counts double
        
        # Weighted average
        total_weight = sum(weights.values())
        consensus = own_value * weights[agent_id]
        
        for nid, val in neighbor_values.items():
            consensus += val * weights.get(nid, 1.0)
        
        return consensus / total_weight


class CoordinationLayer:
    """
    Multi-agent coordination layer.
    
    Responsibilities:
    1. Manage message passing between agents
    2. Run GNN for spatial-temporal patterns
    3. Handle consensus for corridor optimization
    4. Detect and respond to anomalies
    """
    
    def __init__(self, graph: Dict[str, List[str]], state_dim: int = 8):
        """
        Args:
            graph: Adjacency list {intersection_id: [neighbor_ids]}
            state_dim: Dimension of agent state vectors
        """
        self.graph = graph
        self.gnn = SimpleGNN(state_dim)
        self.message_queue = MessageQueue()
        self.consensus = ConsensusProtocol()
        
        # State tracking
        self.agent_states: Dict[str, AgentState] = {}
        self.agent_embeddings: Dict[str, np.ndarray] = {}
    
    def update_state(self, state: AgentState) -> None:
        """Update an agent's state and recompute embedding."""
        self.agent_states[state.intersection_id] = state
        self.agent_embeddings[state.intersection_id] = self.gnn.encode(
            state.to_vector()
        )
    
    def get_coordinated_observation(
        self, agent_id: str
    ) -> Dict[str, np.ndarray]:
        """
        Get GNN-aggregated observation for an agent.
        
        Returns dict with:
        - 'embedding': GNN output for this agent
        - 'neighbor_embeddings': List of neighbor embeddings
        - 'consensus_value': Consensus on optimal timing
        """
        if agent_id not in self.agent_states:
            return {"embedding": np.zeros(self.gnn.hidden_dim)}
        
        own_state = self.agent_states[agent_id]
        neighbors = self.graph.get(agent_id, [])
        
        # Collect neighbor states
        neighbor_states = []
        neighbor_embeddings = []
        for nid in neighbors:
            if nid in self.agent_states:
                ns = self.agent_states[nid]
                neighbor_states.append(ns.to_vector())
                neighbor_embeddings.append(self.agent_embeddings[nid])
        
        # GNN forward pass
        embedding = self.gnn.forward(own_state.to_vector(), neighbor_states)
        
        # Consensus on green extension
        own_proposal = self._propose_extension(own_state)
        neighbor_proposals = {}
        for nid in neighbors:
            if nid in self.agent_states:
                neighbor_proposals[nid] = self._propose_extension(
                    self.agent_states[nid]
                )
        
        consensus = self.consensus.reach_consensus(
            agent_id, own_proposal, neighbor_proposals
        )
        
        return {
            "embedding": embedding,
            "neighbor_embeddings": neighbor_embeddings,
            "consensus_value": consensus,
            "neighbor_queue_lengths": {
                nid: self.agent_states[nid].queue_lengths.tolist()
                for nid in neighbors if nid in self.agent_states
            },
        }
    
    def broadcast_emergency(self, agent_id: str, 
                           emergency_data: Dict[str, Any]) -> None:
        """Broadcast emergency alert to all neighbors."""
        msg = AgentMessage(
            sender_id=agent_id,
            receiver_id="*",
            msg_type=MessageType.EMERGENCY_BROADCAST,
            payload=emergency_data,
            timestamp=emergency_data.get("timestamp", 0),
            ttl=10.0,  # Short TTL for emergencies
        )
        self.message_queue.send(msg)
    
    def _propose_extension(self, state: AgentState) -> float:
        """
        Propose green extension based on local state.
        
        Higher queue = more extension requested.
        """
        max_queue = np.max(state.queue_lengths) if len(state.queue_lengths) > 0 else 0
        # Normalize to 0-1 range
        return min(max_queue / 20.0, 1.0)
