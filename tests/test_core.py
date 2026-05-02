"""
Tests for LLM Traffic Controller
"""

import json
import numpy as np
import pytest

from traffic_agent.llm.parser import ResponseParser, TrafficDecision, VALID_ACTIONS, VALID_PHASES
from traffic_agent.simulation.engine import SimulationEngine, SimulationConfig
from traffic_agent.tools.traffic_tools import IntersectionState
from traffic_agent.crew.traffic_crew import DecisionCache


class TestResponseParser:
    """Test LLM response parsing."""
    
    def test_parse_valid_json(self):
        response = json.dumps({
            "action": "extend_green",
            "phase": "NS_GREEN",
            "duration": 30,
            "reasoning": "北方向车多，需要延长绿灯",
            "confidence": 0.85,
        })
        
        decision = ResponseParser.parse(response)
        assert decision is not None
        assert decision.action == "extend_green"
        assert decision.phase == "NS_GREEN"
        assert decision.duration == 30
        assert "北方向" in decision.reasoning
    
    def test_parse_json_in_codeblock(self):
        response = """```json
{
    "action": "switch_phase",
    "phase": "EW_GREEN",
    "duration": 25,
    "reasoning": "东西方向等待时间过长",
    "confidence": 0.7
}
```"""
        
        decision = ResponseParser.parse(response)
        assert decision is not None
        assert decision.action == "switch_phase"
        assert decision.phase == "EW_GREEN"
    
    def test_parse_with_extra_text(self):
        response = """根据当前路况分析，我决定延长南北绿灯。

```json
{
    "action": "extend_green",
    "phase": "NS_GREEN",
    "duration": 20,
    "reasoning": "南北方向车流量大",
    "confidence": 0.9
}
```

以上是我的决策。"""
        
        decision = ResponseParser.parse(response)
        assert decision is not None
        assert decision.duration == 20
    
    def test_parse_invalid_json(self):
        response = "这不是JSON格式"
        decision = ResponseParser.parse(response)
        assert decision is None
    
    def test_parse_invalid_action(self):
        response = json.dumps({
            "action": "invalid_action",
            "phase": "NS_GREEN",
            "duration": 20,
            "reasoning": "test",
            "confidence": 0.5,
        })
        
        decision = ResponseParser.parse(response)
        assert decision is None
    
    def test_parse_duration_out_of_range(self):
        response = json.dumps({
            "action": "extend_green",
            "phase": "NS_GREEN",
            "duration": 200,  # Too long
            "reasoning": "test",
            "confidence": 0.5,
        })
        
        decision = ResponseParser.parse(response)
        assert decision is not None
        assert decision.duration == 60  # Clamped to max
    
    def test_parse_duration_too_short(self):
        response = json.dumps({
            "action": "extend_green",
            "phase": "NS_GREEN",
            "duration": 3,  # Too short
            "reasoning": "test",
            "confidence": 0.5,
        })
        
        decision = ResponseParser.parse(response)
        assert decision is not None
        assert decision.duration == 10  # Clamped to min
    
    def test_parse_chinese_phase(self):
        response = json.dumps({
            "action": "switch_phase",
            "phase": "南北绿灯",
            "duration": 20,
            "reasoning": "test",
            "confidence": 0.5,
        })
        
        decision = ResponseParser.parse(response)
        assert decision is not None
        assert decision.phase == "NS_GREEN"
    
    def test_fallback(self):
        decision = ResponseParser.fallback("test error")
        assert decision.action == "extend_green"
        assert decision.phase == "NS_GREEN"
        assert decision.duration == 15
        assert decision.confidence == 0.3
    
    def test_decision_to_dict(self):
        decision = TrafficDecision(
            action="extend_green",
            phase="NS_GREEN",
            duration=20,
            reasoning="测试",
            confidence=0.8,
        )
        
        d = decision.to_dict()
        assert d["action"] == "extend_green"
        assert d["duration"] == 20


