"""
Decision Cache — LRU + TTL cache for LLM decisions.

Avoids redundant LLM calls when traffic state hasn't changed significantly.
"""

from __future__ import annotations


import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional, Union

from traffic_agent.llm.parser import TimingAdjustment, TrafficDecision
from traffic_agent.tools.traffic_tools import IntersectionState


@dataclass
class CacheStats:
    """Cache hit/miss statistics."""
    hits: int = 0
    misses: int = 0
    
    @property
    def total(self) -> int:
        return self.hits + self.misses
    
    @property
    def hit_rate(self) -> float:
        return self.hits / max(1, self.total)


class DecisionCache:
    """
    LRU cache with TTL expiration for traffic decisions.

    Key: string key (e.g., coarse-grained state hash)
    Value: decision object + timestamp

    Usage:
        cache = DecisionCache(max_size=1000, ttl_seconds=60)

        decision = cache.get(state_or_key)
        if decision is None:
            decision = call_llm(state)
            cache.set(state_or_key, decision)
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: float = 60.0):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple] = OrderedDict()
        self._stats = CacheStats()

    def _to_key(self, state_or_key) -> str:
        """Convert state or string to cache key."""
        if isinstance(state_or_key, str):
            return state_or_key
        # Assume IntersectionState
        return (
            f"{state_or_key.queue_north // 3}_{state_or_key.queue_south // 3}_"
            f"{state_or_key.queue_east // 3}_{state_or_key.queue_west // 3}_"
            f"{state_or_key.current_phase}"
        )

    def get(self, state_or_key: Union[str, IntersectionState]) -> Any:
        """Get cached decision if available and not expired.

        Returns:
            Cached decision (TimingAdjustment or TrafficDecision) or None
        """
        key = self._to_key(state_or_key)

        if key in self._cache:
            decision, timestamp = self._cache[key]

            # Check TTL
            if time.time() - timestamp < self.ttl_seconds:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                self._stats.hits += 1
                return decision
            else:
                # Expired
                del self._cache[key]

        self._stats.misses += 1
        return None

    def set(self, state_or_key: Union[str, IntersectionState], decision: Any) -> None:
        """Cache a decision (TimingAdjustment or TrafficDecision)."""
        key = self._to_key(state_or_key)

        # Evict oldest if at capacity
        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)

        self._cache[key] = (decision, time.time())
    
    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._stats = CacheStats()
    
    @property
    def stats(self) -> CacheStats:
        return self._stats
    
    @property
    def size(self) -> int:
        return len(self._cache)
