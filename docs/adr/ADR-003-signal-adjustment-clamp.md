# ADR-003: ±10s Signal Adjustment Clamp

## Status

Accepted

## Context

LLM suggests signal timing adjustments, but unbounded adjustments could cause safety issues. We need to constrain adjustments to safe ranges.

## Decision

We clamp all adjustments to ±10 seconds:

```python
MAX_ADJUSTMENT = 10.0  # seconds

def apply_adjustment(base_duration: float, adjustment: float) -> float:
    # Clamp adjustment
    adjustment = max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT, adjustment))
    
    # Apply to base duration
    new_duration = base_duration + adjustment
    
    # Enforce min/max green times
    new_duration = max(MIN_GREEN, min(MAX_GREEN, new_duration))
    
    return new_duration
```

### Safety Constraints

- **Minimum green**: 15 seconds (pedestrian safety)
- **Maximum green**: 90 seconds (fairness)
- **Adjustment range**: ±10 seconds (gradual changes)

## Consequences

### Positive

- **Safety**: Prevents dangerous signal timings
- **Stability**: Gradual changes prevent oscillation
- **Predictability**: Bounded adjustments are easier to reason about
- **Fairness**: No approach gets extremely long/short green

### Negative

- **Limitation**: Cannot make large adjustments when needed
- **Response time**: Slow response to sudden traffic changes

### Mitigations

- Emergency override for urgent situations
- Multiple adjustment cycles for larger changes
- Monitoring for adjustment saturation

## Alternatives Considered

1. **No clamp**: Too dangerous
2. **±5s clamp**: Too restrictive
3. **±20s clamp**: Still too risky
4. **Percentage-based**: Harder to reason about

## References

- `src/traffic_agent/simulation/signal_controller.py`
- `src/traffic_agent/llm/parser.py`
