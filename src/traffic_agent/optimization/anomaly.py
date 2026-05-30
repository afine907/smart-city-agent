"""
Anomaly Detection — detects traffic anomalies and generates alerts.

Monitors traffic conditions and triggers alerts when:
- Queue lengths exceed thresholds
- Wait times are abnormally high
- Sudden changes in traffic flow
- Emergency vehicles detected
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Types of traffic alerts."""
    HIGH_QUEUE = "high_queue"
    LONG_WAIT = "long_wait"
    SUDDEN_CHANGE = "sudden_change"
    EMERGENCY = "emergency"
    CONGESTION = "congestion"


@dataclass
class TrafficAlert:
    """A traffic anomaly alert."""
    alert_type: AlertType
    severity: AlertSeverity
    intersection_id: str
    message: str
    value: float
    threshold: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.alert_type.value,
            "severity": self.severity.value,
            "intersection_id": self.intersection_id,
            "message": self.message,
            "value": self.value,
            "threshold": self.threshold,
            "timestamp": self.timestamp,
        }


@dataclass
class AnomalyConfig:
    """Configuration for anomaly detection thresholds."""
    queue_warning: int = 10
    queue_critical: int = 20
    wait_warning: float = 30.0
    wait_critical: float = 60.0
    change_threshold: float = 5.0  # Sudden queue change threshold
    congestion_threshold: float = 0.8  # 80% capacity


class AnomalyDetector:
    """
    Detects traffic anomalies and generates alerts.

    Usage:
        detector = AnomalyDetector()
        alerts = detector.check(state)
    """

    def __init__(self, config: AnomalyConfig | None = None):
        self.config = config or AnomalyConfig()
        self._history: dict[str, list[dict[str, Any]]] = {}
        self._alerts: list[TrafficAlert] = []

    def check(
        self,
        intersection_id: str,
        state: dict[str, Any],
    ) -> list[TrafficAlert]:
        """
        Check intersection state for anomalies.

        Args:
            intersection_id: Intersection identifier
            state: Current intersection state

        Returns:
            List of alerts generated
        """
        alerts = []

        # Check queue lengths
        total_queue = (
            state.get("queue_north", 0)
            + state.get("queue_south", 0)
            + state.get("queue_east", 0)
            + state.get("queue_west", 0)
        )

        if total_queue >= self.config.queue_critical:
            alerts.append(TrafficAlert(
                alert_type=AlertType.HIGH_QUEUE,
                severity=AlertSeverity.CRITICAL,
                intersection_id=intersection_id,
                message=f"Critical queue length: {total_queue} vehicles",
                value=total_queue,
                threshold=self.config.queue_critical,
            ))
        elif total_queue >= self.config.queue_warning:
            alerts.append(TrafficAlert(
                alert_type=AlertType.HIGH_QUEUE,
                severity=AlertSeverity.WARNING,
                intersection_id=intersection_id,
                message=f"High queue length: {total_queue} vehicles",
                value=total_queue,
                threshold=self.config.queue_warning,
            ))

        # Check wait time
        avg_wait = state.get("avg_wait_time", 0.0)
        if avg_wait >= self.config.wait_critical:
            alerts.append(TrafficAlert(
                alert_type=AlertType.LONG_WAIT,
                severity=AlertSeverity.CRITICAL,
                intersection_id=intersection_id,
                message=f"Critical wait time: {avg_wait:.1f}s",
                value=avg_wait,
                threshold=self.config.wait_critical,
            ))
        elif avg_wait >= self.config.wait_warning:
            alerts.append(TrafficAlert(
                alert_type=AlertType.LONG_WAIT,
                severity=AlertSeverity.WARNING,
                intersection_id=intersection_id,
                message=f"High wait time: {avg_wait:.1f}s",
                value=avg_wait,
                threshold=self.config.wait_warning,
            ))

        # Check sudden changes
        if intersection_id in self._history:
            last_state = self._history[intersection_id][-1]
            last_queue = (
                last_state.get("queue_north", 0)
                + last_state.get("queue_south", 0)
                + last_state.get("queue_east", 0)
                + last_state.get("queue_west", 0)
            )
            change = abs(total_queue - last_queue)
            if change >= self.config.change_threshold:
                alerts.append(TrafficAlert(
                    alert_type=AlertType.SUDDEN_CHANGE,
                    severity=AlertSeverity.WARNING,
                    intersection_id=intersection_id,
                    message=f"Sudden queue change: {change:.0f} vehicles",
                    value=change,
                    threshold=self.config.change_threshold,
                ))

        # Check emergency
        if state.get("emergency", False):
            alerts.append(TrafficAlert(
                alert_type=AlertType.EMERGENCY,
                severity=AlertSeverity.CRITICAL,
                intersection_id=intersection_id,
                message="Emergency vehicle detected",
                value=1.0,
                threshold=0.0,
            ))

        # Update history
        if intersection_id not in self._history:
            self._history[intersection_id] = []
        self._history[intersection_id].append(state)
        # Keep only recent history
        if len(self._history[intersection_id]) > 100:
            self._history[intersection_id] = self._history[intersection_id][-100:]

        self._alerts.extend(alerts)
        return alerts

    def get_recent_alerts(
        self,
        limit: int = 10,
        severity: AlertSeverity | None = None,
    ) -> list[TrafficAlert]:
        """Get recent alerts, optionally filtered by severity."""
        alerts = self._alerts
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return alerts[-limit:]

    def clear_alerts(self) -> None:
        """Clear all stored alerts."""
        self._alerts.clear()

    def get_alert_count(self) -> dict[str, int]:
        """Get alert counts by severity."""
        counts = {s.value: 0 for s in AlertSeverity}
        for alert in self._alerts:
            counts[alert.severity.value] += 1
        return counts
