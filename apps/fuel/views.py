from __future__ import annotations

import time

from django.conf import settings
from django.core.cache import cache
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fuel.models import TripPlanLog
from apps.fuel.serializers import TripPlanRequestSerializer
from apps.fuel.services.cache_keys import build_trip_cache_key
from apps.fuel.services.optimizer import FuelOptimizationError, build_fuel_plan, find_candidate_stations
from apps.fuel.services.routing import (
    OpenRouteServiceGeocoder,
    OpenRouteServiceRoutingClient,
    RoutingProviderError,
    openrouteservice_directions_url,
)


class FuelOptimizeAPIView(APIView):
    serializer_class = TripPlanRequestSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="optimize_fuel_route",
        summary="Find cost-effective fuel stops along a USA route",
        description=(
            "Accepts start and finish locations inside the USA, calls the routing provider once, "
            "finds fuel stations along the route corridor, and returns estimated fuel spend. "
            "Repeated identical searches are served from Redis cache."
        ),
        request=TripPlanRequestSerializer,
        examples=[
            OpenApiExample(
                "New York to Chicago",
                value={
                    "start_location": "New York, NY",
                    "finish_location": "Chicago, IL",
                    "vehicle_range_miles": 500,
                    "miles_per_gallon": 10,
                    "route_corridor_miles": 15,
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        started = time.perf_counter()
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        cache_key = build_trip_cache_key(data)
        cached_payload = cache.get(cache_key)
        if cached_payload is not None:
            duration_ms = int((time.perf_counter() - started) * 1000)
            payload = {**cached_payload, "cache": {"hit": True, "key": cache_key}, "duration_ms": duration_ms}
            TripPlanLog.objects.create(
                start_location=data["start_location"],
                finish_location=data["finish_location"],
                request_payload=request.data,
                response_payload=payload,
                routing_calls=0,
                geocoding_calls=0,
                cache_hit=True,
                duration_ms=duration_ms,
            )
            return Response(payload, status=status.HTTP_200_OK)

        geocoding_calls = 0
        routing_calls = 0

        try:
            geocoder = OpenRouteServiceGeocoder()
            start = geocoder.geocode(data["start_location"])
            finish = geocoder.geocode(data["finish_location"])
            geocoding_calls += int(start.external_call_used) + int(finish.external_call_used)

            router = OpenRouteServiceRoutingClient()
            route = router.route(start.point, finish.point)
            routing_calls += int(route.external_call_used)

            candidates = find_candidate_stations(
                route_points=route.points,
                corridor_miles=data["route_corridor_miles"],
            )
            fuel_plan = build_fuel_plan(
                candidates=candidates,
                route_distance_miles=route.distance_miles,
                vehicle_range_miles=data["vehicle_range_miles"],
                miles_per_gallon=data["miles_per_gallon"],
            )

            payload = {
                "start_location": data["start_location"],
                "finish_location": data["finish_location"],
                "route": {
                    "distance_miles": round(route.distance_miles, 2),
                    "duration_minutes": round(route.duration_minutes, 2),
                    "geometry": route.geometry,
                    "map_url": openrouteservice_directions_url(start.point, finish.point),
                },
                "fuel_plan": fuel_plan,
                "external_api_usage": {
                    "geocoding_calls": geocoding_calls,
                    "routing_calls": routing_calls,
                    "routing_provider": "OpenRouteService",
                    "geocoding_provider": "OpenRouteService",
                },
                "cache": {"hit": False, "key": cache_key},
            }
            cache.set(cache_key, payload, timeout=settings.TRIP_CACHE_TTL_SECONDS)

            duration_ms = int((time.perf_counter() - started) * 1000)
            TripPlanLog.objects.create(
                start_location=data["start_location"],
                finish_location=data["finish_location"],
                request_payload=request.data,
                response_payload=payload,
                routing_calls=routing_calls,
                geocoding_calls=geocoding_calls,
                cache_hit=False,
                duration_ms=duration_ms,
            )
            payload["duration_ms"] = duration_ms
            return Response(payload, status=status.HTTP_200_OK)

        except (RoutingProviderError, FuelOptimizationError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
