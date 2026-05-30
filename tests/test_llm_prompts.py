"""
Tests for LLM Prompts module.
"""

import pytest

from traffic_agent.llm.prompts import (
    TIMING_ADJUSTMENT_SYSTEM,
    TIMING_ADJUSTMENT_USER,
    format_timing_message,
)


class TestPrompts:
    """Test LLM prompt templates."""

    def test_system_prompt_content(self):
        """Test system prompt contains required elements."""
        assert "±10" in TIMING_ADJUSTMENT_SYSTEM or "-10" in TIMING_ADJUSTMENT_SYSTEM
        assert "JSON" in TIMING_ADJUSTMENT_SYSTEM

    def test_user_prompt_format(self):
        """Test user prompt can be formatted."""
        prompt = TIMING_ADJUSTMENT_USER.format(
            intersection_id="ix_0_0",
            intersection_type="crossroad",
            current_phase="NS_GREEN",
            base_duration=30,
            phase_elapsed=15,
            phase_remaining=15,
            north_vehicles=5,
            north_pedestrians=0,
            north_bicycles=0,
            south_vehicles=3,
            south_pedestrians=0,
            south_bicycles=0,
            east_vehicles=8,
            east_pedestrians=0,
            east_bicycles=0,
            west_vehicles=2,
            west_pedestrians=0,
            west_bicycles=0,
            ns_trend=[3, 4, 5],
            ew_trend=[2, 3, 4],
            recent_adjustments="无",
        )
        assert "ix_0_0" in prompt
        assert "NS_GREEN" in prompt

    def test_format_timing_message(self):
        """Test format_timing_message function."""
        detector_data = {
            "readings": {
                "north": {"vehicles": 5, "pedestrians": 2, "bicycles": 1},
                "south": {"vehicles": 3, "pedestrians": 0, "bicycles": 0},
                "east": {"vehicles": 8, "pedestrians": 1, "bicycles": 0},
                "west": {"vehicles": 2, "pedestrians": 0, "bicycles": 0},
            }
        }

        prompt = format_timing_message(
            intersection_id="center",
            intersection_type="crossroad",
            current_phase="NS_GREEN",
            base_duration=30.0,
            phase_elapsed=15.0,
            phase_remaining=15.0,
            detector_data=detector_data,
            ns_trend=[3, 4, 5],
            ew_trend=[2, 3, 4],
            recent_adjustments=[],
        )

        assert "center" in prompt
        assert "NS_GREEN" in prompt
        assert "5" in prompt  # north vehicles

    def test_format_timing_message_with_adjustments(self):
        """Test format_timing_message with recent adjustments."""
        detector_data = {
            "readings": {
                "north": {"vehicles": 5, "pedestrians": 0, "bicycles": 0},
                "south": {"vehicles": 3, "pedestrians": 0, "bicycles": 0},
                "east": {"vehicles": 8, "pedestrians": 0, "bicycles": 0},
                "west": {"vehicles": 2, "pedestrians": 0, "bicycles": 0},
            }
        }

        recent_adjustments = [
            {"phase": "NS_GREEN", "adjustment": 5, "reason": "heavy traffic"},
            {"phase": "EW_GREEN", "adjustment": -3, "reason": "low traffic"},
        ]

        prompt = format_timing_message(
            intersection_id="center",
            intersection_type="crossroad",
            current_phase="NS_GREEN",
            base_duration=30.0,
            phase_elapsed=15.0,
            phase_remaining=15.0,
            detector_data=detector_data,
            ns_trend=[],
            ew_trend=[],
            recent_adjustments=recent_adjustments,
        )

        assert "heavy traffic" in prompt
        assert "low traffic" in prompt

    def test_prompts_contain_safety_constraints(self):
        """Prompts should mention safety constraints."""
        assert "120" in TIMING_ADJUSTMENT_SYSTEM  # max wait time
        assert "10" in TIMING_ADJUSTMENT_SYSTEM  # max adjustment
