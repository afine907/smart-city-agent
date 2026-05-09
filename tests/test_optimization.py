"""
Tests for cost optimization module.
"""

import time

import pytest

from traffic_agent.optimization.cache import DecisionCache
from traffic_agent.optimization.cost_tracker import CostTracker
from traffic_agent.optimization.layered import TimingDecisionPipeline
from traffic_agent.optimization.rule_engine import TimingRuleEngine
from traffic_agent.llm.parser import TimingAdjustment, TrafficDecision
from traffic_agent.tools.traffic_tools import IntersectionState


def _make_detector(n=5, s=3, e=8, w=2, np=0, sp=0, ep=0, wp=0):
    return {
        "readings": {
            "north": {"vehicles": n, "pedestrians": np, "bicycles": 0},
            "south": {"vehicles": s, "pedestrians": sp, "bicycles": 0},
            "east": {"vehicles": e, "pedestrians": ep, "bicycles": 0},
            "west": {"vehicles": w, "pedestrians": wp, "bicycles": 0},
        }
    }


def _make_signal(phase="NS_GREEN", remaining=30.0, elapsed=10.0, base=60.0):
    return {
        "current_phase": phase,
        "phase_remaining": remaining,
        "phase_elapsed": elapsed,
        "base_duration": base,
    }


# ─── Cache Tests ────────────────────────────────────────────

class TestDecisionCache:
    """Test DecisionCache LRU + TTL."""

    def test_set_get_string_key(self):
        cache = DecisionCache(max_size=10, ttl_seconds=60)
        adj = TimingAdjustment(adjustment=5, reasoning="test", confidence=0.9)
        cache.set("key1", adj)
        result = cache.get("key1")
        assert result is not None
        assert result.adjustment == 5

    def test_cache_miss(self):
        cache = DecisionCache(max_size=10, ttl_seconds=60)
        result = cache.get("missing_key")
        assert result is None
        assert cache.stats.misses == 1

    def test_cache_hit(self):
        cache = DecisionCache(max_size=10, ttl_seconds=60)
        adj = TimingAdjustment(adjustment=5, reasoning="test", confidence=0.9)
        cache.set("key1", adj)
        cache.get("key1")
        cache.get("key1")
        assert cache.stats.hits == 2
        assert cache.stats.hit_rate == 1.0

    def test_ttl_expiration(self):
        cache = DecisionCache(max_size=10, ttl_seconds=0.1)
        adj = TimingAdjustment(adjustment=5, reasoning="test", confidence=0.9)
        cache.set("key1", adj)
        assert cache.get("key1") is not None
        time.sleep(0.15)
        assert cache.get("key1") is None
        assert cache.stats.misses == 1

    def test_lru_eviction(self):
        cache = DecisionCache(max_size=2, ttl_seconds=60)
        d = TimingAdjustment(adjustment=0, reasoning="test", confidence=0.9)
        cache.set("key1", d)
        cache.set("key2", d)
        cache.get("key1")
        cache.set("key3", d)
        assert cache.get("key1") is not None
        assert cache.get("key2") is None
        assert cache.get("key3") is not None

    def test_clear(self):
        cache = DecisionCache()
        adj = TimingAdjustment(adjustment=5, reasoning="test", confidence=0.9)
        cache.set("key1", adj)
        assert cache.size == 1
        cache.clear()
        assert cache.size == 0

    def test_size_property(self):
        cache = DecisionCache(max_size=5)
        for i in range(3):
            cache.set(f"key{i}", TimingAdjustment(adjustment=0, reasoning="test", confidence=0.9))
        assert cache.size == 3


# ─── Rule Engine Tests ──────────────────────────────────────

class TestRuleEngine:
    """Test TimingRuleEngine decision logic."""

    def test_low_traffic_keeps_phase(self):
        engine = TimingRuleEngine()
        detector = _make_detector(n=1, s=0, e=1, w=0)
        signal = _make_signal()
        adj = engine.decide(detector, signal)
        assert adj is not None
        assert adj.adjustment == 0
        assert "交通量低" in adj.reasoning
        assert adj.confidence >= 0.8

    def test_high_ns_queue_extends(self):
        engine = TimingRuleEngine()
        detector = _make_detector(n=15, s=10, e=2, w=1)
        signal = _make_signal()
        adj = engine.decide(detector, signal)
        assert adj is not None
        assert adj.adjustment > 0
        assert "延长" in adj.reasoning

    def test_high_ew_queue_extends(self):
        engine = TimingRuleEngine()
        detector = _make_detector(n=2, s=1, e=15, w=10)
        signal = _make_signal(phase="EW_GREEN")
        adj = engine.decide(detector, signal)
        assert adj is not None
        assert adj.adjustment > 0

    def test_cross_queue_shortens(self):
        engine = TimingRuleEngine()
        detector = _make_detector(n=2, s=2, e=10, w=10)
        signal = _make_signal(remaining=30.0)
        adj = engine.decide(detector, signal)
        assert adj is not None
        assert adj.adjustment < 0

    def test_stats_tracking(self):
        engine = TimingRuleEngine()
        detector = _make_detector(n=1, s=0, e=0, w=0)
        signal = _make_signal()
        engine.decide(detector, signal)
        stats = engine.get_stats()
        assert stats["total"] >= 1
        assert stats["decisions_made"] >= 1

    def test_reset_stats(self):
        engine = TimingRuleEngine()
        detector = _make_detector(n=1, s=0, e=0, w=0)
        signal = _make_signal()
        engine.decide(detector, signal)
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
        assert "LLM Cost Report" in report
        assert "ix_0_0" in report
        assert "ix_0_1" in report

    def test_clear(self):
        tracker = CostTracker()
        tracker.record("ix_0_0", "LongCat-Flash-Chat", prompt_tokens=100, completion_tokens=20)
        tracker.clear()
        summary = tracker.get_summary()
        assert summary["total_calls"] == 0


# ─── Pipeline Tests ─────────────────────────────────────────

class TestTimingDecisionPipeline:
    """Test TimingDecisionPipeline three-layer pipeline."""

    def test_low_traffic_uses_rules(self):
        pipeline = TimingDecisionPipeline()
        detector = _make_detector(n=1, s=0, e=0, w=0)
        signal = _make_signal()
        adj = pipeline.decide(detector, signal, intersection_id="ix_1")
        assert adj is not None
        stats = pipeline.get_stats()
        assert stats["layer1_rules"] == 1
        assert stats["layer3_llm"] == 0

    def test_stats_tracking(self):
        pipeline = TimingDecisionPipeline()
        detector = _make_detector(n=1, s=0, e=0, w=0)
        signal = _make_signal()
        pipeline.decide(detector, signal, intersection_id="ix_1")
        stats = pipeline.get_stats()
        assert stats["total_decisions"] == 1
        assert "rule_rate" in stats
        assert "free_rate" in stats
