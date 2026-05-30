"""
Tests for CLI entry point — end-to-end command tests.
"""

import json
import subprocess
import sys

import pytest


class TestCLIHelp:
    """Test CLI help and argument parsing."""

    def test_main_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "traffic_agent.cli", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "LLM Traffic Signal Timing Adjustment Controller" in result.stdout

    def test_run_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "traffic_agent.cli", "run", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "--type" in result.stdout
        assert "--scenario" in result.stdout
        assert "--steps" in result.stdout

    def test_benchmark_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "traffic_agent.cli", "benchmark", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "--type" in result.stdout

    def test_scenarios_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "traffic_agent.cli", "scenarios", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0

    def test_serve_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "traffic_agent.cli", "serve", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "--host" in result.stdout
        assert "--port" in result.stdout

    def test_no_command_shows_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "traffic_agent.cli"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 1
        assert "usage:" in result.stderr.lower() or "usage:" in result.stdout.lower()


class TestCLIScenarios:
    """Test scenarios command."""

    def test_list_scenarios(self):
        result = subprocess.run(
            [sys.executable, "-m", "traffic_agent.cli", "scenarios"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "morning_peak" in result.stdout
        assert "evening_peak" in result.stdout
        assert "normal" in result.stdout


class TestCLIRun:
    """Test run command."""

    def test_run_fixed_timing(self):
        result = subprocess.run(
            [sys.executable, "-m", "traffic_agent.cli", "run", "--steps", "10"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "Simulation Report" in result.stdout
        assert "Total steps: 10" in result.stdout

    def test_run_rule_engine(self):
        result = subprocess.run(
            [sys.executable, "-m", "traffic_agent.cli", "run", "--steps", "10", "--rule"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "Rule engine enabled" in result.stdout

    def test_run_with_export(self, tmp_path):
        export_file = str(tmp_path / "test_export.json")
        result = subprocess.run(
            [sys.executable, "-m", "traffic_agent.cli", "run",
             "--steps", "10", "--export", export_file],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert f"Log exported to {export_file}" in result.stdout

        # Verify export file exists and is valid JSON
        with open(export_file) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_run_tjunction(self):
        result = subprocess.run(
            [sys.executable, "-m", "traffic_agent.cli", "run",
             "--type", "tjunction", "--steps", "10"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "Simulation Report" in result.stdout

    def test_run_scenario(self):
        result = subprocess.run(
            [sys.executable, "-m", "traffic_agent.cli", "run",
             "--scenario", "morning_peak", "--steps", "10"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0


class TestCLIBenchmark:
    """Test benchmark command."""

    def test_benchmark_fixed_vs_rule(self, tmp_path):
        output_file = str(tmp_path / "benchmark_output.json")
        result = subprocess.run(
            [sys.executable, "-m", "traffic_agent.cli", "benchmark",
             "--steps", "10", "--output", output_file],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0
