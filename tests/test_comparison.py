"""
Tests for comparison benchmark framework.
"""

import json
import tempfile
from pathlib import Path

import pytest

from traffic_agent.comparison.benchmark import (
    BenchmarkResult,
    ComparisonBenchmark,
    ComparisonReport,
)


class TestBenchmarkResult:
    """Test BenchmarkResult dataclass."""
    
    def test_creation(self):
        result = BenchmarkResult(
            name="test",
            steps=100,
            metrics={"avg_wait_time": 15.0, "throughput": 2.5},
            duration_seconds=1.23,
        )
        assert result.name == "test"
        assert result.steps == 100
        assert result.metrics["avg_wait_time"] == 15.0
    
    def test_to_dict(self):
        result = BenchmarkResult(
            name="test",
            steps=50,
            metrics={"avg_wait_time": 10.0},
            duration_seconds=0.5,
        )
        d = result.to_dict()
        assert d["name"] == "test"
        assert d["steps"] == 50
        assert d["metrics"]["avg_wait_time"] == 10.0
        assert d["duration_seconds"] == 0.5


class TestComparisonReport:
    """Test ComparisonReport formatting."""
    
    def test_improvements_calculated(self):
        fixed = BenchmarkResult("fixed", 100, {"avg_wait_time": 20.0, "throughput": 1.0}, 1.0)
        llm = BenchmarkResult("llm", 100, {"avg_wait_time": 12.0, "throughput": 1.5}, 2.0)
        
        report = ComparisonReport(
            llm_result=llm,
            fixed_result=fixed,
            improvements={"avg_wait_time": 40.0, "throughput": 50.0},
        )
        
        assert report.improvements["avg_wait_time"] == 40.0
        assert report.improvements["throughput"] == 50.0
    
    def test_format_table(self):
        fixed = BenchmarkResult("fixed", 100, {
            "avg_wait_time": 20.0,
            "max_wait_time": 45.0,
            "throughput": 1.0,
            "total_vehicles": 100,
            "total_served": 80,
        }, 1.0)
        
        llm = BenchmarkResult("llm", 100, {
            "avg_wait_time": 12.0,
            "max_wait_time": 30.0,
            "throughput": 1.5,
            "total_vehicles": 70,
            "total_served": 120,
        }, 2.0)
        
        report = ComparisonReport(
            llm_result=llm,
            fixed_result=fixed,
            improvements={
                "avg_wait_time": 40.0,
                "max_wait_time": 33.3,
                "throughput": 50.0,
                "total_vehicles": 30.0,
                "total_served": 50.0,
            },
        )
        
        table = report.format_table()
        assert "📊 AI vs Fixed Timing" in table
        assert "Fixed" in table
        assert "LLM" in table
        assert "Avg Wait" in table
    
    def test_to_dict(self):
        fixed = BenchmarkResult("fixed", 100, {"avg_wait_time": 20.0}, 1.0)
        llm = BenchmarkResult("llm", 100, {"avg_wait_time": 12.0}, 2.0)
        
        report = ComparisonReport(
            llm_result=llm,
            fixed_result=fixed,
            improvements={"avg_wait_time": 40.0},
        )
        
        d = report.to_dict()
        assert "llm" in d
        assert "fixed" in d
        assert "improvements" in d
        assert d["improvements"]["avg_wait_time"] == 40.0


class TestComparisonBenchmark:
    """Test ComparisonBenchmark (unit tests only, no LLM calls)."""
    
    def test_fixed_simulation_runs(self):
        """Test that fixed-timing simulation runs and produces metrics."""
        bench = ComparisonBenchmark(steps=50, seed=42)
        result = bench._run_fixed()
        
        assert result.name == "fixed"
        assert result.steps == 50
        assert "avg_wait_time" in result.metrics
        assert "throughput" in result.metrics
        assert result.duration_seconds >= 0
    
    def test_improvements_calculation(self):
        """Test improvement percentage calculation."""
        bench = ComparisonBenchmark()
        
        fixed = BenchmarkResult("fixed", 100, {
            "avg_wait_time": 20.0,
            "max_wait_time": 50.0,
            "throughput": 1.0,
            "total_vehicles": 100,
            "total_served": 80,
        }, 1.0)
        
        llm = BenchmarkResult("llm", 100, {
            "avg_wait_time": 10.0,
            "max_wait_time": 30.0,
            "throughput": 1.5,
            "total_vehicles": 60,
            "total_served": 120,
        }, 2.0)
        
        improvements = bench._calc_improvements(fixed, llm)
        
        assert improvements["avg_wait_time"] == 50.0  # (20-10)/20 * 100
        assert improvements["max_wait_time"] == 40.0  # (50-30)/50 * 100
        assert improvements["throughput"] == 50.0     # (1.5-1.0)/1.0 * 100
        assert improvements["total_served"] == 50.0   # (120-80)/80 * 100
    
    def test_save_report(self):
        """Test saving report to JSON file."""
        bench = ComparisonBenchmark()
        
        fixed = BenchmarkResult("fixed", 100, {"avg_wait_time": 20.0}, 1.0)
        llm = BenchmarkResult("llm", 100, {"avg_wait_time": 12.0}, 2.0)
        
        report = ComparisonReport(
            llm_result=llm,
            fixed_result=fixed,
            improvements={"avg_wait_time": 40.0},
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/report.json"
            bench.save(report, path)
            
            assert Path(path).exists()
            
            with open(path) as f:
                data = json.load(f)
            
            assert "comparison" in data
            assert "config" in data
            assert data["config"]["steps"] == bench.steps