class TestIntersectionState:
    """Test intersection state formatting."""
    
    def test_state_to_text(self):
        state = IntersectionState(
            intersection_id="test_ix",
            timestamp=100.0,
            queue_north=15,
            queue_south=10,
            queue_east=5,
            queue_west=3,
            wait_north=30.0,
            wait_south=20.0,
            wait_east=10.0,
            wait_west=6.0,
            current_phase="NS_GREEN",
            phase_duration=45.0,
        )
        
        text = state.to_text()
        assert "test_ix" in text
        assert "15辆" in text
        assert "NS_GREEN" in text
    
    def test_get_max_queue(self):
        state = IntersectionState(
            intersection_id="test",
            timestamp=0,
            queue_north=10,
            queue_south=5,
            queue_east=20,
            queue_west=3,
        )
        
        assert state.get_max_queue() == 20
    
    def test_get_total_queue(self):
        state = IntersectionState(
            intersection_id="test",
            timestamp=0,
            queue_north=10,
            queue_south=5,
            queue_east=20,
            queue_west=3,
        )
        
        assert state.get_total_queue() == 38


class TestSimulationEngine:
    """Test simulation engine."""
    
    def test_create_single_intersection(self):
        engine = SimulationEngine(SimulationConfig(seed=42))
        engine.add_intersection("ix_0")
        
        assert "ix_0" in engine.network.intersections
    
    def test_get_state(self):
        engine = SimulationEngine(SimulationConfig(seed=42))
        engine.add_intersection("ix_0")
        
        state = engine.get_state("ix_0")
        assert state.intersection_id == "ix_0"
        assert state.current_phase == "NS_GREEN"
    
    def test_step_advances_time(self):
        engine = SimulationEngine(SimulationConfig(dt=1.0, seed=42))
        engine.add_intersection("ix_0")
        
        engine.step()
        assert engine.time == 1.0
    
    def test_apply_decision(self):
        engine = SimulationEngine(SimulationConfig(seed=42))
        engine.add_intersection("ix_0")
        
        engine.apply_decision("ix_0", {"phase": "EW_GREEN"})
        ix = engine.network.intersections["ix_0"]
        assert ix.current_phase == "EW_GREEN"
    
    def test_connect_intersections(self):
        engine = SimulationEngine(SimulationConfig(seed=42))
        engine.add_intersection("ix_0")
        engine.add_intersection("ix_1")
        engine.connect("ix_0", "ix_1")
        
        assert "ix_1" in engine.network.neighbors("ix_0")
    
    def test_reset(self):
        engine = SimulationEngine(SimulationConfig(seed=42))
        engine.add_intersection("ix_0")
        
        engine.step()
        engine.step()
        engine.reset()
        
        assert engine.time == 0.0
    
    def test_vehicles_generated(self):
        engine = SimulationEngine(SimulationConfig(
            seed=42, arrival_rate=2.0, road_length=50.0
        ))
        engine.add_intersection("ix_0")
        
        for _ in range(20):
            engine.step()
        
        ix = engine.network.intersections["ix_0"]
        # Check that vehicles were generated (some may have passed through)
        assert ix.total_served > 0 or ix.get_total_queue() > 0


class TestDecisionCache:
    """Test decision caching."""
    
    def test_cache_set_get(self):
        cache = DecisionCache()
        
        state = IntersectionState(
            intersection_id="test", timestamp=0,
            queue_north=10, queue_south=5,
            queue_east=8, queue_west=3,
        )
        
        decision = TrafficDecision(
            action="extend_green", phase="NS_GREEN",
            duration=20, reasoning="test", confidence=0.8,
        )
        
        cache.set(state, decision)
        cached = cache.get(state)
        
        assert cached is not None
        assert cached.action == "extend_green"
    
    def test_cache_miss(self):
        cache = DecisionCache()
        
        state1 = IntersectionState(
            intersection_id="test", timestamp=0,
            queue_north=10, queue_south=5,
            queue_east=8, queue_west=3,
        )
        
        state2 = IntersectionState(
            intersection_id="test", timestamp=0,
            queue_north=30, queue_south=25,
            queue_east=28, queue_west=23,
        )
        
        decision = TrafficDecision(
            action="extend_green", phase="NS_GREEN",
            duration=20, reasoning="test", confidence=0.8,
        )
        
        cache.set(state1, decision)
        cached = cache.get(state2)
        
        assert cached is None  # Different queue ranges
    
    def test_cache_clear(self):
        cache = DecisionCache()
        
        state = IntersectionState(
            intersection_id="test", timestamp=0,
            queue_north=10, queue_south=5,
            queue_east=8, queue_west=3,
        )
        
        decision = TrafficDecision(
            action="extend_green", phase="NS_GREEN",
            duration=20, reasoning="test", confidence=0.8,
        )
        
        cache.set(state, decision)
        cache.clear()
        
        assert cache.get(state) is None
