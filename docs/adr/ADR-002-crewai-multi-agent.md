# ADR-002: CrewAI Multi-Agent Architecture

## Status

Accepted

## Context

Multi-intersection coordination requires complex decision-making. A single agent cannot effectively coordinate multiple intersections with conflicting objectives. We need a distributed approach.

## Decision

We use CrewAI framework with specialized agents:

1. **Intersection Agents** (one per intersection)
   - Monitor local traffic state
   - Make local timing decisions
   - Report to coordinator

2. **Coordinator Agent**
   - Detects conflicts between intersections
   - Suggests green wave offsets
   - Resolves priority conflicts

3. **6 CrewAI Tools**
   - `get_state`: Get intersection state
   - `get_neighbors`: Get neighbor intersections
   - `apply_signal`: Apply signal changes
   - `apply_adjustment`: Apply timing adjustment
   - `check_conflicts`: Detect conflicts
   - `get_trend`: Get traffic trends

## Consequences

### Positive

- **Scalability**: Add intersections by adding agents
- **Modularity**: Each agent is independent
- **Flexibility**: Different agents for different scenarios
- **Observability**: Clear agent roles and communication

### Negative

- **Complexity**: More moving parts
- **Latency**: Agent communication overhead
- **Cost**: More LLM calls for coordination

### Mitigations

- Rule engine for fast local decisions
- Cache for repeated patterns
- Async communication where possible

## Alternatives Considered

1. **Centralized controller**: Single point of failure
2. **Peer-to-peer**: Too complex to coordinate
3. **Rule-based only**: Not flexible enough

## References

- `src/traffic_agent/crew/traffic_crew.py`
- `src/traffic_agent/crew/coordination.py`
- `src/traffic_agent/tools/traffic_tools.py`
