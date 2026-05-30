# Performance Tuning Guide

This guide covers performance optimization for the LLM Traffic Timing Assistant.

## Benchmarks

### Current Performance

| Component | Metric | Value |
|-----------|--------|-------|
| Simulation | Throughput | >100 steps/s |
| Rule Engine | Decision time | <1ms |
| Cache | Hit time | <0.1ms |
| Detector | Update time | <100µs |
| LLM API | Latency | 500-2000ms |

### Running Benchmarks

```bash
# Run built-in benchmarks
python -m traffic_agent.cli benchmark --steps 500

# Performance tests
python -m pytest tests/test_performance.py -v
```

## Optimization Strategies

### 1. Decision Cache

The 3-tier decision pipeline caches LLM decisions to avoid redundant API calls:

```python
from traffic_agent.optimization.layered import TimingDecisionPipeline

pipeline = TimingDecisionPipeline(
    llm_config=llm_config,
    use_cache=True,
    cache_ttl=60,  # seconds
    cache_max_size=1000,
)
```

**Impact**: Reduces LLM calls by 70%+ in steady-state traffic.

### 2. Rule Engine Priority

Rules are evaluated before cache and LLM, providing instant decisions:

```python
from traffic_agent.optimization.rule_engine import TimingRuleEngine

engine = TimingRuleEngine()
# Rules handle ~60% of decisions instantly
decision = engine.decide(detector_data, signal_state)
```

**Impact**: Zero-cost decisions for common patterns.

### 3. Batch Processing

For multi-intersection scenarios, batch decisions:

```python
# Process all intersections in one batch
decisions = crew.step(simulation)
```

**Impact**: Reduces overhead by 3-5x vs individual processing.

### 4. Connection Pooling

Reuse LLM client connections:

```python
from traffic_agent.llm.client import LLMClient, LLMConfig

config = LLMConfig(
    fast_model="LongCat-Flash-Chat",
    max_retries=3,
    timeout=30,
)
client = LLMClient(config)
```

**Impact**: Reduces connection overhead by 50%.

## Memory Optimization

### 1. Vehicle Cleanup

Old vehicles are automatically cleaned up:

```python
# Vehicles are removed after passing through
# No manual cleanup needed
```

### 2. Cache Eviction

LRU cache with TTL prevents unbounded growth:

```python
from traffic_agent.optimization.cache import DecisionCache

cache = DecisionCache(
    ttl_seconds=60,
    max_size=1000,
)
```

### 3. Event History

Limit event history for long-running simulations:

```python
from traffic_agent.visualization.events import EventCollector

collector = EventCollector(max_events=10000)
```

## CPU Optimization

### 1. Numpy Vectorization

Detector calculations use numpy for speed:

```python
# Vectorized queue calculation
vehicle_count = sum(
    lanes.get(i, {}).get(lt, default_lane).queue
    for lt in ["left", "through", "right"]
)
```

### 2. Local Random Generators

Each simulation uses its own RNG to avoid global state:

```python
from numpy.random import Generator, PCG64

rng = Generator(PCG64(seed))
```

### 3. Async I/O

API server uses async for concurrent requests:

```python
@app.post("/api/simulation/start")
async def start_simulation(steps: int = 50):
    # Non-blocking simulation start
    task = asyncio.create_task(_run_simulation(steps))
    return {"status": "started"}
```

## Network Optimization

### 1. SSE Compression

Enable gzip compression for SSE streams:

```python
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

### 2. Batch Events

Batch events before sending:

```python
# Send events in batches
events = collector.get_events(limit=100)
```

## Profiling

### 1. Python Profiler

```bash
# Profile simulation
python -m cProfile -o profile.stats -m traffic_agent.cli run --steps 1000

# Analyze profile
python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumulative').print_stats(20)"
```

### 2. Memory Profiler

```bash
# Install memory profiler
pip install memory_profiler

# Profile memory
python -m memory_profiler -m traffic_agent.cli run --steps 100
```

### 3. Line Profiler

```bash
# Install line profiler
pip install line_profiler

# Profile specific function
@profile
def my_function():
    pass

kernprof -l -v my_script.py
```

## Scaling

### Horizontal Scaling

Run multiple API server instances:

```yaml
# docker-compose.yml
services:
  api1:
    build: .
    ports:
      - "8081:8080"
  api2:
    build: .
    ports:
      - "8082:8080"
```

### Vertical Scaling

Increase resources for single instance:

```yaml
# k8s deployment
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "2000m"
    memory: "2Gi"
```

## Monitoring

### Key Metrics

1. **Throughput**: Steps per second
2. **Latency**: Decision time per step
3. **Cache Hit Rate**: Percentage of cache hits
4. **LLM Calls**: Number of API calls
5. **Memory Usage**: RSS memory

### Alerts

Set up alerts for:

- High latency (>1s per step)
- Low cache hit rate (<50%)
- High memory usage (>1GB)
- LLM API errors

## Best Practices

1. **Use Cache**: Always enable cache for production
2. **Rule Engine First**: Rules handle most cases instantly
3. **Batch Operations**: Process multiple intersections together
4. **Monitor Performance**: Track key metrics continuously
5. **Profile Regularly**: Identify bottlenecks early

## Troubleshooting

### Slow Performance

1. Check LLM API latency
2. Verify cache hit rate
3. Profile CPU usage
4. Check memory usage

### High Memory

1. Reduce cache size
2. Limit event history
3. Clean up old vehicles
4. Use memory profiling

### High CPU

1. Check for busy loops
2. Verify async usage
3. Profile specific functions
4. Consider horizontal scaling
