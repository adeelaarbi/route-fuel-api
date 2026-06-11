# Generated for assignment package.

from __future__ import annotations

import django.contrib.gis.db.models.fields
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL("CREATE EXTENSION IF NOT EXISTS postgis;", reverse_sql=migrations.RunSQL.noop),
        migrations.CreateModel(
            name="FuelStation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("opis_truckstop_id", models.PositiveIntegerField(db_index=True)),
                ("name", models.CharField(max_length=255)),
                ("address", models.CharField(max_length=255)),
                ("city", models.CharField(db_index=True, max_length=120)),
                ("state", models.CharField(db_index=True, max_length=10)),
                ("rack_id", models.PositiveIntegerField(db_index=True)),
                (
                    "retail_price",
                    models.DecimalField(
                        db_index=True,
                        decimal_places=4,
                        max_digits=8,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    "latitude",
                    models.DecimalField(
                        blank=True,
                        db_index=True,
                        decimal_places=6,
                        max_digits=9,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(-90),
                            django.core.validators.MaxValueValidator(90),
                        ],
                    ),
                ),
                (
                    "longitude",
                    models.DecimalField(
                        blank=True,
                        db_index=True,
                        decimal_places=6,
                        max_digits=9,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(-180),
                            django.core.validators.MaxValueValidator(180),
                        ],
                    ),
                ),
                (
                    "location",
                    django.contrib.gis.db.models.fields.PointField(
                        blank=True, geography=True, null=True, spatial_index=True, srid=4326
                    ),
                ),
                ("source_file", models.CharField(blank=True, max_length=255)),
                ("geocoded_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["retail_price", "name"]},
        ),
        migrations.CreateModel(
            name="GeocodeCache",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("query", models.CharField(max_length=500, unique=True)),
                ("normalized_query", models.CharField(db_index=True, max_length=500)),
                ("latitude", models.DecimalField(decimal_places=6, max_digits=9)),
                ("longitude", models.DecimalField(decimal_places=6, max_digits=9)),
                (
                    "location",
                    django.contrib.gis.db.models.fields.PointField(
                        blank=True, geography=True, null=True, spatial_index=True, srid=4326
                    ),
                ),
                ("provider", models.CharField(default="nominatim", max_length=50)),
                ("raw_response", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["query"]},
        ),
        migrations.CreateModel(
            name="TripPlanLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_location", models.CharField(max_length=255)),
                ("finish_location", models.CharField(max_length=255)),
                ("request_payload", models.JSONField(default=dict)),
                ("response_payload", models.JSONField(default=dict)),
                ("routing_calls", models.PositiveSmallIntegerField(default=0)),
                ("geocoding_calls", models.PositiveSmallIntegerField(default=0)),
                ("cache_hit", models.BooleanField(default=False)),
                ("duration_ms", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="fuelstation",
            constraint=models.UniqueConstraint(
                fields=("opis_truckstop_id", "name", "address", "city", "state", "rack_id"),
                name="uniq_station_import_identity",
            ),
        ),
        migrations.AddIndex(
            model_name="fuelstation",
            index=models.Index(fields=["state", "city"], name="fuel_station_state_city_idx"),
        ),
        migrations.AddIndex(
            model_name="fuelstation",
            index=models.Index(fields=["latitude", "longitude"], name="fuel_station_lat_lng_idx"),
        ),
        migrations.AddIndex(
            model_name="fuelstation",
            index=models.Index(fields=["retail_price"], name="fuel_station_price_idx"),
        ),
        migrations.AddIndex(
            model_name="tripplanlog",
            index=models.Index(fields=["created_at"], name="trip_plan_created_idx"),
        ),
    ]
