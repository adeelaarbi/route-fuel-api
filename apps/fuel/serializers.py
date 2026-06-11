from __future__ import annotations

from rest_framework import serializers


class TripPlanRequestSerializer(serializers.Serializer):
    start_location = serializers.CharField(max_length=255)
    finish_location = serializers.CharField(max_length=255)
    vehicle_range_miles = serializers.FloatField(default=500, min_value=100, max_value=1000)
    miles_per_gallon = serializers.FloatField(default=10, min_value=1, max_value=100)
    route_corridor_miles = serializers.FloatField(default=15, min_value=1, max_value=100)

    def validate(self, attrs):
        start = attrs["start_location"].strip()
        finish = attrs["finish_location"].strip()
        if start.lower() == finish.lower():
            raise serializers.ValidationError("start_location and finish_location must be different.")
        attrs["start_location"] = start
        attrs["finish_location"] = finish
        return attrs
