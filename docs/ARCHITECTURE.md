# Architecture — LLM Traffic Timing Assistant

> **System Design Document — ±10s Timing Adjustment + CrewAI Multi-Agent**

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [System Overview](#system-overview)
3. [Core Components](#core-components)
4. [3-Tier Decision Pipeline](#3-tier-decision-pipeline)
5. [Multi-Agent Architecture (CrewAI)](#multi-agent-architecture-crewai)
6. [Simulation Engine](#simulation-engine)
7. [Safety Constraints](#safety-constraints)
8. [Observability](#observability)
9. [Cost & Performance](#cost--performance)

---

## 1. Design Philosophy

### Core Insight

> **Small adjustments, big impact.**
> The LLM does NOT control the signal — it fine-tunes existing baseline timing by ±10 seconds.

Traditional adaptive systems make large, binary decisions (switch phase / extend green).
Our approach keeps a fixed baseline and lets the LLM add a small adjustment layer on top.

### Why ±10s Adjustment

| Aspect | Full LLM Control | ±10s Adjustment |
|--------|------------------|-----------------|
| Risk | High — wrong decision breaks flow | Low — baseline is always safe |
| Explainability | Hard to justify full control | Easy — "why ±5s?" is clear |
| Rollback | Complex | Trivial — ignore adjustment |
| Trust | Operators distrust AI | Operators can verify each adjustment |
| Cost | Many LLM calls | Few calls — rules handle most cases |

### Design Principles

1. **Safety First** — Baseline timing is always valid; adjustments are bounded
2. **Fail-Safe** — Rule engine handles obvious cases without LLM
3. **Cost-Aware** — 70%+ decisions are free (rules + cache)
4. **Observable** — Every adjustment has reasoning and confidence
5. **Composable** — Rules, cache, and LLM are pluggable layers

---

## 2. System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                LLM Traffic Timing Assistant                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Detector Data Perception                    │   │
│  │  • Vehicle queue lengths    • Pedestrian requests        │   │
│  │  • Bicycle counts           • Traffic flow trends        │   │
│  └───────────────────────────┬─────────────────────────────┘   │
│                              │                                  │
│  ┌───────────────────────────▼─────────────────────────────┐   │
│  │              3-Tier Decision Pipeline                    │   │
│  │                                                          │   │
│  │  L1: Rule Engine (FREE, <1ms)                           │   │
│  │    └─ 6 rules for obvious patterns                       │   │
│  │                                                          │   │
│  │  L2: Decision Cache (FREE, <1ms)                        │   │
│  │    └─ LRU + TTL for similar states                       │   │
│  │                                                          │   │
│  │  L3: LLM Reasoning (~$0.001, ~1s)                       │   │
│  │    └─ Complex scenarios requiring semantic understanding │   │
│  └───────────────────────────┬─────────────────────────────┘   │
│                              │                                  │
│  ┌───────────────────────────▼─────────────────────────────┐   │
│  │              Safety Constraint Clamping                   │   │
│  │  • Adjustment: [-10, +10] seconds                        │   │
│  │  • Min green: 15s  • Max green: 90s                      │   │
│  └───────────────────────────┬─────────────────────────────┘   │
│                              │                                  │
│  ┌───────────────────────────▼─────────────────────────────┐   │
│  │              Signal Controller                           │   │
│  │  • Baseline timing + adjustment                          │   │
│  │  • Phase state machine                                   │   │
│  │  • Crossroad / T-junction support                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Components

### 3.1 Signal Controller

The heart of the system. Manages signal phases and applies ±10s adjustments.

```python
class SignalController:
    """Manages signal state with baseline timing + adjustment."""
    
    def __init__(self, intersection_type: str = "crossroad"):
        self.baseline = self._load_baseline(intersection_type)
        self.current_phase = SignalPhase.NS_GREEN
        self.phase_elapsed = 0.0
        self.adjustment = 0  # [-10, +10] seconds
    
    def get_effective_duration(self) -> float:
        """Baseline duration + adjustment, clamped to safe bounds."""
        base = self.baseline[self.current_phase]
        effective = base + self.adjustment
        return max(MIN_GREEN, min(MAX_GREEN, effective))
    
    def apply_adjustment(self, seconds: int):
        """Apply LLM-suggested adjustment."""
        self.adjustment = max(-10, min(10, seconds))
```

### 3.2 Detector Model

Simulates real-world detectors (vehicles, pedestrians, bicycles).

```python
class DetectorSimulator:
    """Generates detector readings from simulation vehicles."""
    
    def get_reading(self, intersection_id: str) -> DetectorReading:
        return DetectorReading(
            vehicle_queue={direction: count for ...},
            pedestrian_waiting={crosswalk: count for ...},
            bicycle_queue={direction: count for ...},
            flow_trend=self.trend_analyzer.get_trend(direction),
        )
```

### 3.3 Trend Analyzer

Tracks traffic flow trends over a sliding window.

```python
class TrendAnalyzer:
    """Tracks traffic flow trends using sliding window."""
    
    def __init__(self, window_size: int = 10):
        self.windows = defaultdict(deque)
    
    def add_sample(self, direction: int, flow_rate: float):
        self.windows[direction].append(flow_rate)
    
    def get_trend(self, direction: int) -> str:
        """Return 'increasing', 'stable', or 'decreasing'."""
        ...
```

---

## 4. 3-Tier Decision Pipeline

### Decision Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Decision Pipeline                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Input: DetectorReading + SignalState                           │
│    │                                                            │
│    ▼                                                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  L1: Rule Engine                                         │   │
│  │  • 6 rules for obvious patterns                          │   │
│  │  • Returns: adjustment (int) or None                     │   │
│  │  • Cost: FREE                                            │   │
│  └───────────────────────────┬─────────────────────────────┘   │
│                              │                                  │
│                    ┌─────────▼─────────┐                       │
│                    │   Rule matched?   │                       │
│                    └─────────┬─────────┘                       │
│                        Yes /   \ No                            │
│                           /     \                               │
│                          ▼       ▼                              │
│                   [Return]  ┌─────────────────────────────┐    │
│                             │  L2: Decision Cache          │    │
│                             │  • LRU + TTL                 │    │
│                             │  • Returns: adjustment or    │    │
│                             │    None                      │    │
│                             │  • Cost: FREE                │    │
│                             └───────────┬─────────────────┘    │
│                                         │                       │
│                               ┌─────────▼─────────┐            │
│                               │   Cache hit?      │            │
│                               └─────────┬─────────┘            │
│                                   Yes /   \ No                 │
│                                      /     \                    │
│                                     ▼       ▼                   │
│                              [Return]  ┌─────────────────────┐ │
│                                        │  L3: LLM Reasoning  │ │
│                                        │  • Prompt + parse    │ │
│                                        │  • Returns:          │ │
│                                        │    TimingAdjustment  │ │
│                                        │  • Cost: ~$0.001     │ │
│                                        └───────────┬─────────┘ │
│                                                    │            │
│                                                    ▼            │
│                                          [Return adjustment]    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.1 Rule Engine (L1)

6 rules for instant decisions without LLM:

| Rule | Condition | Adjustment | Cost |
|------|-----------|------------|------|
| Low Traffic | All queues < 2 | -5s | FREE |
| High Queue | One queue > 20 | +10s | FREE |
| Pedestrian Wait | Pedestrian waiting > 30s | +5s | FREE |
| Phase Too Long | Elapsed > 2x baseline | -10s | FREE |
| Phase Too Short | Elapsed < 0.5x baseline | +5s | FREE |
| Balanced Flow | All queues similar | 0s | FREE |

### 4.2 Decision Cache (L2)

LRU cache with TTL to avoid redundant LLM calls:

```python
class DecisionCache:
    """LRU + TTL decision cache."""
    
    def __init__(self, max_size: int = 1000, ttl_seconds: float = 60.0):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl_seconds
    
    def get(self, state: TrafficState) -> Optional[int]:
        """Return cached adjustment or None."""
        key = self._state_to_key(state)
        if key in self.cache:
            entry = self.cache[key]
            if time.time() - entry.timestamp < self.ttl:
                return entry.adjustment
            del self.cache[key]
        return None
```

### 4.3 LLM Reasoning (L3)

When rules and cache don't handle the case, the LLM provides reasoning:

```python
@dataclass
class TimingAdjustment:
    """LLM output: adjustment + reasoning."""
    adjustment: int          # [-10, +10] seconds
    reasoning: str           # Natural language explanation
    confidence: float        # [0.0, 1.0]
    alerts: List[str]        # Safety alerts (optional)
```

---

## 5. Multi-Agent Architecture (CrewAI)

### 5.1 Overview

The multi-agent path extends the single-intersection design to a 3×3 grid of intersections, each controlled by a dedicated CrewAI Agent. The same 3-tier pipeline (rules → cache → LLM) runs inside the CrewAI framework.

```
┌─────────────────────────────────────────────────────────────────┐
│                  CrewAI Multi-Agent System                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Agent: ix_0_0 │  │ Agent: ix_0_1 │  │ Agent: ix_0_2 │          │
│  │ 4 tools       │  │ 4 tools       │  │ 4 tools       │          │
│  │ fast_llm      │  │ fast_llm      │  │ fast_llm      │          │
│  └───────┬──────┘  └───────┬──────┘  └───────┬──────┘          │
│          │                 │                 │                   │
│          │   ┌─────────────┴─────────────┐   │                   │
│          │   │    3-Tier Pipeline         │   │                   │
│          │   │  L1: Rules (free)          │   │                   │
│          │   │  L2: Cache (free)          │   │                   │
│          │   │  L3: CrewAI LLM (paid)     │   │                   │
│          │   └─────────────┬─────────────┘   │                   │
│          │                 │                 │                   │
│          ▼                 ▼                 ▼                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Coordinator Agent                           │    │
│  │  smart_llm · 3 tools · conflict resolution              │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 CrewAI Tools (6 tools)

Each intersection Agent has 4 tools; the Coordinator has 3:

| Tool | Agent | Coordinator | Description |
|------|:-----:|:-----------:|-------------|
| Get Intersection State | ✓ | ✓ | Real-time queue, wait, phase, emergency |
| Get Neighbor States | ✓ | ✓ | Summary of adjacent intersections |
| Apply Timing Adjustment | ✓ | | ±10s green phase adjustment |
| Apply Signal Decision | ✓ | | Direct phase switch (NS_GREEN/EW_GREEN) |
| Check Conflicts | | ✓ | Detect phase mismatches between neighbors |
| Get Traffic Trend | ✓ | | Directional queue trend analysis |

Tools are implemented with the `@tool` decorator and access the simulation via a shared `SimulationState` container.

### 5.3 Agent Configuration

```python
# Intersection Agent
Agent(
    role="Traffic Signal Controller for {ix_id}",
    goal="Minimize wait time while coordinating with neighbors",
    backstory="Senior traffic engineer, 20 years adaptive signal control",
    tools=intersection_tools,        # 4 tools
    llm=fast_llm,
    function_calling_llm=fast_llm,  # cheaper tool-calling
    max_iter=12,
    max_execution_time=30,          # seconds
    allow_delegation=False,
)

# Coordinator Agent
Agent(
    role="Traffic Network Coordinator",
    goal="Resolve conflicts, optimize city-wide flow",
    backstory="Traffic management center, 15 years network optimization",
    tools=coordinator_tools,        # 3 tools
    llm=smart_llm,
    function_calling_llm=fast_llm,
    max_iter=15,
    max_execution_time=45,
    allow_delegation=False,
)
```

### 5.4 Task Design & Guardrails

Tasks use structured markdown descriptions with What/How/Context/Constraints. A function-based guardrail validates LLM output:

```python
def _validate_signal_decision(output: str) -> tuple[bool, Any]:
    """Check LLM output has valid JSON with required fields."""
    # Validates: JSON parseable, has action/phase/duration,
    # phase in {NS_GREEN, EW_GREEN}, duration is numeric
```

### 5.5 Coordination

Three coordination mechanisms:

1. **ConflictDetector** — detects phase mismatches and excessive green (>45s) between neighbors
2. **GreenWaveAdvisor** — suggests progressive timing offsets along EW/NS corridors (-2s per position upstream)
3. **PriorityResolver** — resolves conflicts by: emergency vehicles → queue length → wait time → intersection ID tiebreak

### 5.6 GridSimulation Integration

`GridSimulation` creates a `SignalController` per intersection using `crossroad_plan()`. The `apply_decision()` method supports both:
- `{"adjustment": ±10}` — timing adjustment via controller
- `{"phase": "EW_GREEN"}` — direct phase switch

---

## 6. Simulation Engine

### 5.1 TimingSimulation

Ties everything together into a simulation loop:

```python
class TimingSimulation:
    """End-to-end simulation with timing adjustment."""
    
    def __init__(
        self,
        intersection_type: str = "crossroad",
        scenario_name: str = "normal",
        pipeline: Optional[TimingDecisionPipeline] = None,
        seed: int = 42,
    ):
        self.controller = SignalController(intersection_type)
        self.detector = DetectorSimulator(intersection_type)
        self.scenario = create_scenario(scenario_name)
        self.pipeline = pipeline  # None = fixed timing
    
    def run(self, steps: int = 500) -> SimulationReport:
        """Run simulation and return metrics."""
        for step in range(steps):
            # 1. Update scenario traffic
            self.scenario.update(step * DT)
            
            # 2. Detect vehicles
            reading = self.detector.get_reading(self.scenario.vehicles)
            
            # 3. Get adjustment (if pipeline enabled)
            if self.pipeline:
                adjustment = self.pipeline.decide(reading, self.controller)
                self.controller.apply_adjustment(adjustment)
            
            # 4. Advance signal controller
            self.controller.step(DT)
            
            # 5. Update vehicles
            self._update_vehicles(DT)
        
        return self._compute_report()
```

### 5.2 Traffic Scenarios

6 preset scenarios with realistic traffic patterns:

| Scenario | Description | Pattern |
|----------|-------------|---------|
| `morning_peak` | Morning rush | Heavy NS flow, ramp up → peak → ramp down |
| `evening_peak` | Evening rush | Heavy EW flow |
| `normal` | Off-peak | Balanced flow |
| `pedestrian_heavy` | Pedestrian peak | High pedestrian volume |
| `accident` | Emergency | Emergency vehicles + congestion |
| `bicycle_rush` | Bicycle rush | Bicycle traffic peak |

---

## 7. Safety Constraints

### Constraint Clamping

All adjustments are clamped to safe bounds:

```python
MIN_GREEN = 15      # Minimum green phase (seconds)
MAX_GREEN = 90      # Maximum green phase (seconds)
MAX_ADJUSTMENT = 10  # Maximum adjustment (seconds)

def clamp_adjustment(adjustment: int) -> int:
    """Clamp adjustment to safe bounds."""
    return max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT, adjustment))

def clamp_effective_duration(base: float, adjustment: int) -> float:
    """Clamp effective duration to safe bounds."""
    effective = base + adjustment
    return max(MIN_GREEN, min(MAX_GREEN, effective))
```

### Safety Rules

1. **Never exceed MAX_GREEN** — Even if LLM suggests more
2. **Never go below MIN_GREEN** — Even if LLM suggests less
3. **Baseline is always valid** — If pipeline fails, use baseline
4. **All adjustments logged** — For audit and analysis

---

## 8. Observability

### Decision Logging

Every decision is logged with full context:

```python
@dataclass
class DecisionLog:
    timestamp: float
    intersection_type: str
    current_phase: str
    phase_elapsed: float
    detector_reading: DetectorReading
    rule_result: Optional[int]
    cache_hit: bool
    llm_adjustment: Optional[TimingAdjustment]
    final_adjustment: int
    effective_duration: float
```

### Metrics

| Metric | Description |
|--------|-------------|
| `avg_wait_time` | Average vehicle wait time |
| `throughput` | Vehicles per second |
| `p95_wait_time` | 95th percentile wait time |
| `llm_call_rate` | Percentage of decisions using LLM |
| `cache_hit_rate` | Percentage of decisions from cache |
| `rule_hit_rate` | Percentage of decisions from rules |

---

## 9. Cost & Performance

### Cost Model

| Component | Cost | Notes |
|-----------|------|-------|
| Rule Engine | FREE | <1ms latency |
| Decision Cache | FREE | <1ms latency |
| LLM (fast) | ~$0.001/call | ~1s latency |
| LLM (smart) | ~$0.01/call | ~2s latency |

### Performance Targets

| Metric | Target | Strategy |
|--------|--------|----------|
| Rule命中率 | >40% | 6 rules cover obvious cases |
| Cache命中率 | >30% | LRU + TTL for similar states |
| LLM调用率 | <30% | Only for complex scenarios |
| 端到端延迟 | <2s | Pipeline design |

---

## Appendix: Tech Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Signal Control | Custom state machine | Full control, zero deps |
| Detection | Custom simulator | Realistic enough for LLM |
| Rule Engine | Python rules | Fast, maintainable |
| Cache | LRU + TTL | Simple, effective |
| LLM | OpenAI-compatible API | Flexible, production-grade |
| Simulation | Custom loop | Lightweight, fast |
| CLI | Click | Rich CLI experience |
| Testing | pytest | 267 tests |
