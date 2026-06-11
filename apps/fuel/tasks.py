from __future__ import annotations

import time
from typing import Any

import requests
from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.fuel.models import FuelStation, GeocodeCache
from apps.fuel.services.routing import OpenRouteServiceGeocoder, RoutingProviderError, normalize_query


@shared_task(bind=True, autoretry_for=(requests.RequestException,), retry_backoff=True, retry_jitter=True, max_retries=3)
def geocode_station_task(self, station_id: int, sleep_seconds: float = 0.25) -> dict[str, Any]:
    """Geocode a single fuel station through OpenRouteService and persist coordinates."""
    station = FuelStation.objects.get(id=station_id)
    if station.has_coordinates:
        return {"station_id": station.id, "status": "already_geocoded"}

    query = station.geocode_query
    normalized = normalize_query(query)
    cached = GeocodeCache.objects.filter(
        normalized_query=normalized,
        provider=OpenRouteServiceGeocoder.provider_name,
    ).first()
    if cached:
        station.mark_geocoded(latitude=float(cached.latitude), longitude=float(cached.longitude))
        station.geocoded_at = timezone.now()
        station.save(update_fields=["latitude", "longitude", "location", "geocoded_at", "updated_at"])
        return {"station_id": station.id, "status": "cache_hit"}

    geocoder = OpenRouteServiceGeocoder()
    result = geocoder.geocode(query)

    with transaction.atomic():
        station.mark_geocoded(latitude=result.point.latitude, longitude=result.point.longitude)
        station.geocoded_at = timezone.now()
        station.save(update_fields=["latitude", "longitude", "location", "geocoded_at", "updated_at"])

    if sleep_seconds > 0:
        time.sleep(sleep_seconds)

    return {"station_id": station.id, "status": "geocoded"}


@shared_task(bind=True)
def geocode_all_stations_task(
    self,
    batch_size: int = 500,
    sleep_seconds: float = 0.25,
) -> dict[str, Any]:
    """Geocode one batch of ungeocoded stations with OpenRouteService.

    Keep batch sizes conservative on the free plan. Run multiple batches until
    ``remaining`` reaches zero.
    """
    station_ids = list(
        FuelStation.objects.filter(location__isnull=True)
        .order_by("id")
        .values_list("id", flat=True)[:batch_size]
    )

    results = {"queued": len(station_ids), "geocoded": 0, "cache_hit": 0, "not_found": 0, "failed": 0}
    for station_id in station_ids:
        try:
            result = geocode_station_task(station_id=station_id, sleep_seconds=sleep_seconds)
            status = result.get("status", "failed")
            if status in results:
                results[status] += 1
        except RoutingProviderError:
            results["not_found"] += 1
        except Exception:  # noqa: BLE001 - Celery batch should continue with other stations.
            results["failed"] += 1

    remaining = FuelStation.objects.filter(location__isnull=True).count()
    results["remaining"] = remaining
    return results
