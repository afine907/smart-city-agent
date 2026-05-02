"""
Tests for Traffic Simulation Engine
"""

import numpy as np
import pytest

from traffic_agent.agents.intersection import AgentConfig, IntersectionAgent
from traffic_agent.coordination.coordinator import (
    AgentState,
    ConsensusProtocol,
    CoordinationLayer,
    MessageQueue,
    MessageType,
    AgentMessage,
)
from traffic_agent.simulation.engine import (
    Intersection,
    RoadNetwork,
    SimulationConfig,
    SimulationEngine,
    Vehicle,
)


class TestSimulationEngine:
    """Test core simulation engine."""
    
    def test_single_intersection_creation(self):
        engine = SimulationEngine(SimulationConfig(seed=42))
        ix = Intersection(id="ix_0", approaches=4)
        engine.add_intersection(ix)
        
        assert "ix_0" in engine.road_network.intersections
        assert len(engine.road_network.intersections) == 1
    
    def test_observation_generation(self):
        engine = SimulationEngine(SimulationConfig(seed=42))
        ix = Intersection(id="ix_0", approaches=4)
        engine.add_intersection(ix)
        
        obs = engine.get_observation("ix_0")
        assert obs.intersection_id == "ix_0"
        assert len(obs.queue_lengths) == 4
        assert obs.current_phase == 0
    
    def test_step_advances_time(self):
        engine = SimulationEngine(SimulationConfig(dt=1.0, seed=42))
        ix = Intersection(id="ix_0", approaches=4)
        engine.add_intersection(ix)
        
        initial_time = engine.time
        engine.step()
        assert engine.time == initial_time + 1.0
    
    def test_action_changes_phase(self):
        engine = SimulationEngine(SimulationConfig(seed=42))
        ix = Intersection(id="ix_0", approaches=4)
        engine.add_intersection(ix)
        
        engine.apply_action("ix_0", phase=2, duration=30)
        assert engine.road_network.intersections["ix_0"].current_phase == 2
    
    def test_metrics_collection(self):
        engine = SimulationEngine(SimulationConfig(seed=42))
        ix = Intersection(id="ix_0", approaches=4)
        engine.add_intersection(ix)
        
        engine.run(num_steps=100)
        metrics = engine.metrics.get_summary()
        
        assert "avg_wait_time" in metrics
        assert "throughput" in metrics
    
    def test_reset(self):
        engine = SimulationEngine(SimulationConfig(seed=42))
        ix = Intersection(id="ix_0", approaches=4)
        engine.add_intersection(ix)
        
        engine.run(num_steps=50)
        engine.reset()
        
        assert engine.time == 0.0
        assert engine.step_count == 0
    
    def test_grid_connection(self):
        engine = SimulationEngine(SimulationConfig(seed=42))
        
        for i in range(4):
            engine.add_intersection(Intersection(id=f"ix_{i}"))
        
        engine.connect("ix_0", "ix_1")
        engine.connect("ix_1", "ix_2")
        
        neighbors = engine.road_network.get_neighbors("ix_0")
        assert "ix_1" in neighbors
        assert "ix_2" not in neighbors


class TestIntersectionAgent:
    """Test RL intersection agent."""
    
    def test_agent_creation(self):
        agent = IntersectionAgent(agent_id="ix_0", num_approaches=4)
        assert agent.agent_id == "ix_0"
        assert agent.is_ready
    
    def test_observation_and_action(self):
        engine = SimulationEngine(SimulationConfig(seed=42))
        ix = Intersection(id="ix_0", approaches=4)
        engine.add_intersection(ix)
        
        agent = IntersectionAgent(agent_id="ix_0", num_approaches=4)
        obs = engine.get_observation("ix_0")
        
        agent.observe(obs)
        action = agent.act()
        
        assert 0 <= action.phase < 4
        assert action.min_green <= action.duration <= action.max_green
    
    def test_agent_metrics(self):
        agent = IntersectionAgent(agent_id="ix_0")
        metrics = agent.get_metrics()
        
        assert "agent/episode_count" in metrics
        assert "agent/avg_reward" in metrics
    
    def test_epsilon_decay(self):
        config = AgentConfig(epsilon_start=1.0, epsilon_decay=0.9)
        agent = IntersectionAgent(agent_id="ix_0", config=config)
        
        initial_epsilon = agent.epsilon
        agent.reset()
        
        assert agent.epsilon < initial_epsilon
    
    def test_save_and_load(self, tmp_path):
        agent = IntersectionAgent(agent_id="ix_0", num_approaches=4)
        
        save_path = tmp_path / "agent.json"
        agent.save(str(save_path))
        
        agent2 = IntersectionAgent(agent_id="ix_0", num_approaches=4)
        agent2.load(str(save_path))
        
        assert agent2.epsilon == agent.epsilon


