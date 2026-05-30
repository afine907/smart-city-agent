"""
Performance Benchmarks — Measure and track performance metrics.

Tests that verify performance characteristics of key operations.
"""

import time
import pytest

from traffic_agent.simulation.sim_loop import TimingSimulation
from traffic_agent.optimization.rule_engine import TimingRuleEngine
from traffic_agent.optimization.cache import DecisionCache
from traffic_agent.simulation.detector import TrendAnalyzer


class TestSimulationPerformance:
    """Test simulation performance."""

    def test_simulation_throughput(self):
        """Simulation should process at least 100 steps per second."""
        sim = TimingSimulation(seed=42)

        start = time.time()
        sim.run(steps=1000, verbose=False)
        elapsed = time.time() - start

        steps_per_second = 1000 / elapsed
        assert steps_per_second > 100, f"Throughput too low: {steps_per_second:.1f} steps/s"

    def test_simulation_memory_stable(self):
        """Simulation memory should not grow unboundedly."""
        sim = TimingSimulation(seed=42)

        # Run a short simulation
        sim.run(steps=100, verbose=False)

        # Check that vehicle list doesn't grow forever
        for direction in sim._vehicles:
            assert len(sim._vehicles[direction]) < 1000


class TestRuleEnginePerformance:
    """Test rule engine performance."""

    def test_rule_engine_speed(self):
        """Rule engine should make decisions in under 1ms."""
        engine = TimingRuleEngine()
        detector_data = {
            "queue_north": 5,
            "queue_south": 3,
            "queue_east": 8,
            "queue_west": 2,
        }
        signal_state = {"current_phase": "NS_GREEN", "phase_duration": 30.0}

        start = time.time()
        for _ in range(1000):
            engine.decide(detector_data, signal_state)
        elapsed = time.time() - start

        per_decision_ms = elapsed / 1000 * 1000
        assert per_decision_ms < 1.0, f"Too slow: {per_decision_ms:.3f}ms per decision"


class TestCachePerformance:
    """Test cache performance."""

    def test_cache_hit_speed(self):
        """Cache hits should be instant (<0.1ms)."""
        cache = DecisionCache(ttl_seconds=60)

        # Prime the cache
        from traffic_agent.tools.traffic_tools import IntersectionState
        state = IntersectionState(
            intersection_id="test",
            timestamp=0.0,
            queue_north=5,
            queue_south=3,
        )

        from traffic_agent.llm.parser import TimingAdjustment
        decision = TimingAdjustment.no_adjustment("test")
        cache.set(state, decision)

        # Measure cache hits
        start = time.time()
        for _ in range(10000):
            cache.get(state)
        elapsed = time.time() - start

        per_hit_us = elapsed / 10000 * 1_000_000
        assert per_hit_us < 100, f"Cache too slow: {per_hit_us:.1f}µs per hit"

    def test_cache_eviction_performance(self):
        """Cache eviction should not slow down inserts."""
        cache = DecisionCache(ttl_seconds=60, max_size=100)

        from traffic_agent.llm.parser import TimingAdjustment
        decision = TimingAdjustment.no_adjustment("test")

        start = time.time()
        for i in range(1000):
            key = f"key_{i}"
            cache.set(key, decision)
        elapsed = time.time() - start

        per_insert_ms = elapsed / 1000 * 1000
        assert per_insert_ms < 1.0, f"Insert too slow: {per_insert_ms:.3f}ms"


class TestDetectorPerformance:
    """Test detector and trend analyzer performance."""

    def test_trend_analysis_speed(self):
        """Trend analysis should be fast."""
        from traffic_agent.simulation.detector import DetectorData, DetectorReading

        analyzer = TrendAnalyzer(window_size=10)

        # Create detector data
        def make_data(count: int) -> DetectorData:
            readings = {
                d: DetectorReading(vehicles=count, pedestrians=0, bicycles=0)
                for d in ["north", "south", "east", "west"]
            }
            return DetectorData(intersection_id="test", timestamp=0.0, readings=readings)

        # Feed data
        start = time.time()
        for i in range(1000):
            analyzer.update(make_data(i % 10))
        elapsed = time.time() - start

        per_update_us = elapsed / 1000 * 1_000_000
        assert per_update_us < 100, f"Too slow: {per_update_us:.1f}µs per update"
