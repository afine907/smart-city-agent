"""
Traffic Prediction — Short-term traffic flow prediction.

Uses historical data and trend analysis to predict future traffic
conditions for proactive signal timing adjustments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PredictionResult:
    """Prediction for a single time step."""

    step: int
    predicted_queue: float
    predicted_wait: float
    confidence: float  # 0.0 to 1.0
    trend: str  # "increasing", "decreasing", "stable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "predicted_queue": self.predicted_queue,
            "predicted_wait": self.predicted_wait,
            "confidence": self.confidence,
            "trend": self.trend,
        }


@dataclass
class TrafficPredictor:
    """
    Short-term traffic predictor using moving average and trend analysis.

    Predicts future queue lengths and wait times based on recent history.
    """

    window_size: int = 10
    prediction_horizon: int = 5  # steps ahead

    # Historical data
    _queue_history: list[float] = field(default_factory=list)
    _wait_history: list[float] = field(default_factory=list)

    def update(self, queue_length: float, wait_time: float) -> None:
        """Update with new observation."""
        self._queue_history.append(queue_length)
        self._wait_history.append(wait_time)

        # Keep only recent history
        max_history = self.window_size * 3
        if len(self._queue_history) > max_history:
            self._queue_history = self._queue_history[-max_history:]
            self._wait_history = self._wait_history[-max_history:]

    def predict(self, steps_ahead: int = 1) -> PredictionResult:
        """
        Predict traffic conditions steps_ahead into the future.

        Uses exponential moving average with trend detection.
        """
        if len(self._queue_history) < 2:
            return PredictionResult(
                step=steps_ahead,
                predicted_queue=0.0,
                predicted_wait=0.0,
                confidence=0.0,
                trend="stable",
            )

        # Calculate trend
        recent = self._queue_history[-self.window_size:]
        if len(recent) >= 2:
            trend_slope = (recent[-1] - recent[0]) / len(recent)
        else:
            trend_slope = 0.0

        # Determine trend direction
        if abs(trend_slope) < 0.5:
            trend = "stable"
        elif trend_slope > 0:
            trend = "increasing"
        else:
            trend = "decreasing"

        # Exponential moving average
        alpha = 0.3  # smoothing factor
        ema_queue = recent[0]
        for q in recent[1:]:
            ema_queue = alpha * q + (1 - alpha) * ema_queue

        # Extrapolate with trend
        predicted_queue = ema_queue + trend_slope * steps_ahead
        predicted_queue = max(0.0, predicted_queue)

        # Similar for wait time
        recent_waits = self._wait_history[-self.window_size:]
        if recent_waits:
            ema_wait = recent_waits[0]
            for w in recent_waits[1:]:
                ema_wait = alpha * w + (1 - alpha) * ema_wait

            if len(recent_waits) >= 2:
                wait_slope = (recent_waits[-1] - recent_waits[0]) / len(recent_waits)
            else:
                wait_slope = 0.0

            predicted_wait = ema_wait + wait_slope * steps_ahead
            predicted_wait = max(0.0, predicted_wait)
        else:
            predicted_wait = 0.0

        # Confidence decreases with prediction distance
        base_confidence = min(1.0, len(self._queue_history) / self.window_size)
        confidence = base_confidence * (0.9 ** steps_ahead)

        return PredictionResult(
            step=steps_ahead,
            predicted_queue=predicted_queue,
            predicted_wait=predicted_wait,
            confidence=confidence,
            trend=trend,
        )

    def predict_multiple(self, horizon: int | None = None) -> list[PredictionResult]:
        """Predict multiple steps ahead."""
        horizon = horizon or self.prediction_horizon
        return [self.predict(steps_ahead=i + 1) for i in range(horizon)]

    def get_trend(self) -> str:
        """Get current traffic trend."""
        if len(self._queue_history) < 2:
            return "stable"

        recent = self._queue_history[-self.window_size:]
        if len(recent) < 2:
            return "stable"

        slope = (recent[-1] - recent[0]) / len(recent)
        if abs(slope) < 0.5:
            return "stable"
        return "increasing" if slope > 0 else "decreasing"

    def reset(self) -> None:
        """Reset predictor state."""
        self._queue_history.clear()
        self._wait_history.clear()
