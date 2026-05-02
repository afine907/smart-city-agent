"""
Tests for cost optimization module.
"""

import time

import pytest

from traffic_agent.optimization.cache import DecisionCache
from traffic_agent.optimization.cost_tracker import CostTracker
from traffic_agent.optimization.layered import LayeredDecisionMaker
from traffic_agent.optimization.rule_engine import RuleEngine
from traffic_agent.llm.parser import TrafficDecision
from traffic_agent.tools.traffic_tools import IntersectionState


def _make_state(
    ix_id: str = "ix_0_0",
    queue_north: int = 5,
    queue_south: int = 3,
    queue_east: int = 8,
    queue_west: int = 2,
    phase: str = "NS_GREEN",
) -> IntersectionState:
    """Helper to create IntersectionState."""
    return IntersectionState(
        intersection_id=ix_id,
        timestamp=0.0,
        queue_north=queue_north,
        queue_south=queue_south,
        queue_east=queue_east,
        queue_west=queue_west,
        wait_north=queue_north * 2.0,
        wait_south=queue_south * 2.0,
        wait_east=queue_east * 2.0,
        wait_west=queue_west * 2.0,
        current_phase=phase,
        phase_duration=15.0,
    )


# ─── Cache Tests ────────────────────────────────────────────

class TestDecisionCache:
    """Test DecisionCache LRU + TTL."""
    
    def test_set_get(self):
        cache = DecisionCache(max_size=10, ttl_seconds=60)
        state = _make_state()
        decision = TrafficDecision(
            action="extend_green", phase="NS_GREEN", duration=15,
            reasoning="test", confidence=0.9,
        )
        
        cache.set(state, decision)
        result = cache.get(state)
        
        assert result is not None
        assert result.phase == "NS_GREEN"
        assert result.duration == 15
    
    def test_cache_miss(self):
        cache = DecisionCache(max_size=10, ttl_seconds=60)
        state = _make_state()
        
        result = cache.get(state)
        assert result is None
        assert cache.stats.misses == 1
    
    def test_cache_hit(self):
        cache = DecisionCache(max_size=10, ttl_seconds=60)
        state = _make_state()
        decision = TrafficDecision(
            action="extend_green", phase="NS_GREEN", duration=15,
            reasoning="test", confidence=0.9,
        )
        
        cache.set(state, decision)
        cache.get(state)  # hit
        cache.get(state)  # hit
        
        assert cache.stats.hits == 2
        assert cache.stats.misses == 0
        assert cache.stats.hit_rate == 1.0
    
    def test_ttl_expiration(self):
        cache = DecisionCache(max_size=10, ttl_seconds=0.1)
        state = _make_state()
        decision = TrafficDecision(
            action="extend_green", phase="NS_GREEN", duration=15,
            reasoning="test", confidence=0.9,
        )
        
        cache.set(state, decision)
        
        # Immediate hit
        assert cache.get(state) is not None
        
        # Wait for expiration
        time.sleep(0.15)
        
        # Should miss (expired)
        assert cache.get(state) is None
        assert cache.stats.misses == 1
    
    def test_lru_eviction(self):
        cache = DecisionCache(max_size=2, ttl_seconds=60)
        
        # These produce different cache keys (queue_north // 3)
        s1 = _make_state(queue_north=0)   # bin 0
        s2 = _make_state(queue_north=3)   # bin 1
        s3 = _make_state(queue_north=6)   # bin 2
        
        d = TrafficDecision(action="extend_green", phase="NS_GREEN", duration=15,
                           reasoning="test", confidence=0.9)
        
        cache.set(s1, d)
        cache.set(s2, d)
        
        # Access s1 to make it recently used
        cache.get(s1)
        
        # Adding s3 should evict s2 (least recently used)
        cache.set(s3, d)
        
        assert cache.get(s1) is not None  # Still cached
        assert cache.get(s2) is None      # Evicted
        assert cache.get(s3) is not None  # Newly cached
    
    def test_state_key_coarseness(self):
        """Test that similar states map to same cache key."""
        cache = DecisionCache()
        
        # These should map to the same key (queue bins of 3)
        # 4 // 3 = 1, 5 // 3 = 1 → same bin
        s1 = _make_state(queue_north=4, queue_south=3)
        s2 = _make_state(queue_north=5, queue_south=4)
        
        k1 = cache._state_key(s1)
        k2 = cache._state_key(s2)
        
        assert k1 == k2  # Same bin
    
    def test_clear(self):
        cache = DecisionCache()
        state = _make_state()
        decision = TrafficDecision(action="extend_green", phase="NS_GREEN", duration=15,
                                   reasoning="test", confidence=0.9)
        
        cache.set(state, decision)
        assert cache.size == 1
        
        cache.clear()
        assert cache.size == 0
    
    def test_size_property(self):
        cache = DecisionCache(max_size=5)
        
        # Use values that produce different cache keys (queue_north // 3)
        for i in range(3):
            state = _make_state(queue_north=i * 3)  # 0, 3, 6 → bins 0, 1, 2
            decision = TrafficDecision(action="extend_green", phase="NS_GREEN", duration=15,
                                       reasoning="test", confidence=0.9)
            cache.set(state, decision)
        
        assert cache.size == 3


