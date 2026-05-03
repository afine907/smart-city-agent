"""
Route planning for OSM traffic simulation.

Provides Dijkstra shortest-path routing between intersections.
"""

import heapq
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(order=True)
class _PriorityEntry:
    """Priority queue entry for Dijkstra."""
    priority: float
    node: str = field(compare=False)


class RoutePlanner:
    """
    Dijkstra-based route planner for road networks.
    
    Pre-computes shortest paths from every intersection to every other
    intersection. Caches results and supports incremental updates.
    """
    
    def __init__(self):
        self._adjacency: Dict[str, List[tuple]] = {}  # node -> [(neighbor, weight)]
        self._dist_cache: Dict[str, Dict[str, float]] = {}
        self._path_cache: Dict[str, Dict[str, List[str]]] = {}
    
    def build_graph(self, segments: dict) -> None:
        """
        Build adjacency list from road segments.
        
        Args:
            segments: Dict of road_id -> OSMSegment (or similar with from_id, to_id, length)
        """
        self._adjacency = {}
        self._dist_cache = {}
        self._path_cache = {}
        
        for seg in segments.values():
            # Forward edge (one-way or bidirectional)
            if seg.from_id not in self._adjacency:
                self._adjacency[seg.from_id] = []
            self._adjacency[seg.from_id].append((seg.to_id, seg.length, seg.road_id))
            
            # Bidirectional roads get reverse edge too
            if not seg.oneway:
                if seg.to_id not in self._adjacency:
                    self._adjacency[seg.to_id] = []
                self._adjacency[seg.to_id].append((seg.from_id, seg.length, seg.road_id))
    
    def shortest_path(self, start: str, end: str) -> Optional[List[str]]:
        """
        Find shortest path from start to end intersection.
        
        Returns:
            List of intersection IDs forming the path, or None if unreachable.
        """
        if start == end:
            return [start]
        
        # Check cache
        if start in self._path_cache and end in self._path_cache[start]:
            return self._path_cache[start][end]
        
        # Dijkstra's algorithm
        dist = {start: 0.0}
        prev: Dict[str, Optional[str]] = {start: None}
        visited = set()
        
        pq = [_PriorityEntry(0.0, start)]
        
        while pq:
            entry = heapq.heappop(pq)
            d, u = entry.priority, entry.node
            
            if u in visited:
                continue
            visited.add(u)
            
            if u == end:
                break
            
            for v, weight, edge_id in self._adjacency.get(u, []):
                if v in visited:
                    continue
                new_dist = d + weight
                if new_dist < dist.get(v, float("inf")):
                    dist[v] = new_dist
                    prev[v] = u
                    heapq.heappush(pq, _PriorityEntry(new_dist, v))
        
        if end not in prev:
            return None  # Unreachable
        
        # Reconstruct path
        path = []
        node = end
        while node is not None:
            path.append(node)
            node = prev[node]
        path.reverse()
        
        # Cache result
        if start not in self._path_cache:
            self._path_cache[start] = {}
        self._path_cache[start][end] = path
        
        return path
    
    def next_hop(self, current: str, destination: str) -> Optional[str]:
        """
        Get the next intersection to move to toward destination.
        
        Returns:
            Next intersection ID, or None if at destination or unreachable.
        """
        path = self.shortest_path(current, destination)
        if path is None or len(path) < 2:
            return None
        return path[1]
    
    def get_edge_id(self, from_id: str, to_id: str) -> Optional[str]:
        """Get the road segment ID connecting two adjacent intersections."""
        for v, _, edge_id in self._adjacency.get(from_id, []):
            if v == to_id:
                return edge_id
        return None
    
    def get_distance(self, start: str, end: str) -> Optional[float]:
        """Get shortest distance between two intersections."""
        if start in self._dist_cache and end in self._dist_cache[start]:
            return self._dist_cache[start][end]
        
        path = self.shortest_path(start, end)
        if path is None:
            return None
        
        total = 0.0
        for i in range(len(path) - 1):
            for v, w, _ in self._adjacency.get(path[i], []):
                if v == path[i + 1]:
                    total += w
                    break
        
        # Cache
        if start not in self._dist_cache:
            self._dist_cache[start] = {}
        self._dist_cache[start][end] = total
        
        return total
    
    def clear_cache(self) -> None:
        """Clear path and distance caches."""
        self._dist_cache.clear()
        self._path_cache.clear()
