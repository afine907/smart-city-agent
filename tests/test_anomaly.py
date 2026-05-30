"""
Tests for Anomaly Detection.
"""

import pytest

from traffic_agent.optimization.anomaly import (
    AlertSeverity,
    AlertType,
    AnomalyConfig,
    AnomalyDetector,
    TrafficAlert,
)


class TestAnomalyDetector:
    """Test anomaly detection."""

    @pytest.fixture
    def detector(self):
        return AnomalyDetector()

    @pytest.fixture
    def custom_detector(self):
        config = AnomalyConfig(
            queue_warning=5,
            queue_critical=15,
            wait_warning=20.0,
            wait_critical=40.0,
            change_threshold=3.0,
        )
        return AnomalyDetector(config=config)

    def test_no_alerts_normal_traffic(self, detector):
        state = {
            "queue_north": 2, "queue_south": 1,
            "queue_east": 1, "queue_west": 0,
            "avg_wait_time": 10.0,
        }
        alerts = detector.check("ix_0_0", state)
        assert len(alerts) == 0

    def test_high_queue_warning(self, detector):
        state = {
            "queue_north": 5, "queue_south": 3,
            "queue_east": 2, "queue_west": 1,
            "avg_wait_time": 10.0,
        }
        alerts = detector.check("ix_0_0", state)
        assert any(a.alert_type == AlertType.HIGH_QUEUE for a in alerts)
        assert any(a.severity == AlertSeverity.WARNING for a in alerts)

    def test_high_queue_critical(self, detector):
        state = {
            "queue_north": 10, "queue_south": 8,
            "queue_east": 5, "queue_west": 4,
            "avg_wait_time": 10.0,
        }
        alerts = detector.check("ix_0_0", state)
        assert any(a.severity == AlertSeverity.CRITICAL for a in alerts)

    def test_long_wait_warning(self, detector):
        state = {
            "queue_north": 1, "queue_south": 0,
            "queue_east": 0, "queue_west": 0,
            "avg_wait_time": 35.0,
        }
        alerts = detector.check("ix_0_0", state)
        assert any(a.alert_type == AlertType.LONG_WAIT for a in alerts)

    def test_long_wait_critical(self, detector):
        state = {
            "queue_north": 1, "queue_south": 0,
            "queue_east": 0, "queue_west": 0,
            "avg_wait_time": 65.0,
        }
        alerts = detector.check("ix_0_0", state)
        assert any(a.severity == AlertSeverity.CRITICAL for a in alerts)

    def test_emergency_alert(self, detector):
        state = {
            "queue_north": 1, "queue_south": 0,
            "queue_east": 0, "queue_west": 0,
            "emergency": True,
        }
        alerts = detector.check("ix_0_0", state)
        assert any(a.alert_type == AlertType.EMERGENCY for a in alerts)

    def test_sudden_change_alert(self, detector):
        # First check - no history
        state1 = {"queue_north": 1, "queue_south": 0, "queue_east": 0, "queue_west": 0}
        detector.check("ix_0_0", state1)

        # Second check - sudden increase
        state2 = {"queue_north": 10, "queue_south": 0, "queue_east": 0, "queue_west": 0}
        alerts = detector.check("ix_0_0", state2)
        assert any(a.alert_type == AlertType.SUDDEN_CHANGE for a in alerts)

    def test_custom_thresholds(self, custom_detector):
        state = {
            "queue_north": 3, "queue_south": 2,
            "queue_east": 1, "queue_west": 0,
            "avg_wait_time": 10.0,
        }
        alerts = custom_detector.check("ix_0_0", state)
        assert any(a.alert_type == AlertType.HIGH_QUEUE for a in alerts)

    def test_get_recent_alerts(self, detector):
        state = {
            "queue_north": 10, "queue_south": 8,
            "queue_east": 5, "queue_west": 4,
            "avg_wait_time": 65.0,
        }
        detector.check("ix_0_0", state)
        recent = detector.get_recent_alerts(limit=5)
        assert len(recent) > 0

    def test_get_recent_alerts_filtered(self, detector):
        state = {
            "queue_north": 10, "queue_south": 8,
            "queue_east": 5, "queue_west": 4,
            "avg_wait_time": 65.0,
        }
        detector.check("ix_0_0", state)
        warnings = detector.get_recent_alerts(severity=AlertSeverity.WARNING)
        criticals = detector.get_recent_alerts(severity=AlertSeverity.CRITICAL)
        # Should have both
        assert len(warnings) + len(criticals) > 0

    def test_clear_alerts(self, detector):
        state = {
            "queue_north": 10, "queue_south": 8,
            "queue_east": 5, "queue_west": 4,
        }
        detector.check("ix_0_0", state)
        assert len(detector.get_recent_alerts(limit=100)) > 0
        detector.clear_alerts()
        assert len(detector.get_recent_alerts(limit=100)) == 0

    def test_get_alert_count(self, detector):
        state = {
            "queue_north": 10, "queue_south": 8,
            "queue_east": 5, "queue_west": 4,
            "avg_wait_time": 65.0,
        }
        detector.check("ix_0_0", state)
        counts = detector.get_alert_count()
        assert "warning" in counts
        assert "critical" in counts
        assert counts["warning"] + counts["critical"] > 0


class TestTrafficAlert:
    """Test TrafficAlert dataclass."""

    def test_to_dict(self):
        alert = TrafficAlert(
            alert_type=AlertType.HIGH_QUEUE,
            severity=AlertSeverity.WARNING,
            intersection_id="ix_0_0",
            message="High queue",
            value=15.0,
            threshold=10.0,
        )
        d = alert.to_dict()
        assert d["type"] == "high_queue"
        assert d["severity"] == "warning"
        assert d["intersection_id"] == "ix_0_0"
        assert "timestamp" in d
