from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.fuel.models import FuelStation, GeocodeCache
from apps.fuel.services.routing import OpenRouteServiceGeocoder, RoutingProviderError, normalize_query


class Command(BaseCommand):
    help = "Geocode fuel stations with OpenRouteService and store coordinates for fast route optimization."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--sleep-seconds", type=float, default=0.25)

    def handle(self, *args, **options):
        limit = options["limit"]
        sleep_seconds = options["sleep_seconds"]
        geocoder = OpenRouteServiceGeocoder()
        geocoded = 0
        cache_hits = 0
        failed = 0

        queryset = FuelStation.objects.filter(latitude__isnull=True, longitude__isnull=True).order_by("id")[:limit]

        for station in queryset:
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
                cache_hits += 1
                continue

            try:
                result = geocoder.geocode(query)
                station.mark_geocoded(latitude=result.point.latitude, longitude=result.point.longitude)
                station.geocoded_at = timezone.now()
                station.save(update_fields=["latitude", "longitude", "location", "geocoded_at", "updated_at"])
                geocoded += 1
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
            except RoutingProviderError as exc:
                failed += 1
                self.stderr.write(f"No geocode result for station={station.id} query={query}: {exc}")
            except Exception as exc:  # noqa: BLE001 - management command should continue processing.
                failed += 1
                self.stderr.write(f"Failed station={station.id}: {exc}")

        self.stdout.write(
            self.style.SUCCESS(
                f"OpenRouteService geocoding completed. geocoded={geocoded}, cache_hits={cache_hits}, failed={failed}"
            )
        )
