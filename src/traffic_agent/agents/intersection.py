"""
CrewAI Agents — Multi-Agent traffic control using CrewAI.

Defines the agent roles, goals, and backstories for the traffic control crew.
"""

from typing import Dict, List, Optional

from traffic_agent.llm.client import LLMClient, LLMConfig
from traffic_agent.tools.traffic_tools import (
    TRAFFIC_EXPERT_PROMPT,
    COORDINATOR_PROMPT,
    IntersectionState,
    TrafficObservationTool,
    NeighborStateTool,
    CoordinationMessageTool,
)


class IntersectionAgentFactory:
    """Factory for creating intersection traffic agents."""
    
    @staticmethod
    def create(
        intersection_id: str,
        neighbors: List[str],
        llm_config: Optional[LLMConfig] = None,
    ):
        """
        Create a CrewAI Agent for an intersection.
        
        Args:
            intersection_id: ID of the intersection to control
            neighbors: List of neighbor intersection IDs
            llm_config: LLM configuration
        
        Returns:
            CrewAI Agent instance
        """
        try:
            from crewai import Agent
        except ImportError:
            raise ImportError("CrewAI not installed. Run: pip install crewai")
        
        goal = (
            f"Minimize vehicle wait time at {intersection_id} intersection "
            f"while maintaining safety. Coordinate with neighboring "
            f"intersections ({', '.join(neighbors)}) to create green waves."
        )
        
        return Agent(
            role=f"Traffic Signal Controller — {intersection_id}",
            goal=goal,
            backstory=TRAFFIC_EXPERT_PROMPT.format(
                intersection_id=intersection_id
            ),
            tools=[
                TrafficObservationTool(),
                NeighborStateTool(),
            ],
            llm=llm_config.fast_model if llm_config else "gpt-4o-mini",
            allow_delegation=False,
            max_iter=3,
            verbose=True,
        )


class CoordinatorAgentFactory:
    """Factory for creating the coordination supervisor agent."""
    
    @staticmethod
    def create(
        intersection_ids: List[str],
        llm_config: Optional[LLMConfig] = None,
    ):
        """
        Create a CrewAI Agent for coordination.
        
        Args:
            intersection_ids: All intersection IDs in the network
            llm_config: LLM configuration
        
        Returns:
            CrewAI Agent instance
        """
        try:
            from crewai import Agent
        except ImportError:
            raise ImportError("CrewAI not installed. Run: pip install crewai")
        
        return Agent(
            role="Traffic Coordination Supervisor",
            goal=(
                "Resolve conflicts between intersection agents and "
                "optimize city-wide traffic flow across all "
                f"intersections: {', '.join(intersection_ids)}"
            ),
            backstory=COORDINATOR_PROMPT,
            tools=[
                CoordinationMessageTool(),
            ],
            llm=llm_config.smart_model if llm_config else "gpt-4o",
            allow_delegation=True,
            max_iter=5,
            verbose=True,
        )
