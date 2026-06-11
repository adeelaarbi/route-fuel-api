from django.contrib import admin

from apps.fuel.models import FuelStation, GeocodeCache, TripPlanLog


@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = (
        "opis_truckstop_id",
        "name",
        "city",
        "state",
        "rack_id",
        "retail_price",
        "latitude",
        "longitude",
    )
    search_fields = ("opis_truckstop_id", "name", "address", "city", "state")
    list_filter = ("state", "rack_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(GeocodeCache)
class GeocodeCacheAdmin(admin.ModelAdmin):
    list_display = ("query", "latitude", "longitude", "provider", "created_at")
    search_fields = ("query", "normalized_query")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TripPlanLog)
class TripPlanLogAdmin(admin.ModelAdmin):
    list_display = ("start_location", "finish_location", "routing_calls", "geocoding_calls", "cache_hit", "duration_ms", "created_at")
    search_fields = ("start_location", "finish_location")
    readonly_fields = ("created_at",)
