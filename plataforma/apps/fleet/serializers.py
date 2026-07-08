from rest_framework import serializers

from apps.fleet.models import VehicleTelemetry


class VehicleTelemetrySerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleTelemetry
        fields = [
            "id",
            "vehicle_id",
            "latitude",
            "longitude",
            "speed",
            "heading",
            "payload",
            "received_at",
        ]
