"""
Rule Engine — Fast rule-based timing adjustments.

Zero cost, instant decisions for simple/obvious traffic patterns.
Returns None when the situation requires LLM reasoning.

Rules are tuned for the ±10s adjustment model:
- Rule 1: Low traffic → no adjustment (0)
- Rule 2: High current-direction queue → extend +8~10s
- Rule 3: Moderate current-direction queue → extend +3~7s
- Rule 4: Opposing queue 2x current → shorten -5~10s
- Rule 5: Pedestrians waiting → extend +3~5s
- Rule 6: Rising trend → extend +2~5s
"""

from typing import Dict, List, Optional

from traffic_agent.llm.parser import TimingAdjustment


class TimingRuleEngine:
    """
    Rule-based timing adjustment engine.

    Returns TimingAdjustment if rules apply, None if LLM is needed.

    Usage:
        engine = TimingRuleEngine()
        adjustment = engine.decide(detector_data, signal_state, trend)
        if adjustment is None:
            adjustment = call_llm(detector_data, signal_state, trend)
    """

    def __init__(
        self,
        low_queue_threshold: int = 3,
        high_queue_threshold: int = 15,
        moderate_queue_threshold: int = 8,
        pedestrian_threshold: int = 3,
    ):
        self.low_queue = low_queue_threshold
        self.high_queue = high_queue_threshold
        self.moderate_queue = moderate_queue_threshold
        self.pedestrian_threshold = pedestrian_threshold
        self._decisions_made = 0
        self._decisions_skipped = 0

    def decide(
        self,
        detector_data: Dict,
        signal_state: Dict,
        trend: Optional[Dict[str, List[int]]] = None,
    ) -> Optional[TimingAdjustment]:
        """
        Make a rule-based timing adjustment.

        Args:
            detector_data: dict with "readings" per direction
            signal_state: dict with "current_phase", "phase_remaining", etc.
            trend: optional dict with trend data per direction

        Returns:
            TimingAdjustment if rules apply, None if LLM is needed.
        """
        readings = detector_data.get("readings", {})
        current_phase = signal_state.get("current_phase", "NS_GREEN")
        phase_remaining = signal_state.get("phase_remaining", 30.0)

        # Determine which direction is currently green
        is_ns_green = "NS_GREEN" in current_phase
        is_ew_green = "EW_GREEN" in current_phase

        # Not a green phase — no adjustment possible
        if not is_ns_green and not is_ew_green:
            self._decisions_made += 1
            return TimingAdjustment.no_adjustment(
                f"当前为{current_phase}过渡相位，不进行调整"
            )

        # Get queue counts
        north_v = readings.get("north", {}).get("vehicles", 0)
        south_v = readings.get("south", {}).get("vehicles", 0)
        east_v = readings.get("east", {}).get("vehicles", 0)
        west_v = readings.get("west", {}).get("vehicles", 0)

        ns_queue = north_v + south_v
        ew_queue = east_v + west_v

        # Get pedestrian counts
        north_p = readings.get("north", {}).get("pedestrians", 0)
        south_p = readings.get("south", {}).get("pedestrians", 0)
        east_p = readings.get("east", {}).get("pedestrians", 0)
        west_p = readings.get("west", {}).get("pedestrians", 0)

        ns_peds = north_p + south_p
        ew_peds = east_p + west_p

        total_vehicles = ns_queue + ew_queue
        total_peds = ns_peds + ew_peds

        # Current green queue (the direction that currently has green)
        if is_ns_green:
            green_queue = ns_queue
            cross_queue = ew_queue
            green_peds = ns_peds
        elif is_ew_green:
            green_queue = ew_queue
            cross_queue = ns_queue
            green_peds = ew_peds
        else:
            # Yellow or all-red: no adjustment
            self._decisions_made += 1
            return TimingAdjustment.no_adjustment(
                f"当前为{current_phase}过渡相位，不进行调整"
            )

        # ─── Rule 1: Low traffic → no adjustment ───
        if total_vehicles < self.low_queue and total_peds == 0:
            self._decisions_made += 1
            return TimingAdjustment(
                adjustment=0,
                reasoning=f"交通量低（{total_vehicles}辆），无需调整",
                confidence=0.9,
                source="rule",
            )

        # ─── Rule 2: High current-direction queue → extend ───
        if green_queue >= self.high_queue:
            adjustment = min(10, max(8, (green_queue - self.high_queue) // 2 + 8))
            self._decisions_made += 1
            return TimingAdjustment(
                adjustment=adjustment,
                reasoning=(
                    f"当前绿灯方向排队{green_queue}辆，接近饱和，"
                    f"建议延长{adjustment}秒以消化积压"
                ),
                confidence=0.85,
                alerts=[f"绿灯方向排队{green_queue}辆，接近饱和"] if green_queue >= 20 else [],
                source="rule",
            )

        # ─── Rule 3: Moderate current-direction queue → extend ───
        if green_queue >= self.moderate_queue:
            # Linear mapping: 8→3s, 10→5s, 14→7s
            adjustment = max(3, min(7, (green_queue - self.moderate_queue) + 3))
            self._decisions_made += 1
            return TimingAdjustment(
                adjustment=adjustment,
                reasoning=f"当前绿灯方向排队{green_queue}辆，建议延长{adjustment}秒",
                confidence=0.8,
                source="rule",
            )

        # ─── Rule 4: Cross queue 2x current → shorten ───
        if cross_queue > 0 and cross_queue >= green_queue * 2 and phase_remaining > 15:
            adjustment = max(-10, min(-5, -(cross_queue - green_queue) // 3))
            self._decisions_made += 1
            return TimingAdjustment(
                adjustment=adjustment,
                reasoning=(
                    f"对向排队{cross_queue}辆是当前方向{green_queue}辆的{cross_queue/max(1,green_queue):.1f}倍，"
                    f"建议缩短{abs(adjustment)}秒让行"
                ),
                confidence=0.8,
                alerts=[f"对向排队{cross_queue}辆，严重不平衡"],
                source="rule",
            )

        # ─── Rule 5: Pedestrians waiting → extend ───
        if green_peds >= self.pedestrian_threshold:
            adjustment = max(3, min(5, green_peds // 2))
            self._decisions_made += 1
            return TimingAdjustment(
                adjustment=adjustment,
                reasoning=f"当前方向有{green_peds}名行人等待过街，建议延长{adjustment}秒",
                confidence=0.75,
                source="rule",
            )

        # ─── Rule 6: Rising trend → extend ───
        if trend:
            trend_key = "ns_total" if "NS" in current_phase else "ew_total"
            trend_data = trend.get(trend_key, [])
            if len(trend_data) >= 3:
                recent = trend_data[-3:]
                if all(recent[i] <= recent[i + 1] for i in range(len(recent) - 1)):
                    # Monotonically increasing
                    adjustment = max(2, min(5, (recent[-1] - recent[0]) // 3))
                    self._decisions_made += 1
                    return TimingAdjustment(
                        adjustment=adjustment,
                        reasoning=f"绿灯方向流量呈上升趋势{recent}，建议延长{adjustment}秒",
                        confidence=0.7,
                        source="rule",
                    )

        # Rules don't cover this — need LLM
        self._decisions_skipped += 1
        return None

    def get_stats(self) -> dict:
        """Return rule engine statistics."""
        total = self._decisions_made + self._decisions_skipped
        return {
            "decisions_made": self._decisions_made,
            "decisions_skipped": self._decisions_skipped,
            "total": total,
            "rule_coverage": self._decisions_made / max(1, total),
        }

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._decisions_made = 0
        self._decisions_skipped = 0


# Backward compatibility alias
RuleEngine = TimingRuleEngine
