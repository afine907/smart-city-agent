"""
Response Parser — Parse and validate LLM responses.

Handles JSON extraction, validation, and fallback for two models:
1. TimingAdjustment (new): LLM suggests ±10s adjustment to baseline timing
2. TrafficDecision (legacy): LLM controls phase and duration directly
"""

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# Valid actions and phases (legacy)
VALID_ACTIONS = {"extend_green", "switch_phase", "emergency"}
VALID_PHASES = {"NS_GREEN", "EW_GREEN", "NS_YELLOW", "EW_YELLOW"}
DURATION_RANGE = (10, 60)

# Timing adjustment constraints
ADJUSTMENT_RANGE = (-10, 10)


@dataclass
class TrafficDecision:
    """Parsed traffic signal decision."""
    action: str
    phase: str
    duration: int
    reasoning: str
    confidence: float
    coordination_message: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "action": self.action,
            "phase": self.phase,
            "duration": self.duration,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "coordination_message": self.coordination_message,
        }


class ResponseParser:
    """
    Parse LLM responses into structured decisions.
    
    Handles:
    - Clean JSON responses
    - JSON embedded in markdown code blocks
    - Partial/malformed responses
    - Validation and normalization
    """
    
    @staticmethod
    def parse(response_text: str) -> Optional[TrafficDecision]:
        """
        Parse LLM response text into TrafficDecision.
        
        Returns None if parsing fails.
        """
        # Try direct JSON parse
        data = ResponseParser._extract_json(response_text)
        if data is None:
            return None
        
        return ResponseParser._validate_and_create(data)
    
    @staticmethod
    def _extract_json(text: str) -> Optional[Dict]:
        """Extract JSON from text (handles markdown code blocks)."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Try extracting from code block
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'\{.*\}',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1) if match.lastindex else match.group(0))
                except (json.JSONDecodeError, IndexError):
                    continue
        
        return None
    
    @staticmethod
    def _validate_and_create(data: Dict) -> Optional[TrafficDecision]:
        """Validate parsed data and create TrafficDecision."""
        # Validate action
        action = data.get("action", "")
        if action not in VALID_ACTIONS:
            # Try to fix common mistakes
            if "extend" in action.lower():
                action = "extend_green"
            elif "switch" in action.lower() or "change" in action.lower():
                action = "switch_phase"
            elif "emergency" in action.lower():
                action = "emergency"
            else:
                return None
        
        # Validate phase
        phase = data.get("phase", "NS_GREEN").upper().replace(" ", "_")
        if phase not in VALID_PHASES:
            if "NS" in phase or "南北" in phase:
                phase = "NS_GREEN"
            elif "EW" in phase or "东西" in phase:
                phase = "EW_GREEN"
            else:
                phase = "NS_GREEN"  # Default
        
        # Validate duration
        duration = data.get("duration", 15)
        try:
            duration = int(duration)
        except (ValueError, TypeError):
            duration = 15
        duration = max(DURATION_RANGE[0], min(DURATION_RANGE[1], duration))
        
        # Extract reasoning
        reasoning = data.get("reasoning", "No reasoning provided")
        if isinstance(reasoning, list):
            reasoning = " ".join(str(r) for r in reasoning)
        
        # Extract confidence
        confidence = data.get("confidence", 0.7)
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.7
        
        # Extract coordination message
        coord_msg = data.get("coordination_message")
        if coord_msg and not isinstance(coord_msg, str):
            coord_msg = str(coord_msg)
        
        return TrafficDecision(
            action=action,
            phase=phase,
            duration=duration,
            reasoning=reasoning,
            confidence=confidence,
            coordination_message=coord_msg,
        )
    
    @staticmethod
    def fallback(reason: str = "Unknown error") -> TrafficDecision:
        """Create a safe fallback decision."""
        return TrafficDecision(
            action="extend_green",
            phase="NS_GREEN",
            duration=15,
            reasoning=f"解析失败，使用规则回退: {reason}",
            confidence=0.3,
        )


# ─── New: TimingAdjustment (±10s model) ────────────────────────

@dataclass
class TimingAdjustment:
    """
    LLM output for the ±10s timing adjustment model.

    The LLM does NOT control the signal directly.
    It only suggests small timing adjustments on top of a fixed baseline plan.
    """
    adjustment: int              # -10 to +10 seconds
    reasoning: str               # Chinese explanation
    confidence: float            # 0.0 to 1.0
    alerts: List[str] = field(default_factory=list)  # warning messages
    source: str = "llm"          # "llm", "rule", or "cache"

    def to_dict(self) -> Dict:
        return {
            "adjustment": self.adjustment,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "alerts": self.alerts,
            "source": self.source,
        }

    @staticmethod
    def no_adjustment(reason: str = "当前状态无需调整") -> "TimingAdjustment":
        """Create a zero-adjustment response."""
        return TimingAdjustment(
            adjustment=0,
            reasoning=reason,
            confidence=0.8,
            source="rule",
        )


class TimingAdjustmentParser:
    """
    Parse LLM responses into TimingAdjustment.

    Handles JSON extraction, validation, and clamping to ±10s.
    """

    @staticmethod
    def parse(response_text: str) -> Optional[TimingAdjustment]:
        """Parse LLM response text into TimingAdjustment."""
        data = ResponseParser._extract_json(response_text)
        if data is None:
            return None
        return TimingAdjustmentParser._validate_and_create(data)

    @staticmethod
    def _validate_and_create(data: Dict) -> Optional[TimingAdjustment]:
        """Validate parsed data and create TimingAdjustment."""
        # Validate adjustment
        adjustment = data.get("adjustment", 0)
        try:
            adjustment = int(adjustment)
        except (ValueError, TypeError):
            adjustment = 0
        adjustment = max(ADJUSTMENT_RANGE[0], min(ADJUSTMENT_RANGE[1], adjustment))

        # Extract reasoning
        reasoning = data.get("reasoning", "无解释")
        if isinstance(reasoning, list):
            reasoning = " ".join(str(r) for r in reasoning)
        if not isinstance(reasoning, str):
            reasoning = str(reasoning)

        # Extract confidence
        confidence = data.get("confidence", 0.7)
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.7

        # Extract alerts
        alerts = data.get("alerts", [])
        if not isinstance(alerts, list):
            alerts = [str(alerts)] if alerts else []
        alerts = [str(a) for a in alerts]

        return TimingAdjustment(
            adjustment=adjustment,
            reasoning=reasoning,
            confidence=confidence,
            alerts=alerts,
            source="llm",
        )

    @staticmethod
    def fallback(reason: str = "LLM响应解析失败") -> TimingAdjustment:
        """Create a safe fallback: no adjustment."""
        return TimingAdjustment(
            adjustment=0,
            reasoning=f"解析失败，不进行调整: {reason}",
            confidence=0.2,
            alerts=["LLM响应解析失败，使用安全默认值"],
            source="fallback",
        )
