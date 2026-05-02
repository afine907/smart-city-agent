"""
Cost Tracker — Track LLM API usage and estimated costs.

Provides per-intersection and aggregate cost accounting.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class APICallRecord:
    """Record of a single LLM API call."""
    timestamp: float
    intersection_id: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached: bool = False
    latency_ms: float = 0.0
    
    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


# Cost per 1K tokens (approximate, adjust per model)
MODEL_COSTS = {
    "LongCat-Flash-Chat": {"input": 0.0002, "output": 0.0006},
    "LongCat-Flash-Thinking-2601": {"input": 0.0008, "output": 0.0024},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
}


class CostTracker:
    """
    Track LLM API usage costs.
    
    Usage:
        tracker = CostTracker()
        
        tracker.record("ix_0_0", "LongCat-Flash-Chat", prompt_tokens=200, completion_tokens=50)
        tracker.record("ix_0_0", "LongCat-Flash-Chat", prompt_tokens=200, completion_tokens=50, cached=True)
        
        print(tracker.format_report())
    """
    
    def __init__(self):
        self._records: List[APICallRecord] = []
        self._start_time = time.time()
    
    def record(
        self,
        intersection_id: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached: bool = False,
        latency_ms: float = 0.0,
    ) -> None:
        """Record an API call."""
        self._records.append(APICallRecord(
            timestamp=time.time(),
            intersection_id=intersection_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached=cached,
            latency_ms=latency_ms,
        ))
    
    def get_total_cost(self) -> float:
        """Calculate total estimated cost."""
        total = 0.0
        for r in self._records:
            if r.cached:
                continue  # Cached calls are free
            
            costs = MODEL_COSTS.get(r.model, {"input": 0.001, "output": 0.003})
            total += (r.prompt_tokens / 1000) * costs["input"]
            total += (r.completion_tokens / 1000) * costs["output"]
        
        return total
    
    def get_per_intersection(self) -> Dict[str, Dict[str, Any]]:
        """Get per-intersection breakdown."""
        breakdown: Dict[str, Dict[str, Any]] = {}
        
        for r in self._records:
            if r.intersection_id not in breakdown:
                breakdown[r.intersection_id] = {
                    "calls": 0,
                    "cached_calls": 0,
                    "total_tokens": 0,
                    "cost": 0.0,
                }
            
            entry = breakdown[r.intersection_id]
            entry["calls"] += 1
            entry["total_tokens"] += r.total_tokens
            
            if r.cached:
                entry["cached_calls"] += 1
            else:
                costs = MODEL_COSTS.get(r.model, {"input": 0.001, "output": 0.003})
                entry["cost"] += (r.prompt_tokens / 1000) * costs["input"]
                entry["cost"] += (r.completion_tokens / 1000) * costs["output"]
        
        return breakdown
    
    def get_summary(self) -> Dict[str, Any]:
        """Get aggregate summary."""
        total_calls = len(self._records)
        cached_calls = sum(1 for r in self._records if r.cached)
        total_tokens = sum(r.total_tokens for r in self._records)
        total_prompt = sum(r.prompt_tokens for r in self._records)
        total_completion = sum(r.completion_tokens for r in self._records)
        avg_latency = (
            sum(r.latency_ms for r in self._records) / max(1, total_calls)
        )
        
        elapsed = time.time() - self._start_time
        
        return {
            "total_calls": total_calls,
            "cached_calls": cached_calls,
            "uncached_calls": total_calls - cached_calls,
            "cache_rate": cached_calls / max(1, total_calls),
            "total_tokens": total_tokens,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "estimated_cost_usd": self.get_total_cost(),
            "avg_latency_ms": avg_latency,
            "elapsed_seconds": elapsed,
        }
    
    def format_report(self) -> str:
        """Format as readable report."""
        summary = self.get_summary()
        per_ix = self.get_per_intersection()
        
        lines = []
        lines.append("=" * 50)
        lines.append("  💰 LLM Cost Report")
        lines.append("=" * 50)
        lines.append("")
        lines.append(f"  Total Calls:      {summary['total_calls']}")
        lines.append(f"  Cached Calls:     {summary['cached_calls']} ({summary['cache_rate']:.0%})")
        lines.append(f"  API Calls:        {summary['uncached_calls']}")
        lines.append(f"  Total Tokens:     {summary['total_tokens']:,}")
        lines.append(f"  Avg Latency:      {summary['avg_latency_ms']:.0f}ms")
        lines.append(f"  Estimated Cost:   ${summary['estimated_cost_usd']:.4f}")
        lines.append("")
        
        if per_ix:
            lines.append("  Per Intersection:")
            lines.append(f"  {'ID':<12} {'Calls':>6} {'Cached':>7} {'Tokens':>8} {'Cost':>10}")
            lines.append("  " + "-" * 45)
            
            for ix_id, data in sorted(per_ix.items()):
                lines.append(
                    f"  {ix_id:<12} {data['calls']:>6} {data['cached_calls']:>7} "
                    f"{data['total_tokens']:>8,} ${data['cost']:>9.4f}"
                )
        
        lines.append("=" * 50)
        return "\n".join(lines)
    
    def clear(self) -> None:
        """Clear all records."""
        self._records.clear()
        self._start_time = time.time()
