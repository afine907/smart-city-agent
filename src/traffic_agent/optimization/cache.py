"""
Decision Cache — LRU + TTL cache for LLM decisions.

Avoids redundant LLM calls when traffic state hasn't changed significantly.
"""

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from traffic_agent.llm.parser import TrafficDecision
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
    
    Key: coarse-grained state hash (queue bins + current phase)
    Value: TrafficDecision + timestamp
    
    Usage:
        cache = DecisionCache(max_size=1000, ttl_seconds=60)
        
        decision = cache.get(state)
        if decision is None:
            decision = call_llm(state)
            cache.set(state, decision)
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: float = 60.0):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple] = OrderedDict()
        self._stats = CacheStats()
    
    def _state_key(self, state: IntersectionState) -> str:
        """Generate cache key from state (coarse-grained bins)."""
        # Round queue lengths to bins of 3 to increase cache hits
        return (
            f"{state.queue_north // 3}_{state.queue_south // 3}_"
            f"{state.queue_east // 3}_{state.queue_west // 3}_"
            f"{state.current_phase}"
        )
    
    def get(self, state: IntersectionState) -> Optional[TrafficDecision]:
        """Get cached decision if available and not expired."""
        key = self._state_key(state)
        
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
    
    def set(self, state: IntersectionState, decision: TrafficDecision) -> None:
        """Cache a decision."""
        key = self._state_key(state)
        
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