# ─── Rule Engine Tests ──────────────────────────────────────

class TestRuleEngine:
    """Test RuleEngine decision logic."""
    
    def test_low_traffic_keeps_phase(self):
        engine = RuleEngine()
        state = _make_state(queue_north=1, queue_south=0, queue_east=1, queue_west=0)
        
        decision = engine.decide(state)
        
        assert decision is not None
        assert decision.phase == "NS_GREEN"  # Same as current
        assert "交通量低" in decision.reasoning
        assert decision.confidence >= 0.8
    
    def test_severe_ns_congestion(self):
        engine = RuleEngine()
        state = _make_state(queue_north=15, queue_south=10, queue_east=2, queue_west=1)
        
        decision = engine.decide(state)
        
        assert decision is not None
        assert decision.phase == "NS_GREEN"
        assert decision.duration == 45
        assert "严重拥堵" in decision.reasoning
    
    def test_severe_ew_congestion(self):
        engine = RuleEngine()
        state = _make_state(queue_north=2, queue_south=1, queue_east=15, queue_west=10)
        
        decision = engine.decide(state)
        
        assert decision is not None
        assert decision.phase == "EW_GREEN"
        assert decision.duration == 45
    
    def test_moderate_imbalance_switches(self):
        engine = RuleEngine()
        # EW has more demand, current is NS_GREEN
        state = _make_state(
            queue_north=3, queue_south=2,
            queue_east=8, queue_west=7,
            phase="NS_GREEN",
        )
        
        decision = engine.decide(state)
        
        # Should recommend switching to EW
        if decision is not None:
            assert decision.phase == "EW_GREEN"
    
    def test_balanced_traffic(self):
        engine = RuleEngine()
        state = _make_state(queue_north=5, queue_south=4, queue_east=5, queue_west=4)
        
        decision = engine.decide(state)
        
        if decision is not None:
            assert "均衡" in decision.reasoning
    
    def test_stats_tracking(self):
        engine = RuleEngine()
        
        # Low traffic (rule applies)
        s1 = _make_state(queue_north=1, queue_south=0, queue_east=0, queue_west=0)
        engine.decide(s1)
        
        # Moderate traffic (may or may not apply)
        s2 = _make_state(queue_north=7, queue_south=5, queue_east=12, queue_west=8)
        engine.decide(s2)
        
        stats = engine.get_stats()
        assert stats["total"] >= 1
        assert stats["decisions_made"] >= 1
    
    def test_reset_stats(self):
        engine = RuleEngine()
        state = _make_state(queue_north=1, queue_south=0, queue_east=0, queue_west=0)
        engine.decide(state)
        
        assert engine.get_stats()["total"] > 0
        
        engine.reset_stats()
        assert engine.get_stats()["total"] == 0


# ─── Cost Tracker Tests ─────────────────────────────────────

