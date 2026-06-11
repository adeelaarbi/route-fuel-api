from __future__ import annotations

from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Point as GEOSPoint
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class FuelStation(models.Model):
    opis_truckstop_id = models.PositiveIntegerField(db_index=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=120, db_index=True)
    state = models.CharField(max_length=10, db_index=True)
    rack_id = models.PositiveIntegerField(db_index=True)
    retail_price = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        validators=[MinValueValidator(0)],
        db_index=True,
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
        db_index=True,
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
        db_index=True,
    )
    # PostGIS field used for spatial indexing and advanced geospatial querying.
    # GEOS/GeoDjango expects Point(x=longitude, y=latitude), SRID 4326.
    location = gis_models.PointField(
        geography=True,
        srid=4326,
        null=True,
        blank=True,
        spatial_index=True,
    )
    source_file = models.CharField(max_length=255, blank=True)
    geocoded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["opis_truckstop_id", "name", "address", "city", "state", "rack_id"],
                name="uniq_station_import_identity",
            )
        ]
        indexes = [
            models.Index(fields=["state", "city"], name="fuel_station_state_city_idx"),
            models.Index(fields=["latitude", "longitude"], name="fuel_station_lat_lng_idx"),
            models.Index(fields=["retail_price"], name="fuel_station_price_idx"),
        ]
        ordering = ["retail_price", "name"]

    def __str__(self) -> str:
        return f"{self.name} - {self.city}, {self.state} (${self.retail_price})"

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None and self.location is not None

    @property
    def geocode_query(self) -> str:
        return f"{self.name}, {self.address}, {self.city}, {self.state}, USA"

    def set_coordinates(self, latitude: float, longitude: float) -> None:
        self.latitude = latitude
        self.longitude = longitude
        self.location = GEOSPoint(float(longitude), float(latitude), srid=4326)

    def mark_geocoded(self, latitude: float, longitude: float) -> None:
        self.set_coordinates(latitude=latitude, longitude=longitude)
        self.geocoded_at = timezone.now()

    def save(self, *args, **kwargs) -> None:
        if self.latitude is not None and self.longitude is not None and self.location is None:
            self.location = GEOSPoint(float(self.longitude), float(self.latitude), srid=4326)
        super().save(*args, **kwargs)


class GeocodeCache(models.Model):
    query = models.CharField(max_length=500, unique=True)
    normalized_query = models.CharField(max_length=500, db_index=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    location = gis_models.PointField(
        geography=True,
        srid=4326,
        null=True,
        blank=True,
        spatial_index=True,
    )
    provider = models.CharField(max_length=50, default="nominatim")
    raw_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["query"]

    def __str__(self) -> str:
        return self.query

    def save(self, *args, **kwargs) -> None:
        if self.location is None:
            self.location = GEOSPoint(float(self.longitude), float(self.latitude), srid=4326)
        super().save(*args, **kwargs)


class TripPlanLog(models.Model):
    start_location = models.CharField(max_length=255)
    finish_location = models.CharField(max_length=255)
    request_payload = models.JSONField(default=dict)
    response_payload = models.JSONField(default=dict)
    routing_calls = models.PositiveSmallIntegerField(default=0)
    geocoding_calls = models.PositiveSmallIntegerField(default=0)
    cache_hit = models.BooleanField(default=False)
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["created_at"], name="trip_plan_created_idx")]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.start_location} -> {self.finish_location}"
