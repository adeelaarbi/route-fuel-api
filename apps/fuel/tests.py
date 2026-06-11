from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework import serializers
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model

from apps.fuel.models import FuelStation
from apps.fuel.serializers import TripPlanRequestSerializer
from apps.fuel.services.cache_keys import build_trip_cache_key
from apps.fuel.services.geospatial import Point, haversine_miles, route_bounding_box
from apps.fuel.services.optimizer import CandidateStation, FuelOptimizationError, build_fuel_plan


class GeospatialTests(SimpleTestCase):
    def test_haversine_distance_is_reasonable(self):
        nyc = Point(latitude=40.7128, longitude=-74.0060)
        chicago = Point(latitude=41.8781, longitude=-87.6298)

        distance = haversine_miles(nyc, chicago)

        self.assertGreater(distance, 700)
        self.assertLess(distance, 730)

    def test_route_bounding_box_applies_padding(self):
        route = [Point(40.0, -75.0), Point(41.0, -74.0)]

        min_lat, max_lat, min_lng, max_lng = route_bounding_box(route, padding_miles=10)

        self.assertLess(min_lat, 40.0)
        self.assertGreater(max_lat, 41.0)
        self.assertLess(min_lng, -75.0)
        self.assertGreater(max_lng, -74.0)


class TripPlanRequestSerializerTests(SimpleTestCase):
    def test_rejects_same_start_and_finish(self):
        serializer = TripPlanRequestSerializer(
            data={"start_location": "Dallas, TX", "finish_location": " dallas, tx "}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)

    def test_rejects_unrealistic_vehicle_range(self):
        serializer = TripPlanRequestSerializer(
            data={
                "start_location": "New York, NY",
                "finish_location": "Chicago, IL",
                "vehicle_range_miles": 50,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("vehicle_range_miles", serializer.errors)

    def test_trims_valid_locations(self):
        serializer = TripPlanRequestSerializer(
            data={"start_location": " New York, NY ", "finish_location": " Chicago, IL "}
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["start_location"], "New York, NY")
        self.assertEqual(serializer.validated_data["finish_location"], "Chicago, IL")


class CacheKeyTests(SimpleTestCase):
    def test_cache_key_is_stable_for_same_semantic_payload(self):
        first = build_trip_cache_key(
            {
                "start_location": " New York, NY ",
                "finish_location": "Chicago, IL",
                "vehicle_range_miles": 500,
                "miles_per_gallon": 10,
                "route_corridor_miles": 15,
            }
        )
        second = build_trip_cache_key(
            {
                "finish_location": "chicago, il",
                "start_location": "new york, ny",
                "miles_per_gallon": 10,
                "vehicle_range_miles": 500,
                "route_corridor_miles": 15,
            }
        )

        self.assertEqual(first, second)


class OptimizerEdgeCaseTests(TestCase):
    def make_station(self, *, price: str, latitude: float = 40.0, longitude: float = -75.0) -> FuelStation:
        station = FuelStation.objects.create(
            opis_truckstop_id=1,
            name=f"Station {price}",
            address="1 Test Road",
            city="Test City",
            state="PA",
            rack_id=100,
            retail_price=Decimal(price),
        )
        station.mark_geocoded(latitude=latitude, longitude=longitude)
        station.save(update_fields=["latitude", "longitude", "location", "geocoded_at", "updated_at"])
        return station

    def test_short_route_uses_lowest_price_candidate_for_estimate(self):
        expensive = CandidateStation(self.make_station(price="4.5000"), route_mile=20, detour_miles=1)
        cheap = CandidateStation(self.make_station(price="3.5000", longitude=-75.1), route_mile=40, detour_miles=3)

        plan = build_fuel_plan(
            candidates=[expensive, cheap],
            route_distance_miles=200,
            vehicle_range_miles=500,
            miles_per_gallon=10,
        )

        self.assertEqual(plan["total_money_spent"], "70.00")
        self.assertEqual(plan["stops"][0]["retail_price"], "3.5000")

    def test_long_route_without_reachable_station_raises_clear_error(self):
        station = CandidateStation(self.make_station(price="3.5000"), route_mile=600, detour_miles=2)

        with self.assertRaises(FuelOptimizationError):
            build_fuel_plan(
                candidates=[station],
                route_distance_miles=1000,
                vehicle_range_miles=500,
                miles_per_gallon=10,
            )


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.TokenAuthentication"],
        "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
        "DEFAULT_THROTTLE_CLASSES": [],
    },
)
class AuthenticationTests(TestCase):
    def test_trip_endpoint_requires_authentication(self):
        client = APIClient()

        response = client.post("/api/v1/trips/optimize-fuel/", {}, format="json")

        self.assertEqual(response.status_code, 401)

    def test_token_authentication_reaches_validation(self):
        user = get_user_model().objects.create_user(username="demo", password="demo")
        token = Token.objects.create(user=user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = client.post("/api/v1/trips/optimize-fuel/", {}, format="json")

        self.assertEqual(response.status_code, 400)
