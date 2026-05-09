"""Tests for timing adjustment rule engine and parser."""

import pytest
from traffic_agent.llm.parser import TimingAdjustment, TimingAdjustmentParser
from traffic_agent.optimization.rule_engine import TimingRuleEngine


class TestTimingAdjustment:
    def test_create(self):
        adj = TimingAdjustment(
            adjustment=5,
            reasoning="测试",
            confidence=0.8,
        )
        assert adj.adjustment == 5
        assert adj.source == "llm"

    def test_no_adjustment(self):
        adj = TimingAdjustment.no_adjustment()
        assert adj.adjustment == 0
        assert adj.source == "rule"

    def test_to_dict(self):
        adj = TimingAdjustment(adjustment=3, reasoning="test", confidence=0.7)
        d = adj.to_dict()
        assert d["adjustment"] == 3
        assert d["source"] == "llm"


class TestTimingAdjustmentParser:
    def test_parse_valid(self):
        text = '{"adjustment": 5, "reasoning": "车多", "confidence": 0.8}'
        result = TimingAdjustmentParser.parse(text)
        assert result is not None
        assert result.adjustment == 5
        assert result.reasoning == "车多"
        assert result.source == "llm"

    def test_parse_with_alerts(self):
        text = '{"adjustment": -3, "reasoning": "对向拥堵", "confidence": 0.7, "alerts": ["拥堵"]}'
        result = TimingAdjustmentParser.parse(text)
        assert result is not None
        assert result.adjustment == -3
        assert result.alerts == ["拥堵"]

    def test_parse_clamp_positive(self):
        text = '{"adjustment": 50, "reasoning": "test", "confidence": 0.5}'
        result = TimingAdjustmentParser.parse(text)
        assert result is not None
        assert result.adjustment == 10  # clamped to max

    def test_parse_clamp_negative(self):
        text = '{"adjustment": -50, "reasoning": "test", "confidence": 0.5}'
        result = TimingAdjustmentParser.parse(text)
        assert result is not None
        assert result.adjustment == -10  # clamped to min

    def test_parse_missing_adjustment(self):
        text = '{"reasoning": "test"}'
        result = TimingAdjustmentParser.parse(text)
        assert result is not None
        assert result.adjustment == 0  # default

    def test_parse_invalid_json(self):
        result = TimingAdjustmentParser.parse("not json")
        assert result is None

    def test_parse_in_code_block(self):
        text = '''```json
{"adjustment": 3, "reasoning": "test", "confidence": 0.8}
```'''
        result = TimingAdjustmentParser.parse(text)
        assert result is not None
        assert result.adjustment == 3

    def test_parse_chinese_reasoning(self):
        text = '{"adjustment": 5, "reasoning": "南北方向排队20辆，建议延长", "confidence": 0.85}'
        result = TimingAdjustmentParser.parse(text)
        assert result is not None
        assert "南北" in result.reasoning

    def test_fallback(self):
        result = TimingAdjustmentParser.fallback("test error")
        assert result.adjustment == 0
        assert result.source == "fallback"
        assert "test error" in result.reasoning


class TestTimingRuleEngine:
    def setup_method(self):
        self.engine = TimingRuleEngine()

    def _make_detector(self, n=0, s=0, e=0, w=0, np=0, sp=0, ep=0, wp=0):
        return {
            "readings": {
                "north": {"vehicles": n, "pedestrians": np, "bicycles": 0},
                "south": {"vehicles": s, "pedestrians": sp, "bicycles": 0},
                "east": {"vehicles": e, "pedestrians": ep, "bicycles": 0},
                "west": {"vehicles": w, "pedestrians": wp, "bicycles": 0},
            }
        }

    def _make_signal(self, phase="NS_GREEN", remaining=30.0):
        return {
            "current_phase": phase,
            "phase_remaining": remaining,
        }

    def test_low_traffic_no_adjustment(self):
        detector = self._make_detector(n=1, s=1, e=0, w=0)
        signal = self._make_signal()
        result = self.engine.decide(detector, signal)
        assert result is not None
        assert result.adjustment == 0
        assert result.source == "rule"

    def test_high_queue_extend(self):
        detector = self._make_detector(n=10, s=10, e=0, w=0)
        signal = self._make_signal()
        result = self.engine.decide(detector, signal)
        assert result is not None
        assert result.adjustment > 0  # should extend

    def test_moderate_queue_extend(self):
        detector = self._make_detector(n=5, s=5, e=0, w=0)
        signal = self._make_signal()
        result = self.engine.decide(detector, signal)
        assert result is not None
        assert 3 <= result.adjustment <= 7

    def test_cross_queue_shorten(self):
        detector = self._make_detector(n=2, s=2, e=10, w=10)
        signal = self._make_signal(remaining=30.0)
        result = self.engine.decide(detector, signal)
        assert result is not None
        assert result.adjustment < 0  # should shorten

    def test_pedestrian_extend(self):
        detector = self._make_detector(n=2, s=2, e=0, w=0, np=3, sp=2)
        signal = self._make_signal()
        result = self.engine.decide(detector, signal)
        assert result is not None
        assert result.adjustment > 0  # should extend for pedestrians

    def test_no_adjustment_during_yellow(self):
        detector = self._make_detector(n=10, s=10, e=0, w=0)
        signal = self._make_signal(phase="NS_YELLOW")
        result = self.engine.decide(detector, signal)
        assert result is not None
        assert result.adjustment == 0  # no adjustment during yellow

    def test_rising_trend_extend(self):
        detector = self._make_detector(n=5, s=5, e=0, w=0)
        signal = self._make_signal()
        trend = {"ns_total": [5, 10, 15, 20], "ew_total": [2, 2, 2, 2]}
        result = self.engine.decide(detector, signal, trend)
        assert result is not None
        assert result.adjustment > 0  # should extend for rising trend

    def test_ew_green_direction(self):
        detector = self._make_detector(n=0, s=0, e=10, w=10)
        signal = self._make_signal(phase="EW_GREEN")
        result = self.engine.decide(detector, signal)
        assert result is not None
        assert result.adjustment > 0  # should extend EW green

    def test_stats(self):
        detector = self._make_detector(n=0, s=0, e=0, w=0)
        signal = self._make_signal()
        self.engine.decide(detector, signal)
        stats = self.engine.get_stats()
        assert stats["decisions_made"] > 0

    def test_reset_stats(self):
        detector = self._make_detector(n=0, s=0, e=0, w=0)
        signal = self._make_signal()
        self.engine.decide(detector, signal)
        self.engine.reset_stats()
        stats = self.engine.get_stats()
        assert stats["decisions_made"] == 0
