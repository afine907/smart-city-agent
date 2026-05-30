# ADR-001: Three-Tier Decision Pipeline

## Status

Accepted

## Context

The traffic signal timing system needs to make decisions about signal adjustments. Using LLM for every decision is expensive and slow. We need a cost-effective approach that balances accuracy with performance.

## Decision

We implement a three-tier decision pipeline:

1. **Layer 1: Rule Engine** (free, instant)
   - 6 predefined rules for common traffic patterns
   - Handles ~60% of decisions
   - Zero cost, <1ms latency

2. **Layer 2: Decision Cache** (free, instant)
   - LRU cache with TTL
   - Caches LLM decisions for similar traffic states
   - Handles ~20% of decisions
   - Zero cost, <0.1ms latency

3. **Layer 3: LLM** (paid, slow)
   - CrewAI multi-agent system
   - Handles complex scenarios
   - ~20% of decisions
   - 500-2000ms latency

## Consequences

### Positive

- **Cost Reduction**: 80%+ of decisions are free (rules + cache)
- **Low Latency**: Most decisions are instant
- **Accuracy**: LLM handles complex cases
- **Scalability**: Rules and cache scale linearly

### Negative

- **Complexity**: Three layers to maintain
- **Cache Invalidation**: Stale cache entries may cause issues
- **Rule Maintenance**: Rules need manual tuning

### Mitigations

- TTL-based cache expiration
- Configurable rule priorities
- Monitoring and alerting for cache hit rates

## Alternatives Considered

1. **LLM-only**: Too expensive and slow
2. **Rules-only**: Not accurate enough for complex scenarios
3. **ML model**: Requires training data and infrastructure

## References

- `src/traffic_agent/optimization/layered.py`
- `src/traffic_agent/optimization/rule_engine.py`
- `src/traffic_agent/optimization/cache.py`