class TestCostTracker:
    """Test CostTracker accounting."""
    
    def test_record_and_total(self):
        tracker = CostTracker()
        
        tracker.record("ix_0_0", "LongCat-Flash-Chat", prompt_tokens=200, completion_tokens=50)
        tracker.record("ix_0_1", "LongCat-Flash-Chat", prompt_tokens=300, completion_tokens=80)
        
        cost = tracker.get_total_cost()
        assert cost > 0
    
    def test_cached_calls_free(self):
        tracker = CostTracker()
        
        tracker.record("ix_0_0", "LongCat-Flash-Chat", prompt_tokens=200, completion_tokens=50, cached=False)
        tracker.record("ix_0_0", "LongCat-Flash-Chat", prompt_tokens=200, completion_tokens=50, cached=True)
        
        summary = tracker.get_summary()
        assert summary["cached_calls"] == 1
        assert summary["uncached_calls"] == 1
    
    def test_per_intersection(self):
        tracker = CostTracker()
        
        tracker.record("ix_0_0", "LongCat-Flash-Chat", prompt_tokens=100, completion_tokens=20)
        tracker.record("ix_0_0", "LongCat-Flash-Chat", prompt_tokens=100, completion_tokens=20)
        tracker.record("ix_0_1", "LongCat-Flash-Chat", prompt_tokens=150, completion_tokens=30)
        
        per_ix = tracker.get_per_intersection()
        
        assert "ix_0_0" in per_ix
        assert "ix_0_1" in per_ix
        assert per_ix["ix_0_0"]["calls"] == 2
        assert per_ix["ix_0_1"]["calls"] == 1
    
    def test_summary(self):
        tracker = CostTracker()
        
        tracker.record("ix_0_0", "LongCat-Flash-Chat", prompt_tokens=200, completion_tokens=50)
        
        summary = tracker.get_summary()
        
        assert summary["total_calls"] == 1
        assert summary["cached_calls"] == 0
        assert summary["total_tokens"] == 250
        assert summary["estimated_cost_usd"] > 0
    
    def test_format_report(self):
        tracker = CostTracker()
        
        tracker.record("ix_0_0", "LongCat-Flash-Chat", prompt_tokens=200, completion_tokens=50)
        tracker.record("ix_0_1", "LongCat-Flash-Chat", prompt_tokens=150, completion_tokens=30, cached=True)
        
        report = tracker.format_report()
        
        assert "💰 LLM Cost Report" in report
        assert "ix_0_0" in report
        assert "ix_0_1" in report
    
    def test_clear(self):
        tracker = CostTracker()
        tracker.record("ix_0_0", "LongCat-Flash-Chat", prompt_tokens=100, completion_tokens=20)
        
        tracker.clear()
        
        summary = tracker.get_summary()
        assert summary["total_calls"] == 0


# ─── Layered Decision Maker Tests ───────────────────────────

class TestLayeredDecisionMaker:
    """Test LayeredDecisionMaker three-layer pipeline."""

    def test_low_traffic_uses_rules(self):
        """Low traffic should be handled by rule engine (Layer 1)."""
        maker = LayeredDecisionMaker()
        state = _make_state(queue_north=1, queue_south=0, queue_east=0, queue_west=0)

        decision = maker.decide(state)

        assert decision is not None
        stats = maker.get_stats()
        assert stats["layer1_rules"] == 1
        assert stats["layer3_llm"] == 0

    def test_stats_tracking(self):
        maker = LayeredDecisionMaker()
        state = _make_state(queue_north=1, queue_south=0, queue_east=0, queue_west=0)
        maker.decide(state)

        stats = maker.get_stats()
        assert stats["total_decisions"] == 1
        assert "rule_rate" in stats
        assert "free_rate" in stats

    def test_complexity_simple(self):
        maker = LayeredDecisionMaker()
        state = _make_state(queue_north=2, queue_south=1, queue_east=1, queue_west=0)
        assert maker._assess_complexity(state) == "simple"

    def test_complexity_moderate(self):
        maker = LayeredDecisionMaker()
        state = _make_state(queue_north=5, queue_south=3, queue_east=10, queue_west=8)
        assert maker._assess_complexity(state) in ["moderate", "complex"]

    def test_complexity_emergency(self):
        maker = LayeredDecisionMaker()
        state = _make_state(queue_north=1, queue_south=0, queue_east=0, queue_west=0)
        state.emergency = True
        assert maker._assess_complexity(state) == "complex"
