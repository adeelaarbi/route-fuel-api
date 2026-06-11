from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Iterable

EARTH_RADIUS_MILES = 3958.7613
METERS_PER_MILE = 1609.344


@dataclass(frozen=True, slots=True)
class Point:
    latitude: float
    longitude: float

    def as_osrm_coordinate(self) -> str:
        return f"{self.longitude},{self.latitude}"

    def as_geojson_coordinate(self) -> list[float]:
        return [self.longitude, self.latitude]


@dataclass(frozen=True, slots=True)
class RouteMatch:
    route_mile: float
    detour_miles: float
    nearest_point: Point


def haversine_miles(a: Point, b: Point) -> float:
    lat1 = radians(a.latitude)
    lon1 = radians(a.longitude)
    lat2 = radians(b.latitude)
    lon2 = radians(b.longitude)
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    h = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * asin(sqrt(h))


def cumulative_distances(points: list[Point]) -> list[float]:
    if not points:
        return []
    distances = [0.0]
    total = 0.0
    for previous, current in zip(points, points[1:], strict=False):
        total += haversine_miles(previous, current)
        distances.append(total)
    return distances


def route_bounding_box(points: Iterable[Point], padding_miles: float) -> tuple[float, float, float, float]:
    points = list(points)
    if not points:
        raise ValueError("Cannot calculate route bounding box without route points.")

    min_lat = min(p.latitude for p in points)
    max_lat = max(p.latitude for p in points)
    min_lng = min(p.longitude for p in points)
    max_lng = max(p.longitude for p in points)

    # One latitude degree is roughly 69 miles. Longitude varies by latitude; this safe padding is fine
    # for candidate pre-filtering because exact distance is checked later.
    padding_degrees = padding_miles / 69.0
    return (
        min_lat - padding_degrees,
        max_lat + padding_degrees,
        min_lng - padding_degrees,
        max_lng + padding_degrees,
    )


def nearest_route_match(station: Point, route_points: list[Point], cumulative: list[float]) -> RouteMatch:
    best_index = 0
    best_distance = float("inf")

    for index, route_point in enumerate(route_points):
        distance = haversine_miles(station, route_point)
        if distance < best_distance:
            best_distance = distance
            best_index = index

    return RouteMatch(
        route_mile=cumulative[best_index],
        detour_miles=best_distance,
        nearest_point=route_points[best_index],
    )
