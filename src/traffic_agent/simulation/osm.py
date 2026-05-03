"""
OpenStreetMap Road Network Integration.

Downloads real road networks from OSM and converts them to
the simulation's intersection/segment format.
"""

import json
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class OSMIntersection:
    """An intersection extracted from OSM data."""
    id: str
    lat: float
    lon: float
    neighbors: list[str] = field(default_factory=list)
    roads: list[str] = field(default_factory=list)  # road names
    num_lanes: int = 2
    speed_limit: float = 50.0  # km/h


@dataclass
class OSMRoad:
    """A road segment extracted from OSM data."""
    id: str
    from_intersection: str
    to_intersection: str
    length: float  # meters
    speed_limit: float = 50.0  # km/h
    lanes: int = 2
    name: str = ""
    oneway: bool = True


class OSMNetwork:
    """
    Load and manage a road network from OpenStreetMap.

    Supports three loading modes:
    1. Place name: osmnx-based download (requires network)
    2. GeoJSON file: offline loading
    3. Manual construction: for testing
    """

    def __init__(self):
        self.intersections: dict[str, OSMIntersection] = {}
        self.roads: dict[str, OSMRoad] = {}
        self._graph = None

    @classmethod
    def from_place(cls, place_name: str) -> "OSMNetwork":
        """
        Download road network for a place from OSM.

        Args:
            place_name: City/area name, e.g. "Manhattan, New York" or "Wuhan, China"
        """
        try:
            import osmnx as ox
        except ImportError:
            raise ImportError(
                "osmnx is required for OSM integration. "
                "Install with: pip install osmnx"
            )

        net = cls()
        G = ox.graph_from_place(place_name, network_type="drive")
        net._graph = G
        net._convert_graph(G)
        return net

    @classmethod
    def from_bbox(cls, north: float, south: float, east: float, west: float) -> "OSMNetwork":
        """
        Download road network for a bounding box from OSM.

        Args:
            north, south, east, west: Bounding box coordinates in degrees
        """
        try:
            import osmnx as ox
        except ImportError:
            raise ImportError(
                "osmnx is required for OSM integration. "
                "Install with: pip install osmnx"
            )

        net = cls()
        G = ox.graph_from_bbox(north, south, east, west, network_type="drive")
        net._graph = G
        net._convert_graph(G)
        return net

    @classmethod
    def from_geojson(cls, geojson_path: str) -> "OSMNetwork":
        """
        Load road network from a GeoJSON file.

        The GeoJSON should contain LineString features for roads
        and Point features for intersections (optional).
        """
        with open(geojson_path) as f:
            data = json.load(f)

        net = cls()
        net._load_geojson(data)
        return net

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OSMNetwork":
        """
        Load from a dictionary (useful for testing and presets).

        Expected format:
        {
            "intersections": {
                "ix_1": {"lat": 30.5, "lon": 114.3, "neighbors": ["ix_2", "ix_3"], ...},
                ...
            },
            "roads": {
                "road_1": {"from": "ix_1", "to": "ix_2", "length": 200, "speed_limit": 50, ...},
                ...
            }
        }
        """
        net = cls()

        for ix_id, ix_data in data.get("intersections", {}).items():
            net.intersections[ix_id] = OSMIntersection(
                id=ix_id,
                lat=ix_data.get("lat", 0.0),
                lon=ix_data.get("lon", 0.0),
                neighbors=ix_data.get("neighbors", []),
                roads=ix_data.get("roads", []),
                num_lanes=ix_data.get("num_lanes", 2),
                speed_limit=ix_data.get("speed_limit", 50.0),
            )

        for road_id, road_data in data.get("roads", {}).items():
            net.roads[road_id] = OSMRoad(
                id=road_id,
                from_intersection=road_data["from"],
                to_intersection=road_data["to"],
                length=road_data.get("length", 200.0),
                speed_limit=road_data.get("speed_limit", 50.0),
                lanes=road_data.get("lanes", 2),
                name=road_data.get("name", ""),
                oneway=road_data.get("oneway", True),
            )

        return net

    def _convert_graph(self, G) -> None:
        """Convert osmnx MultiDiGraph to our format."""
        try:
            import osmnx as ox
        except ImportError:
            return

        # Extract intersections (nodes)
        for node_id, node_data in G.nodes(data=True):
            ix_id = f"osm_{node_id}"
            lat = node_data.get("y", 0.0)
            lon = node_data.get("x", 0.0)

            # Get road info from connected edges
            roads = []
            for _, _, edge_data in G.out_edges(node_id, data=True):
                road_name = edge_data.get("name", "")
                if road_name and road_name not in roads:
                    roads.append(str(road_name))

            self.intersections[ix_id] = OSMIntersection(
                id=ix_id,
                lat=lat,
                lon=lon,
                roads=roads,
            )

        # Extract roads (edges)
        road_counter = 0
        for u, v, edge_data in G.edges(data=True):
            from_id = f"osm_{u}"
            to_id = f"osm_{v}"

            # Calculate length if not provided
            length = edge_data.get("length", 0.0)
            if length == 0.0:
                # Calculate from coordinates
                u_data = G.nodes[u]
                v_data = G.nodes[v]
                length = self._haversine(
                    u_data["y"], u_data["x"],
                    v_data["y"], v_data["x"]
                )

            speed = edge_data.get("maxspeed", 50.0)
            if isinstance(speed, list):
                speed = speed[0]
            if isinstance(speed, str):
                speed = float(speed.replace(" km/h", "").replace(" mph", ""))
                # Convert mph to km/h if needed
                if "mph" in str(edge_data.get("maxspeed", "")):
                    speed *= 1.60934

            lanes = edge_data.get("lanes", 2)
            if isinstance(lanes, str):
                lanes = int(lanes) if lanes.isdigit() else 2

            road_id = f"road_{road_counter}"
            road_counter += 1

            self.roads[road_id] = OSMRoad(
                id=road_id,
                from_intersection=from_id,
                to_intersection=to_id,
                length=length,
                speed_limit=float(speed) if isinstance(speed, (int, float)) else 50.0,
                lanes=lanes if isinstance(lanes, int) else 2,
                name=str(edge_data.get("name", "")),
                oneway=edge_data.get("oneway", True) in (True, "yes", "1"),
            )

            # Update neighbors
            if from_id in self.intersections:
                self.intersections[from_id].neighbors.append(to_id)

        # Deduplicate neighbors
        for ix in self.intersections.values():
            ix.neighbors = list(set(ix.neighbors))

    def _load_geojson(self, data: dict) -> None:
        """Load from GeoJSON dict."""
        features = data.get("features", [])

        intersections = {}
        roads = {}

        for feature in features:
            geom = feature.get("geometry", {})
            props = feature.get("properties", {})
            ftype = geom.get("type", "")

            if ftype == "Point":
                # Intersection
                coords = geom.get("coordinates", [0, 0])
                ix_id = props.get("id", f"osm_ix_{len(intersections)}")
                intersections[ix_id] = OSMIntersection(
                    id=ix_id,
                    lat=coords[1],
                    lon=coords[0],
                    neighbors=props.get("neighbors", []),
                    roads=props.get("roads", []),
                    num_lanes=props.get("num_lanes", 2),
                    speed_limit=props.get("speed_limit", 50.0),
                )

            elif ftype == "LineString":
                # Road
                coords = geom.get("coordinates", [])
                if len(coords) < 2:
                    continue

                road_id = props.get("id", f"osm_road_{len(roads)}")

                # Calculate length from coordinates
                length = 0.0
                for i in range(len(coords) - 1):
                    length += self._haversine(
                        coords[i][1], coords[i][0],
                        coords[i + 1][1], coords[i + 1][0]
                    )

                roads[road_id] = OSMRoad(
                    id=road_id,
                    from_intersection=props.get("from", ""),
                    to_intersection=props.get("to", ""),
                    length=length,
                    speed_limit=props.get("speed_limit", 50.0),
                    lanes=props.get("lanes", 2),
                    name=props.get("name", ""),
                    oneway=props.get("oneway", True),
                )

        self.intersections = intersections
        self.roads = roads

    def get_intersections(self) -> dict[str, OSMIntersection]:
        """Get all intersections."""
        return self.intersections

    def get_roads(self) -> dict[str, OSMRoad]:
        """Get all roads."""
        return self.roads

    def get_neighbors(self, ix_id: str) -> list[str]:
        """Get neighboring intersection IDs."""
        ix = self.intersections.get(ix_id)
        return ix.neighbors if ix else []

    def get_road_between(self, from_id: str, to_id: str) -> OSMRoad | None:
        """Get the road connecting two intersections."""
        for road in self.roads.values():
            if road.from_intersection == from_id and road.to_intersection == to_id:
                return road
            # Check reverse for bidirectional roads
            if not road.oneway and road.from_intersection == to_id and road.to_intersection == from_id:
                return road
        return None

    def get_stats(self) -> dict[str, Any]:
        """Get network statistics."""
        return {
            "num_intersections": len(self.intersections),
            "num_roads": len(self.roads),
            "avg_road_length": np.mean([r.length for r in self.roads.values()]) if self.roads else 0,
            "total_road_length": sum(r.length for r in self.roads.values()),
        }

    def to_geojson(self) -> dict:
        """Export network as GeoJSON (for visualization)."""
        features = []

        # Intersections as Points
        for ix in self.intersections.values():
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [ix.lon, ix.lat],
                },
                "properties": {
                    "id": ix.id,
                    "roads": ix.roads,
                    "num_lanes": ix.num_lanes,
                    "speed_limit": ix.speed_limit,
                },
            })

        # Roads as LineStrings
        for road in self.roads.values():
            from_ix = self.intersections.get(road.from_intersection)
            to_ix = self.intersections.get(road.to_intersection)

            if from_ix and to_ix:
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [from_ix.lon, from_ix.lat],
                            [to_ix.lon, to_ix.lat],
                        ],
                    },
                    "properties": {
                        "id": road.id,
                        "name": road.name,
                        "length": road.length,
                        "speed_limit": road.speed_limit,
                        "lanes": road.lanes,
                        "oneway": road.oneway,
                    },
                })

        return {
            "type": "FeatureCollection",
            "features": features,
        }

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in meters using Haversine formula."""
        R = 6371000  # Earth's radius in meters

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (math.sin(delta_phi / 2) ** 2 +
             math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c


# ─── Preset Networks ──────────────────────────────────────

# Small test network (for unit tests and quick demos)
SMALL_MANHATTAN = {
    "intersections": {
        "ix_1_1": {"lat": 40.7580, "lon": -73.9855, "neighbors": ["ix_1_2", "ix_2_1"], "roads": ["7th Ave"], "speed_limit": 40.0},
        "ix_1_2": {"lat": 40.7580, "lon": -73.9830, "neighbors": ["ix_1_1", "ix_1_3", "ix_2_2"], "roads": ["Broadway", "7th Ave"], "speed_limit": 40.0},
        "ix_1_3": {"lat": 40.7580, "lon": -73.9805, "neighbors": ["ix_1_2", "ix_2_3"], "roads": ["Broadway"], "speed_limit": 40.0},
        "ix_2_1": {"lat": 40.7560, "lon": -73.9855, "neighbors": ["ix_1_1", "ix_2_2", "ix_3_1"], "roads": ["42nd St"], "speed_limit": 40.0},
        "ix_2_2": {"lat": 40.7560, "lon": -73.9830, "neighbors": ["ix_1_2", "ix_2_1", "ix_2_3", "ix_3_2"], "roads": ["Times Square"], "speed_limit": 30.0},
        "ix_2_3": {"lat": 40.7560, "lon": -73.9805, "neighbors": ["ix_1_3", "ix_2_2", "ix_3_3"], "roads": ["42nd St"], "speed_limit": 40.0},
        "ix_3_1": {"lat": 40.7540, "lon": -73.9855, "neighbors": ["ix_2_1", "ix_3_2"], "roads": ["34th St"], "speed_limit": 40.0},
        "ix_3_2": {"lat": 40.7540, "lon": -73.9830, "neighbors": ["ix_2_2", "ix_3_1", "ix_3_3"], "roads": ["34th St", "7th Ave"], "speed_limit": 40.0},
        "ix_3_3": {"lat": 40.7540, "lon": -73.9805, "neighbors": ["ix_2_3", "ix_3_2"], "roads": ["34th St"], "speed_limit": 40.0},
    },
    "roads": {
        "r_1": {"from": "ix_1_1", "to": "ix_1_2", "length": 220, "speed_limit": 40.0, "lanes": 3, "name": "7th Ave", "oneway": True},
        "r_2": {"from": "ix_1_2", "to": "ix_1_3", "length": 220, "speed_limit": 40.0, "lanes": 3, "name": "Broadway", "oneway": True},
        "r_3": {"from": "ix_2_1", "to": "ix_2_2", "length": 220, "speed_limit": 40.0, "lanes": 2, "name": "42nd St", "oneway": True},
        "r_4": {"from": "ix_2_2", "to": "ix_2_3", "length": 220, "speed_limit": 40.0, "lanes": 2, "name": "42nd St", "oneway": True},
        "r_5": {"from": "ix_3_1", "to": "ix_3_2", "length": 220, "speed_limit": 40.0, "lanes": 2, "name": "34th St", "oneway": True},
        "r_6": {"from": "ix_3_2", "to": "ix_3_3", "length": 220, "speed_limit": 40.0, "lanes": 2, "name": "34th St", "oneway": True},
        "r_7": {"from": "ix_1_1", "to": "ix_2_1", "length": 220, "speed_limit": 40.0, "lanes": 3, "name": "7th Ave", "oneway": True},
        "r_8": {"from": "ix_2_1", "to": "ix_3_1", "length": 220, "speed_limit": 40.0, "lanes": 3, "name": "7th Ave", "oneway": True},
        "r_9": {"from": "ix_1_2", "to": "ix_2_2", "length": 220, "speed_limit": 30.0, "lanes": 4, "name": "Times Square", "oneway": True},
        "r_10": {"from": "ix_2_2", "to": "ix_3_2", "length": 220, "speed_limit": 40.0, "lanes": 3, "name": "7th Ave", "oneway": True},
        "r_11": {"from": "ix_1_3", "to": "ix_2_3", "length": 220, "speed_limit": 40.0, "lanes": 2, "name": "Broadway", "oneway": True},
        "r_12": {"from": "ix_2_3", "to": "ix_3_3", "length": 220, "speed_limit": 40.0, "lanes": 2, "name": "Broadway", "oneway": True},
    },
}

# Wuhan Optics Valley (光谷) — a real Chinese intersection cluster
WUHAN_OPTICS_VALLEY = {
    "intersections": {
        "guanggu_1": {"lat": 30.5065, "lon": 114.3958, "neighbors": ["guanggu_2", "guanggu_4"], "roads": ["珞瑜路"], "speed_limit": 60.0},
        "guanggu_2": {"lat": 30.5065, "lon": 114.3990, "neighbors": ["guanggu_1", "guanggu_3", "guanggu_5"], "roads": ["珞瑜路", "光谷广场"], "speed_limit": 40.0},
        "guanggu_3": {"lat": 30.5065, "lon": 114.4022, "neighbors": ["guanggu_2", "guanggu_6"], "roads": ["珞瑜路"], "speed_limit": 60.0},
        "guanggu_4": {"lat": 30.5040, "lon": 114.3958, "neighbors": ["guanggu_1", "guanggu_5"], "roads": ["民族大道"], "speed_limit": 50.0},
        "guanggu_5": {"lat": 30.5040, "lon": 114.3990, "neighbors": ["guanggu_2", "guanggu_4", "guanggu_6"], "roads": ["光谷广场", "民族大道"], "speed_limit": 40.0},
        "guanggu_6": {"lat": 30.5040, "lon": 114.4022, "neighbors": ["guanggu_3", "guanggu_5"], "roads": ["关山路"], "speed_limit": 50.0},
    },
    "roads": {
        "g_1": {"from": "guanggu_1", "to": "guanggu_2", "length": 280, "speed_limit": 60.0, "lanes": 4, "name": "珞瑜路", "oneway": True},
        "g_2": {"from": "guanggu_2", "to": "guanggu_3", "length": 280, "speed_limit": 60.0, "lanes": 4, "name": "珞瑜路", "oneway": True},
        "g_3": {"from": "guanggu_1", "to": "guanggu_4", "length": 280, "speed_limit": 50.0, "lanes": 3, "name": "民族大道", "oneway": True},
        "g_4": {"from": "guanggu_2", "to": "guanggu_5", "length": 280, "speed_limit": 40.0, "lanes": 3, "name": "光谷广场", "oneway": True},
        "g_5": {"from": "guanggu_3", "to": "guanggu_6", "length": 280, "speed_limit": 50.0, "lanes": 3, "name": "关山路", "oneway": True},
        "g_6": {"from": "guanggu_4", "to": "guanggu_5", "length": 280, "speed_limit": 40.0, "lanes": 3, "name": "光谷广场", "oneway": True},
        "g_7": {"from": "guanggu_5", "to": "guanggu_6", "length": 280, "speed_limit": 50.0, "lanes": 3, "name": "关山路", "oneway": True},
    },
}
