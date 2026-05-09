"""
Multi-Agent Coordination — Conflict detection between intersection agents.

Detects when neighboring intersections have conflicting signal phases.
"""

from typing import Dict, List, Tuple

from traffic_agent.llm.parser import TrafficDecision


class ConflictDetector:
    """Detect conflicts between neighboring agents."""

    @staticmethod
    def detect(
        decisions: Dict[str, TrafficDecision],
        graph: Dict[str, List[str]],
    ) -> List[Tuple[str, str, str]]:
        """
        Detect conflicts between neighboring intersections.

        Returns list of (agent1, agent2, conflict_type) tuples.
        """
        conflicts = []

        for ix_id, decision in decisions.items():
            neighbors = graph.get(ix_id, [])

            for nid in neighbors:
                if nid in decisions:
                    neighbor_decision = decisions[nid]

                    # Conflict: adjacent intersections with incompatible phases
                    if (decision.phase == "NS_GREEN" and
                        neighbor_decision.phase == "EW_GREEN"):
                        conflicts.append((ix_id, nid, "phase_mismatch"))

                    # Conflict: both want to extend green excessively
                    if (decision.duration > 45 and
                        neighbor_decision.duration > 45):
                        conflicts.append((ix_id, nid, "excessive_green"))

        return conflicts
