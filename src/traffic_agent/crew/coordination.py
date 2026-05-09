"""
Multi-Agent Coordination — Conflict detection and resolution.

Detects when neighboring intersections have conflicting signal phases,
advises green wave offsets, and resolves conflicts by priority.
"""

from typing import Dict, List, Optional, Tuple

from traffic_agent.llm.parser import TrafficDecision
from traffic_agent.tools.traffic_tools import IntersectionState


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


class GreenWaveAdvisor:
    """Suggests phase offsets to create green waves along corridors."""

    @staticmethod
    def suggest_offsets(
        decisions: Dict[str, TrafficDecision],
        graph: Dict[str, List[str]],
        corridor_direction: str = "EW",
    ) -> Dict[str, int]:
        """
        Returns recommended phase_duration adjustments for green wave.

        Identifies corridors (rows for EW, columns for NS) and suggests
        progressive timing adjustments so vehicles encounter green lights.
        """
        suggestions: Dict[str, int] = {}

        # Group intersections into corridors
        corridors = GreenWaveAdvisor._identify_corridors(graph, corridor_direction)

        for corridor in corridors:
            # Sort intersections by position in corridor
            sorted_ixs = sorted(corridor)

            for i, ix_id in enumerate(sorted_ixs):
                if ix_id not in decisions:
                    continue
                decision = decisions[ix_id]
                # Progressive offset: earlier intersections get shorter green
                # to let traffic arrive at later intersections during their green
                offset = -2 * i  # -2s per position upstream
                offset = max(-10, min(10, offset))
                if offset != 0:
                    suggestions[ix_id] = offset

        return suggestions

    @staticmethod
    def _identify_corridors(
        graph: Dict[str, List[str]],
        direction: str,
    ) -> List[List[str]]:
        """Group intersections into corridors based on direction."""
        corridors: List[List[str]] = []
        visited: set = set()

        for ix_id in graph:
            if ix_id in visited:
                continue
            # Parse ix_row_col
            parts = ix_id.split("_")
            row, col = int(parts[1]), int(parts[2])

            corridor = [ix_id]
            visited.add(ix_id)

            # Find connected intersections along the corridor direction
            if direction == "EW":
                # Same row, adjacent columns
                for other_id in graph:
                    if other_id in visited:
                        continue
                    parts2 = other_id.split("_")
                    row2, col2 = int(parts2[1]), int(parts2[2])
                    if row2 == row and abs(col2 - col) == 1:
                        corridor.append(other_id)
                        visited.add(other_id)
            else:
                # Same column, adjacent rows
                for other_id in graph:
                    if other_id in visited:
                        continue
                    parts2 = other_id.split("_")
                    row2, col2 = int(parts2[1]), int(parts2[2])
                    if col2 == col and abs(row2 - row) == 1:
                        corridor.append(other_id)
                        visited.add(other_id)

            if len(corridor) > 1:
                corridors.append(corridor)

        return corridors


class PriorityResolver:
    """Resolves conflicts between intersection decisions using priority rules."""

    @staticmethod
    def resolve(
        decisions: Dict[str, TrafficDecision],
        states: Dict[str, IntersectionState],
        conflicts: List[Tuple[str, str, str]],
    ) -> Dict[str, TrafficDecision]:
        """
        Returns resolved decisions with conflicts handled.

        Priority rules:
        1. Emergency vehicles always win
        2. Higher total queue gets priority
        3. Longer wait time gets priority
        4. Tie-breaking by intersection ID (deterministic)
        """
        if not conflicts:
            return decisions

        resolved = dict(decisions)

        for ix_a, ix_b, conflict_type in conflicts:
            if ix_a not in resolved or ix_b not in resolved:
                continue

            a_decision = resolved[ix_a]
            b_decision = resolved[ix_b]
            a_state = states.get(ix_a)
            b_state = states.get(ix_b)

            if a_state is None or b_state is None:
                continue

            # Determine winner
            winner_id, loser_id = PriorityResolver._pick_winner(
                ix_a, ix_b, a_state, b_state
            )

            if loser_id in resolved:
                # Loser gets the opposite phase
                winner_decision = resolved[winner_id]
                loser_phase = (
                    "EW_GREEN" if winner_decision.phase == "NS_GREEN"
                    else "NS_GREEN"
                )
                resolved[loser_id] = TrafficDecision(
                    action="switch_phase",
                    phase=loser_phase,
                    duration=20,
                    reasoning=f"优先级让步给 {winner_id}",
                    confidence=0.7,
                )

        return resolved

    @staticmethod
    def _pick_winner(
        ix_a: str, ix_b: str,
        state_a: IntersectionState, state_b: IntersectionState,
    ) -> Tuple[str, str]:
        """Pick the winner based on priority rules. Returns (winner_id, loser_id)."""
        # Rule 1: Emergency vehicles always win
        if state_a.emergency and not state_b.emergency:
            return ix_a, ix_b
        if state_b.emergency and not state_a.emergency:
            return ix_b, ix_a

        # Rule 2: Higher total queue gets priority
        queue_a = state_a.get_total_queue()
        queue_b = state_b.get_total_queue()
        if queue_a != queue_b:
            return (ix_a, ix_b) if queue_a > queue_b else (ix_b, ix_a)

        # Rule 3: Longer wait time gets priority
        wait_a = state_a.wait_north + state_a.wait_south + state_a.wait_east + state_a.wait_west
        wait_b = state_b.wait_north + state_b.wait_south + state_b.wait_east + state_b.wait_west
        if wait_a != wait_b:
            return (ix_a, ix_b) if wait_a > wait_b else (ix_b, ix_a)

        # Rule 4: Tie-breaking by intersection ID (deterministic)
        return (ix_a, ix_b) if ix_a < ix_b else (ix_b, ix_a)
