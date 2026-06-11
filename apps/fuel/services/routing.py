from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings

from apps.fuel.models import GeocodeCache
from apps.fuel.services.geospatial import METERS_PER_MILE, Point


@dataclass(frozen=True, slots=True)
class GeocodeResult:
    point: Point
    external_call_used: bool


@dataclass(frozen=True, slots=True)
class RouteResult:
    points: list[Point]
    distance_miles: float
    duration_minutes: float
    geometry: dict[str, Any]
    external_call_used: bool


class RoutingProviderError(RuntimeError):
    pass


def normalize_query(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _ors_headers() -> dict[str, str]:
    if not settings.OPENROUTESERVICE_API_KEY:
        raise RoutingProviderError(
            "OPENROUTESERVICE_API_KEY is required. Create a free OpenRouteService key and set it in .env."
        )
    return {
        "Authorization": settings.OPENROUTESERVICE_API_KEY,
        "Accept": "application/json, application/geo+json",
        "Content-Type": "application/json",
        "User-Agent": settings.GEOCODER_USER_AGENT,
    }


class OpenRouteServiceGeocoder:
    """Geocoder backed by OpenRouteService Pelias geocoding.

    Results are persisted in GeocodeCache so repeated station and trip searches do
    not repeatedly call the external provider.
    """

    provider_name = "openrouteservice"

    def __init__(self) -> None:
        self.base_url = settings.OPENROUTESERVICE_BASE_URL.rstrip("/")
        self.timeout = settings.HTTP_TIMEOUT_SECONDS

    def geocode(self, query: str) -> GeocodeResult:
        normalized = normalize_query(query)
        cached = GeocodeCache.objects.filter(normalized_query=normalized, provider=self.provider_name).first()
        if cached:
            return GeocodeResult(
                point=Point(float(cached.latitude), float(cached.longitude)),
                external_call_used=False,
            )

        response = requests.get(
            f"{self.base_url}/geocode/search",
            params={"text": query, "size": 1, "boundary.country": "USA"},
            headers=_ors_headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        features = payload.get("features") or []
        if not features:
            raise RoutingProviderError(f"Could not geocode location with OpenRouteService: {query}")

        first = features[0]
        longitude, latitude = first["geometry"]["coordinates"][:2]
        point = Point(latitude=float(latitude), longitude=float(longitude))
        GeocodeCache.objects.update_or_create(
            normalized_query=normalized,
            provider=self.provider_name,
            defaults={
                "query": query,
                "latitude": point.latitude,
                "longitude": point.longitude,
                "raw_response": first,
            },
        )
        return GeocodeResult(point=point, external_call_used=True)


class OpenRouteServiceRoutingClient:
    """Directions client backed by OpenRouteService.

    The trip API calls this once per cache miss and uses the returned GeoJSON
    route locally for station matching and fuel-stop optimization.
    """

    provider_name = "openrouteservice"

    def __init__(self) -> None:
        self.base_url = settings.OPENROUTESERVICE_BASE_URL.rstrip("/")
        self.timeout = settings.HTTP_TIMEOUT_SECONDS
        self.profile = settings.OPENROUTESERVICE_PROFILE

    def route(self, start: Point, finish: Point) -> RouteResult:
        response = requests.post(
            f"{self.base_url}/v2/directions/{self.profile}/geojson",
            json={
                "coordinates": [
                    start.as_geojson_coordinate(),
                    finish.as_geojson_coordinate(),
                ],
                "instructions": False,
                "geometry_simplify": False,
                "units": "m",
            },
            headers=_ors_headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()

        features = payload.get("features") or []
        if not features:
            raise RoutingProviderError("OpenRouteService did not return a route for the requested locations.")

        feature = features[0]
        geometry = feature["geometry"]
        summary = feature.get("properties", {}).get("summary", {})
        coordinates = geometry.get("coordinates") or []
        points = [Point(latitude=lat, longitude=lng) for lng, lat in coordinates]
        if len(points) < 2:
            raise RoutingProviderError("OpenRouteService returned an invalid route geometry.")

        return RouteResult(
            points=points,
            distance_miles=float(summary.get("distance", 0.0)) / METERS_PER_MILE,
            duration_minutes=float(summary.get("duration", 0.0)) / 60,
            geometry=geometry,
            external_call_used=True,
        )


def openrouteservice_directions_url(start: Point, finish: Point) -> str:
    return (
        "https://maps.openrouteservice.org/#/directions/"
        f"{start.longitude},{start.latitude}/"
        f"{finish.longitude},{finish.latitude}/driving-car"
    )