class TestCoordination:
    """Test multi-agent coordination."""
    
    def test_message_queue(self):
        mq = MessageQueue()
        
        msg = AgentMessage(
            sender_id="agent_a",
            receiver_id="agent_b",
            msg_type=MessageType.STATE_UPDATE,
            payload={"queue": [5, 3, 2, 4]},
            timestamp=100.0,
        )
        mq.send(msg)
        
        messages = mq.receive("agent_b", current_time=101.0)
        assert len(messages) == 1
        assert messages[0].sender_id == "agent_a"
    
    def test_broadcast(self):
        mq = MessageQueue()
        
        msg = AgentMessage(
            sender_id="agent_a",
            receiver_id="*",
            msg_type=MessageType.EMERGENCY_BROADCAST,
            payload={"approach": 2},
            timestamp=100.0,
        )
        mq.send(msg)
        
        for agent_id in ["agent_b", "agent_c", "agent_d"]:
            messages = mq.receive(agent_id, current_time=101.0)
            assert len(messages) == 1
    
    def test_message_expiry(self):
        mq = MessageQueue()
        
        msg = AgentMessage(
            sender_id="agent_a",
            receiver_id="agent_b",
            msg_type=MessageType.STATE_UPDATE,
            payload={},
            timestamp=100.0,
            ttl=5.0,
        )
        mq.send(msg)
        
        # Within TTL
        messages = mq.receive("agent_b", current_time=103.0)
        assert len(messages) == 1
        
        # After TTL
        messages = mq.receive("agent_b", current_time=110.0)
        assert len(messages) == 0
    
    def test_consensus_reach(self):
        consensus = ConsensusProtocol()
        
        # All neighbors agree on 0.8
        result = consensus.reach_consensus(
            agent_id="a",
            own_value=0.8,
            neighbor_values={"b": 0.8, "c": 0.8},
        )
        
        assert abs(result - 0.8) < 0.01
    
    def test_consensus_with_disagreement(self):
        consensus = ConsensusProtocol()
        
        result = consensus.reach_consensus(
            agent_id="a",
            own_value=0.5,
            neighbor_values={"b": 0.9, "c": 0.9},
        )
        
        # Should be between 0.5 and 0.9
        assert 0.5 < result < 0.9
    
    def test_coordination_layer(self):
        graph = {
            "ix_0": ["ix_1"],
            "ix_1": ["ix_0", "ix_2"],
            "ix_2": ["ix_1"],
        }
        
        coordinator = CoordinationLayer(graph)
        
        # Update states
        for ix_id in ["ix_0", "ix_1", "ix_2"]:
            state = AgentState(
                intersection_id=ix_id,
                queue_lengths=np.array([5, 3, 2, 4]),
                current_phase=0,
                phase_duration=10.0,
            )
            coordinator.update_state(state)
        
        # Get coordinated observation
        obs = coordinator.get_coordinated_observation("ix_0")
        
        assert "embedding" in obs
        assert "consensus_value" in obs
        assert "neighbor_queue_lengths" in obs


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_simulation(self):
        engine = SimulationEngine(SimulationConfig(seed=42))
        metrics = engine.run(num_steps=10)
        
        assert metrics["throughput"] == 0
    
    def test_single_step(self):
        engine = SimulationEngine(SimulationConfig(seed=42))
        ix = Intersection(id="ix_0", approaches=4)
        engine.add_intersection(ix)
        
        obs = engine.step()
        assert "ix_0" in obs
    
    def test_agent_without_observation(self):
        agent = IntersectionAgent(agent_id="ix_0")
        action = agent.act()
        
        # Should return safe default
        assert action.phase == 0
