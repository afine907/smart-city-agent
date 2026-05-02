"""
Smart City Agent — AI-Powered Traffic Signal Control

Multi-Agent Reinforcement Learning for Smart City Intersections.
"""

__version__ = "0.1.0"
__author__ = "afine907"

from traffic_agent.agents.base_agent import BaseAgent
from traffic_agent.agents.intersection import IntersectionAgent
from traffic_agent.simulation.engine import SimulationEngine
from traffic_agent.coordination.coordinator import CoordinationLayer

__all__ = [
    "BaseAgent",
    "IntersectionAgent",
    "SimulationEngine",
    "CoordinationLayer",
]
