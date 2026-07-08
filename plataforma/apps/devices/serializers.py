from rest_framework import serializers

from apps.devices.models import Camera, Drone, RBox, Vehicle
from apps.devices.services import CameraAdminService, DeviceAdminError, DroneAdminService, RBoxAdminService, VehicleAdminService


class RBoxSerializer(serializers.ModelSerializer):
    class Meta:
        model = RBox
        fields = [
            "id",
            "company_id",
            "name",
            "serial",
            "local_ip",
            "public_ip",
            "server_ip",
            "server_port",
            "location",
            "status",
            "last_connection_at",
            "active",
        ]


class RBoxWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = RBox
        fields = [
            "id",
            "company",
            "area",
            "name",
            "serial",
            "local_ip",
            "public_ip",
            "server_ip",
            "server_port",
            "location",
            "status",
            "active",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        return RBoxAdminService().create(validated_data)

    def update(self, instance, validated_data):
        return RBoxAdminService().update(instance, validated_data)


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = [
            "id",
            "company_id",
            "name",
            "vehicle_type",
            "vehicle_subtype",
            "unique_code",
            "plate",
            "brand",
            "model",
            "year",
            "driver_name",
            "description",
            "active",
            "can_publish",
        ]


class VehicleWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = [
            "id",
            "company",
            "area",
            "owner_user",
            "name",
            "vehicle_type",
            "vehicle_subtype",
            "unique_code",
            "plate",
            "brand",
            "model",
            "year",
            "driver_name",
            "description",
            "active",
            "can_publish",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        try:
            return VehicleAdminService().create(validated_data)
        except DeviceAdminError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

    def update(self, instance, validated_data):
        try:
            return VehicleAdminService().update(instance, validated_data)
        except DeviceAdminError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc


class DroneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Drone
        fields = [
            "id",
            "company_id",
            "name",
            "provider",
            "unique_code",
            "drone_type",
            "model",
            "manufacturer",
            "serial_number",
            "status",
            "active",
            "can_publish",
        ]


class DroneWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Drone
        fields = [
            "id",
            "company",
            "area",
            "owner_user",
            "name",
            "provider",
            "unique_code",
            "drone_type",
            "model",
            "manufacturer",
            "serial_number",
            "status",
            "active",
            "can_publish",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        try:
            return DroneAdminService().create(validated_data)
        except DeviceAdminError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

    def update(self, instance, validated_data):
        try:
            return DroneAdminService().update(instance, validated_data)
        except DeviceAdminError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc


class CameraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Camera
        fields = [
            "id",
            "company_id",
            "rbox_id",
            "vehicle_id",
            "drone_id",
            "name",
            "brand",
            "model",
            "unique_code",
            "camera_type",
            "inference_type",
            "protocol",
            "ip",
            "port",
            "channel",
            "stream",
            "quality",
            "vehicle_position",
            "public_ip_enabled",
            "uses_rbox",
            "notification_telegram",
            "notification_email",
            "status",
            "active",
            "can_publish",
        ]


class CameraWriteSerializer(serializers.ModelSerializer):
    password = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = Camera
        fields = [
            "id",
            "company",
            "area",
            "rbox",
            "vehicle",
            "drone",
            "name",
            "brand",
            "model",
            "rtsp_url",
            "unique_code",
            "camera_type",
            "inference_type",
            "protocol",
            "ip",
            "port",
            "username",
            "password",
            "channel",
            "stream",
            "quality",
            "vehicle_position",
            "public_ip_enabled",
            "uses_rbox",
            "notification_telegram",
            "notification_email",
            "status",
            "active",
            "can_publish",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        raw_password = validated_data.pop("password", "")
        return CameraAdminService().create(validated_data, raw_password=raw_password)

    def update(self, instance, validated_data):
        raw_password = validated_data.pop("password", "")
        return CameraAdminService().update(instance, validated_data, raw_password=raw_password)
