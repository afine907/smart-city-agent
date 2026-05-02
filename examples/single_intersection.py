"""
Example: Single Intersection RL Training

Train an RL agent to control traffic signals at a single intersection.
"""

import numpy as np

from traffic_agent.agents.intersection import AgentConfig, IntersectionAgent
from traffic_agent.simulation.engine import Intersection, SimulationConfig, SimulationEngine


def main():
    print("🚦 Single Intersection Training Example")
    print("=" * 50)
    
    # Create simulation
    config = SimulationConfig(
        dt=0.1,
        max_steps=2000,
        arrival_rate=0.5,
        seed=42,
    )
    engine = SimulationEngine(config)
    
    # Add intersection
    ix = Intersection(id="main_intersection", approaches=4)
    engine.add_intersection(ix)
    
    # Create agent
    agent_config = AgentConfig(
        learning_rate=1e-3,
        epsilon_start=1.0,
        epsilon_end=0.1,
        epsilon_decay=0.999,
    )
    agent = IntersectionAgent(
        agent_id="main_intersection",
        config=agent_config,
        num_approaches=4,
        num_phases=4,
    )
    
    # Training loop
    print("\n📚 Training...")
    for episode in range(10):
        engine.reset()
        agent.reset()
        
        episode_reward = 0.0
        for step in range(200):
            # Get observation
            obs = engine.get_observation("main_intersection")
            
            # Agent decides
            agent.observe(obs)
            action = agent.act()
            
            # Apply action
            engine.apply_action("main_intersection", action.phase, action.duration)
            
            # Step simulation
            engine.step()
            
            # Get new observation
            next_obs = engine.get_observation("main_intersection")
            
            # Calculate reward (negative queue length)
            reward = -np.sum(next_obs.queue_lengths) * 0.1
            
            # Learn
            agent.learn(obs, action, reward, next_obs, done=False)
            episode_reward += reward
        
        metrics = agent.get_metrics()
        print(
            f"Episode {episode+1:2d} | "
            f"Reward: {episode_reward:8.1f} | "
            f"Epsilon: {agent.epsilon:.3f} | "
            f"Avg Wait: {metrics['agent/avg_reward']:.2f}"
        )
    
    print("\n✅ Training complete!")
    
    # Save agent
    agent.save("trained_agent.json")
    print("💾 Agent saved to trained_agent.json")


if __name__ == "__main__":
    main()
