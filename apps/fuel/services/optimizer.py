from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.contrib.gis.geos import Polygon
from django.db.models import QuerySet

from apps.fuel.models import FuelStation
from apps.fuel.services.geospatial import (
    Point,
    cumulative_distances,
    nearest_route_match,
    route_bounding_box,
)


@dataclass(frozen=True, slots=True)
class CandidateStation:
    station: FuelStation
    route_mile: float
    detour_miles: float

    @property
    def price(self) -> float:
        return float(self.station.retail_price)


class FuelOptimizationError(RuntimeError):
    pass


def find_candidate_stations(route_points: list[Point], corridor_miles: float) -> list[CandidateStation]:
    min_lat, max_lat, min_lng, max_lng = route_bounding_box(route_points, padding_miles=corridor_miles)

    # PostGIS spatial pre-filter: the database uses the station.location GiST index
    # to quickly find stations inside the route corridor bounding box. We still run
    # an in-Python nearest-route check below because the real corridor follows the
    # route polyline, not just the rectangular bounding box.
    bbox = Polygon.from_bbox((min_lng, min_lat, max_lng, max_lat))
    queryset: QuerySet[FuelStation] = FuelStation.objects.filter(
        location__isnull=False,
        location__within=bbox,
    ).only(
        "id",
        "opis_truckstop_id",
        "name",
        "address",
        "city",
        "state",
        "rack_id",
        "retail_price",
        "latitude",
        "longitude",
        "location",
    )

    cumulative = cumulative_distances(route_points)
    candidates: list[CandidateStation] = []

    for station in queryset.iterator(chunk_size=1000):
        point = Point(float(station.latitude), float(station.longitude))
        match = nearest_route_match(point, route_points, cumulative)
        if match.detour_miles <= corridor_miles:
            c_station = CandidateStation(
                    station=station,
                    route_mile=match.route_mile,
                    detour_miles=match.detour_miles,
                )
            candidates.append(c_station)

    candidates.sort(key=lambda item: (item.route_mile, item.price))
    return candidates


def choose_fuel_stops(
    *,
    candidates: list[CandidateStation],
    route_distance_miles: float,
    vehicle_range_miles: float,
) -> list[CandidateStation]:
    if route_distance_miles <= 0:
        return []

    if not candidates:
        raise FuelOptimizationError(
            "No geocoded fuel stations were found near this route. Import and geocode stations first."
        )

    # For short routes, return the lowest-priced station near the route so we can estimate fuel cost.
    if route_distance_miles <= vehicle_range_miles:
        return [min(candidates, key=lambda item: (item.price, item.detour_miles))]

    selected: list[CandidateStation] = []
    current_mile = 0.0

    while route_distance_miles - current_mile > vehicle_range_miles:
        window_start = current_mile + max(50.0, vehicle_range_miles * 0.35)
        window_end = current_mile + vehicle_range_miles
        reachable = [c for c in candidates if window_start <= c.route_mile <= window_end]

        # If the ideal window has no station, relax the lower bound but never exceed max vehicle range.
        if not reachable:
            reachable = [c for c in candidates if current_mile < c.route_mile <= window_end]

        if not reachable:
            raise FuelOptimizationError(
                "Could not build a fuel plan within vehicle range. Try increasing route_corridor_miles "
                "or geocoding more fuel stations."
            )

        best = min(reachable, key=lambda item: (item.price, item.detour_miles, -item.route_mile))
        if selected and best.station.id == selected[-1].station.id:
            raise FuelOptimizationError("Optimizer got stuck on the same station. Check station coordinates.")

        selected.append(best)
        current_mile = best.route_mile

    return selected


def build_fuel_plan(
    *,
    candidates: list[CandidateStation],
    route_distance_miles: float,
    vehicle_range_miles: float,
    miles_per_gallon: float,
) -> dict[str, Any]:
    stops = choose_fuel_stops(
        candidates=candidates,
        route_distance_miles=route_distance_miles,
        vehicle_range_miles=vehicle_range_miles,
    )

    if not stops:
        return {
            "vehicle_range_miles": vehicle_range_miles,
            "miles_per_gallon": miles_per_gallon,
            "estimated_gallons": round(route_distance_miles / miles_per_gallon, 2),
            "total_money_spent": "0.00",
            "currency": "USD",
            "stops": [],
        }

    # Cost assignment: each selected fuel station covers the route leg from that station to the next
    # selected fuel station or to the destination. For short routes the single best station is used to
    # estimate the whole trip fuel cost.
    response_stops: list[dict[str, Any]] = []
    total_cost = Decimal("0.00")

    for index, candidate in enumerate(stops):
        station = candidate.station
        next_mile = stops[index + 1].route_mile if index + 1 < len(stops) else route_distance_miles
        if len(stops) == 1 and route_distance_miles <= vehicle_range_miles:
            leg_miles = route_distance_miles
        else:
            leg_miles = max(0.0, next_mile - candidate.route_mile)

        gallons = Decimal(str(leg_miles / miles_per_gallon))
        cost = gallons * station.retail_price
        total_cost += cost

        response_stops.append(
            {
                "opis_truckstop_id": station.opis_truckstop_id,
                "name": station.name,
                "address": station.address,
                "city": station.city,
                "state": station.state,
                "rack_id": station.rack_id,
                "retail_price": str(station.retail_price),
                "latitude": float(station.latitude),
                "longitude": float(station.longitude),
                "route_mile": round(candidate.route_mile, 2),
                "detour_miles": round(candidate.detour_miles, 2),
                "gallons_to_next_stop": round(float(gallons), 2),
                "estimated_cost_to_next_stop": str(cost.quantize(Decimal("0.01")))
            }
        )

    return {
        "vehicle_range_miles": vehicle_range_miles,
        "miles_per_gallon": miles_per_gallon,
        "estimated_gallons": round(route_distance_miles / miles_per_gallon, 2),
        "total_money_spent": str(total_cost.quantize(Decimal("0.01"))),
        "currency": "USD",
        "stops": response_stops,
    }
