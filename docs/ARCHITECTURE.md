# 🏗️ Architecture — Smart City Agent

> **System Design Document — Google Architecture Level**

## Table of Contents

1. [Design Principles](#design-principles)
2. [System Overview](#system-overview)
3. [Core Components](#core-components)
4. [Data Flow](#data-flow)
5. [Multi-Agent Protocol](#multi-agent-protocol)
6. [Reinforcement Learning Design](#reinforcement-learning-design)
7. [Observability & Monitoring](#observability--monitoring)
8. [Performance Requirements](#performance-requirements)
9. [Failure Modes & Recovery](#failure-modes--recovery)
10. [Security Considerations](#security-considerations)

---

## 1. Design Principles

### Google's Approach Applied

| Principle | Application |
|-----------|-------------|
| **Design for failure** | Every intersection agent can fail independently; neighbors compensate |
| **Observability first** | Every decision is logged with reasoning trace |
| **Measure everything** | 50+ metrics collected per intersection per second |
| **Ship early, iterate** | MVP is single intersection; scale is opt-in |
| **Simplicity is a feature** | Agent interface is < 20 lines; complexity is internal |

### Key Architectural Decisions

1. **Decentralized control** — No single point of failure
2. **Event-driven architecture** — Agents react to vehicle arrivals, not polling
3. **Simulation-in-the-loop** — All policies validated in sim before deployment
4. **Human-in-the-loop** — Override capability at all times

---

## 2. System Overview

```
                          ┌─────────────────┐
                          │   Traffic Data   │
                          │   (Sim/Real)     │
                          └────────┬────────┘
                                   │
                          ┌────────▼────────┐
                          │  Event Stream   │
                          │  (Kafka/Redis)  │
                          └────────┬────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                     │
     ┌────────▼────────┐ ┌────────▼────────┐ ┌────────▼────────┐
     │  Agent A        │ │  Agent B        │ │  Agent C        │
     │  (Intersection) │ │  (Intersection) │ │  (Intersection) │
     │                 │ │                 │ │                 │
     │  State → Policy │ │  State → Policy │ │  State → Policy │
     │  Reward ← Env   │ │  Reward ← Env   │ │  Reward ← Env   │
     └────────┬────────┘ └────────┬────────┘ └────────┬────────┘
              │                    │                     │
              └────────────────────┼────────────────────┘
                                   │
                          ┌────────▼────────┐
                          │  Coordination   │
                          │  Layer          │
                          │  (GNN + Message)│
                          └────────┬────────┘
                                   │
                          ┌────────▼────────┐
                          │  Dashboard      │
                          │  (Real-time)    │
                          └─────────────────┘
```

---

## 3. Core Components

### 3.1 Simulation Engine

**Purpose**: Faithfully model urban traffic dynamics.

```python
class SimulationEngine:
    """
    Core simulation loop.
    
    Responsibilities:
    - Maintain road network graph
    - Spawn vehicles according to demand patterns
    - Process agent actions (signal changes)
    - Calculate metrics (wait time, throughput, queue length)
    - Handle special events (emergencies, accidents)
    """
    
    def __init__(self, config: SimulationConfig):
        self.road_network: RoadNetwork
        self.vehicle_manager: VehicleManager
        self.event_bus: EventBus
        self.metrics_collector: MetricsCollector
        self.clock: SimulationClock
        
    def step(self, dt: float) -> SimulationState:
        """
        Advance simulation by dt seconds.
        
        1. Process events (new vehicles, emergencies)
        2. Update vehicle positions
        3. Collect agent observations
        4. Execute agent actions
        5. Calculate rewards
        6. Emit metrics
        """
        pass
    
    def reset(self) -> Observation:
        """Reset to initial state, return initial observation."""
        pass
```

**Road Network Model**:

```python
class RoadNetwork:
    """
    Graph representation of road network.
    
    Nodes = Intersections
    Edges = Road segments
    
    Each edge has:
    - capacity (max vehicles)
    - length (meters)
    - speed_limit (km/h)
    - current_vehicles (list)
    """
    
    def __init__(self):
        self.graph: nx.DiGraph  # Directed graph
        self.intersections: Dict[str, Intersection]
        self.road_segments: Dict[str, RoadSegment]
```

### 3.2 Agent Layer

**Purpose**: Each intersection runs an independent RL agent.

```python
class IntersectionAgent:
    """
    RL agent for a single intersection.
    
    State Space (per intersection):
    - Queue length per approach (N approaches × 1)
    - Current phase duration (1)
    - Time since last phase change (1)
    - Pedestrian waiting (N approaches × 1)
    - Emergency vehicle pending (1)
    Total: 2N + 3 dimensions
    
    Action Space:
    - Phase selection (discrete: 0 to P-1)
    - Phase extension (continuous: 0 to max_extension)
    
    Reward Function:
    R = -α·wait_time - β·queue_length + γ·throughput - δ·phase_changes
    """
    
    def __init__(self, intersection_id: str, config: AgentConfig):
        self.intersection_id = intersection_id
        self.policy_network: PolicyNetwork
        self.replay_buffer: ReplayBuffer
        self.reward_shaper: RewardShaper
        
    def observe(self, state: IntersectionState) -> Observation:
        """Process raw state into agent observation."""
        pass
    
    def act(self, observation: Observation) -> Action:
        """Select action given observation."""
        pass
    
    def learn(self, batch: Batch) -> Loss:
        """Update policy from experience batch."""
        pass
```

### 3.3 Coordination Layer

**Purpose**: Enable spatial-temporal coordination between agents.

```python
class CoordinationLayer:
    """
    Graph Neural Network based coordination.
    
    Architecture:
    1. Each agent encodes local state → embedding
    2. GNN aggregates neighbor embeddings (message passing)
    3. Updated embeddings inform action selection
    
    This allows agents to:
    - Anticipate upstream traffic
    - Create green wave corridors
    - Respond to cascading congestion
    """
    
    def __init__(self, graph: nx.DiGraph, config: CoordinationConfig):
        self.gnn: GraphNeuralNetwork
        self.message_queue: MessageQueue
        self.consensus: ConsensusProtocol
        
    def aggregate(self, agent_states: Dict[str, Tensor]) -> Dict[str, Tensor]:
        """Aggregate neighbor information via GNN."""
        pass
    
    def coordinate(self, agent_actions: Dict[str, Action]) -> Dict[str, Action]:
        """Adjust actions for corridor-level optimization."""
        pass
```

### 3.4 Observability Layer

**Purpose**: Production-grade monitoring and debugging.

```python
class ObservabilityLayer:
    """
    Comprehensive observability stack.
    
    Metrics (Prometheus):
    - traffic_agent_wait_time_seconds (histogram)
    - traffic_agent_throughput_per_hour (gauge)
    - traffic_agent_queue_length (gauge)
    - traffic_agent_phase_changes_total (counter)
    - traffic_agent_rl_loss (gauge)
    - traffic_agent_coordination_latency_ms (histogram)
    
    Tracing (OpenTelemetry):
    - Each agent decision traced
    - Message passing between agents
    - End-to-end latency
    
    Logging (structured JSON):
    - Agent decisions with reasoning
    - Anomaly detection alerts
    - System health events
    """
    
    def __init__(self, config: ObservabilityConfig):
        self.metrics: MetricsCollector
        self.tracer: Tracer
        self.logger: StructuredLogger
        self.alerter: AlertManager
```

---

## 4. Data Flow

### 4.1 Real-time Decision Loop (per tick)

```
┌─────────────────────────────────────────────────────────────┐
│                    Decision Loop (5 Hz)                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  t=0ms    ┌──────────┐                                      │
│           │ Collect  │  Each agent reads:                   │
│           │ State    │  - Vehicle positions                 │
│           └────┬─────┘  - Queue lengths                     │
│                │       - Current phase                       │
│  t=5ms    ┌────▼─────┐                                      │
│           │ Neighbor │  Share state with adjacent agents    │
│           │ Sync     │  via message queue                   │
│           └────┬─────┘                                      │
│                │                                            │
│  t=10ms   ┌────▼─────┐                                      │
│           │ GNN      │  Aggregate neighbor information     │
│           │ Aggregate│  Update embeddings                   │
│           └────┬─────┘                                      │
│                │                                            │
│  t=15ms   ┌────▼─────┐                                      │
│           │ Policy   │  Select action:                      │
│           │ Inference│  - Current observation                │
│           └────┬─────┘  - Aggregated neighbor info          │
│                │                                            │
│  t=20ms   ┌────▼─────┐                                      │
│           │ Execute  │  Apply phase change to simulation    │
│           │ Action   │                                      │
│           └────┬─────┘                                      │
│                │                                            │
│  t=25ms   ┌────▼─────┐                                      │
│           │ Calculate│  Compute reward:                     │
│           │ Reward   │  - Wait time reduction               │
│           └────┬─────┘  - Throughput delta                  │
│                │       - Queue balance                      │
│  t=30ms   ┌────▼─────┐                                      │
│           │ Store    │  (s, a, r, s') → Replay Buffer       │
│           │ Experience│                                     │
│           └────┬─────┘                                      │
│                │                                            │
│  t=35ms   ┌────▼─────┐                                      │
│           │ Emit     │  Push metrics to dashboard           │
│           │ Metrics  │                                      │
│           └──────────┘                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Training Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                    Training Pipeline                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ Parallel │    │ Episode  │    │ Replay   │              │
│  │ Sim      │───►│ Runner   │───►│ Buffer   │              │
│  │ (N sims) │    │          │    │ (1M exp) │              │
│  └──────────┘    └──────────┘    └────┬─────┘              │
│                                       │                     │
│  ┌──────────┐    ┌──────────┐    ┌────▼─────┐              │
│  │ Model    │    │ Checkpoint│    │ Training │              │
│  │ Registry │◄───│ Manager  │◄───│ Loop     │              │
│  │          │    │          │    │ (GPU)    │              │
│  └──────────┘    └──────────┘    └──────────┘              │
│                                                             │
│  Frequency:                                                 │
│  - Collect: 1000 steps per update                           │
│  - Train: 10 epochs per update                             │
│  - Evaluate: every 10 updates                              │
│  - Checkpoint: every 50 updates                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Multi-Agent Protocol

### 5.1 Message Types

```python
from enum import Enum
from dataclasses import dataclass

class MessageType(Enum):
    STATE_UPDATE = "state_update"      # Share local state
    ACTION_REQUEST = "action_request"  # Request coordination
    ACTION_COMMIT = "action_commit"    # Commit to action
    ANOMALY_ALERT = "anomaly_alert"    # Report unusual event
    HEARTBEAT = "heartbeat"            # Liveness check

@dataclass
class AgentMessage:
    sender_id: str
    receiver_id: str  # or "*" for broadcast
    msg_type: MessageType
    payload: dict
    timestamp: float
    ttl: float  # Time to live in seconds
```

### 5.2 Communication Pattern

```
Phase 1: State Broadcast (every 5s)
┌─────────┐    STATE_UPDATE    ┌─────────┐
│ Agent A │ ──────────────────►│ Agent B │
│         │ ──────────────────►│ Agent C │
└─────────┘                    └─────────┘

Phase 2: Coordination Request (on anomaly)
┌─────────┐   ACTION_REQUEST   ┌─────────┐
│ Agent A │ ◄─────────────────►│ Agent B │
│         │   "I need green   │         │
│         │    extension for   │         │
│         │    emergency"      │         │
└─────────┘                    └─────────┘

Phase 3: Consensus (for major changes)
┌─────────┐                    ┌─────────┐
│ Agent A │ ◄──► Coordinator ◄─►│ Agent B │
│         │    "Agree to give  │         │
│         │     Agent A extra  │         │
│         │     15s green"     │         │
└─────────┘                    └─────────┘
```

### 5.3 Conflict Resolution

When agents disagree (e.g., both want green extension):

1. **Priority-based**: Emergency > Throughput > Fairness
2. **Game-theoretic**: Nash equilibrium search
3. **Auction-based**: Agents "bid" for green time using urgency scores

---

## 6. Reinforcement Learning Design

### 6.1 State Representation

```python
@dataclass
class IntersectionState:
    """Complete state of one intersection."""
    
    # Per-approach features (N approaches)
    queue_lengths: np.ndarray      # [N] vehicles waiting
    vehicle_positions: np.ndarray   # [N, max_vehicles] distances
    arrival_rates: np.ndarray      # [N] vehicles/second
    
    # Intersection features
    current_phase: int             # Active phase index
    phase_duration: float          # Time in current phase
    time_since_change: float       # Since last phase change
    
    # Coordination features
    neighbor_states: Dict[str, 'IntersectionState']
    emergency_pending: bool
    
    def to_tensor(self) -> torch.Tensor:
        """Convert to flat tensor for RL input."""
        pass
```

### 6.2 Action Space

```python
@dataclass
class TrafficAction:
    """Action taken by an intersection agent."""
    
    phase: int              # Which phase to activate
    duration: float         # How long to hold (seconds)
    min_green: float = 10.0 # Minimum green time
    max_green: float = 60.0 # Maximum green time
    
    # Coordination overrides
    emergency_override: bool = False
    pedestrian_request: bool = False
```

### 6.3 Reward Function

```python
class RewardFunction:
    """
    Multi-objective reward function.
    
    R = -α₁·Δwait_time        # Minimize increased wait
        - α₂·Δqueue_length    # Minimize queue growth
        + α₃·Δthroughput      # Maximize throughput
        - α₄·phase_changes    # Penalize frequent switching
        + α₅·balance_score    # Reward balanced queues
        + α₆·emergency_bonus  # Bonus for clearing emergency
    
    Weights are adaptive based on:
    - Time of day (rush hour vs off-peak)
    - Special events (sports, concerts)
    - Emergency situations
    """
    
    def __init__(self, config: RewardConfig):
        self.weights = config.weights
        self.adaptive = config.adaptive
        
    def calculate(
        self,
        state: IntersectionState,
        action: TrafficAction,
        next_state: IntersectionState,
        info: dict
    ) -> float:
        pass
```

### 6.4 Algorithm Selection

| Scenario | Algorithm | Why |
|----------|-----------|-----|
| Single intersection | DQN / PPO | Simple, fast convergence |
| Multi-intersection (small) | MAPPO | Multi-agent PPO, stable |
| Multi-intersection (large) | Graph-QL | Scalable to 100+ agents |
| Emergency priority | Hierarchical RL | Separate emergency policy |

---

## 7. Observability & Monitoring

### 7.1 Metrics Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│  🚦 Smart City Traffic Dashboard                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Active Intersections: 9     Total Vehicles: 1,247          │
│  Avg Wait Time: 42s          Throughput: 1,320 veh/hr       │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Traffic Heatmap                                    │   │
│  │  🟢🟢🟡🟡🔴🔴🟡🟢🟢                             │   │
│  │  🟢🟡🟡🔴🔴🔴🟡🟡🟢                             │   │
│  │  🟡🟡🔴🔴🔴🔴🔴🟡🟡                             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Wait Time    │  │ Throughput   │  │ Queue Length │     │
│  │ ▂▃▄▅▆▇█▇▆▅▄ │  │ ▁▂▃▄▅▆▇█▇▆ │  │ █▇▆▅▄▃▂▁▂▃ │     │
│  │ 42s avg      │  │ 1320/hr      │  │ 18 max       │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Key Metrics

```python
METRICS = {
    # Traffic flow
    "traffic.wait_time_seconds": Histogram,
    "traffic.throughput_per_hour": Gauge,
    "traffic.queue_length": Gauge,
    "traffic.occupancy_ratio": Gauge,
    
    # Agent performance
    "agent.decision_latency_ms": Histogram,
    "agent.rl_loss": Gauge,
    "agent.episode_reward": Gauge,
    "agent.exploration_rate": Gauge,
    
    # Coordination
    "coordination.message_latency_ms": Histogram,
    "coordination.consensus_rounds": Counter,
    "coordination.conflict_rate": Gauge,
    
    # System health
    "system.cpu_usage": Gauge,
    "system.memory_usage": Gauge,
    "system.simulation_speed": Gauge,
}
```

---

## 8. Performance Requirements

| Requirement | Target | Measurement |
|-------------|--------|-------------|
| Decision latency | < 50ms | 99th percentile |
| Simulation speed | > 100x real-time | Training throughput |
| Agent convergence | < 10K episodes | Single intersection |
| Dashboard refresh | < 1s | WebSocket latency |
| Fault recovery | < 5s | Agent restart time |
| Memory per agent | < 100MB | Resident memory |

---

## 9. Failure Modes & Recovery

| Failure | Impact | Recovery |
|---------|--------|----------|
| Agent crash | Intersection falls back to fixed timing | Auto-restart from checkpoint |
| Coordination failure | Agents operate independently | Graceful degradation |
| Simulation lag | Training slows down | Reduce parallel sims |
| Memory overflow | OOM kill | Checkpoint + restart |
| Network partition | Agents can't coordinate | Local决策 + reconnect |

---

## 10. Security Considerations

- **Input validation**: All vehicle data sanitized
- **Rate limiting**: Max 1000 decisions/second per agent
- **Authentication**: API requires JWT tokens
- **Encryption**: TLS for all inter-agent communication
- **Audit logging**: All actions logged with reasoning
- **Override capability**: Human operator can always override

---

## Appendix: Technology Choices

| Decision | Choice | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| RL Framework | PyTorch + SB3 | TensorFlow, JAX | Flexibility, ecosystem |
| Multi-Agent | Ray | custom | Scalability, fault tolerance |
| Graph Learning | PyTorch Geometric | DGL | PyTorch native, docs |
| Dashboard | React + WebSocket | Grafana | Customization, embedding |
| API | FastAPI | Flask, Django | Async, auto-docs, speed |
| Simulation | Custom | SUMO | Zero deps, full control |
| Testing | pytest | unittest | Fixtures, plugins, speed |
