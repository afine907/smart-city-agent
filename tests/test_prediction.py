"""
Tests for Traffic Prediction module.
"""

import pytest

from traffic_agent.simulation.prediction import (
    PredictionResult,
    TrafficPredictor,
)


class TestPredictionResult:
    """Test PredictionResult data class."""

    def test_to_dict(self):
        result = PredictionResult(
            step=1,
            predicted_queue=5.0,
            predicted_wait=10.0,
            confidence=0.8,
            trend="increasing",
        )
        d = result.to_dict()
        assert d["step"] == 1
        assert d["predicted_queue"] == 5.0
        assert d["trend"] == "increasing"


class TestTrafficPredictor:
    """Test TrafficPredictor."""

    def test_initial_state(self):
        predictor = TrafficPredictor()
        assert predictor.get_trend() == "stable"

    def test_predict_with_no_data(self):
        predictor = TrafficPredictor()
        result = predictor.predict(1)
        assert result.confidence == 0.0
        assert result.trend == "stable"

    def test_predict_with_data(self):
        predictor = TrafficPredictor(window_size=5)

        # Add increasing traffic
        for i in range(10):
            predictor.update(queue_length=float(i), wait_time=float(i * 2))

        result = predictor.predict(1)
        assert result.predicted_queue > 0
        assert result.trend == "increasing"

    def test_predict_decreasing(self):
        predictor = TrafficPredictor(window_size=5)

        # Add decreasing traffic
        for i in range(10, 0, -1):
            predictor.update(queue_length=float(i), wait_time=float(i * 2))

        result = predictor.predict(1)
        assert result.trend == "decreasing"

    def test_predict_stable(self):
        predictor = TrafficPredictor(window_size=5)

        # Add stable traffic
        for _ in range(10):
            predictor.update(queue_length=5.0, wait_time=10.0)

        result = predictor.predict(1)
        assert result.trend == "stable"
        assert abs(result.predicted_queue - 5.0) < 1.0

    def test_predict_multiple(self):
        predictor = TrafficPredictor(window_size=5, prediction_horizon=3)

        for i in range(10):
            predictor.update(queue_length=float(i), wait_time=float(i))

        predictions = predictor.predict_multiple()
        assert len(predictions) == 3

        # Confidence should decrease with distance
        for i in range(len(predictions) - 1):
            assert predictions[i].confidence >= predictions[i + 1].confidence

    def test_predict_negative_clamped(self):
        predictor = TrafficPredictor(window_size=5)

        # Add decreasing traffic that would go negative
        for i in range(10, 0, -1):
            predictor.update(queue_length=float(i), wait_time=float(i))

        result = predictor.predict(100)
        assert result.predicted_queue >= 0.0
        assert result.predicted_wait >= 0.0

    def test_reset(self):
        predictor = TrafficPredictor()
        predictor.update(5.0, 10.0)
        predictor.update(6.0, 12.0)

        predictor.reset()
        assert predictor.get_trend() == "stable"

    def test_history_trimming(self):
        predictor = TrafficPredictor(window_size=5)

        # Add more than max_history entries
        for i in range(100):
            predictor.update(queue_length=float(i), wait_time=float(i))

        # History should be trimmed
        assert len(predictor._queue_history) <= 15  # window_size * 3
