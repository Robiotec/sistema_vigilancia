from rest_framework import status
from rest_framework.response import Response

from apps.core.api import CompanyScopedModelViewSet
from apps.core.permissions import ReadOnlyOrStaff
from apps.devices.models import Camera, Drone, RBox, Vehicle
from apps.devices.serializers import (
    CameraSerializer,
    CameraWriteSerializer,
    DroneSerializer,
    DroneWriteSerializer,
    RBoxSerializer,
    RBoxWriteSerializer,
    VehicleSerializer,
    VehicleWriteSerializer,
)
from apps.devices.services import CameraAdminService, DroneAdminService, RBoxAdminService, VehicleAdminService


class RBoxViewSet(CompanyScopedModelViewSet):
    queryset = RBox.objects.select_related("company", "area")
    serializer_class = RBoxSerializer
    permission_classes = [ReadOnlyOrStaff]

    def get_serializer_class(self):
        if self.request.method in {"POST", "PUT", "PATCH"}:
            return RBoxWriteSerializer
        return RBoxSerializer

    def destroy(self, request, *args, **kwargs):
        RBoxAdminService().delete(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


class CameraViewSet(CompanyScopedModelViewSet):
    queryset = Camera.objects.select_related("company", "area", "rbox", "vehicle", "drone")
    serializer_class = CameraSerializer
    permission_classes = [ReadOnlyOrStaff]

    def get_serializer_class(self):
        if self.request.method in {"POST", "PUT", "PATCH"}:
            return CameraWriteSerializer
        return CameraSerializer

    def destroy(self, request, *args, **kwargs):
        CameraAdminService().delete(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


class VehicleViewSet(CompanyScopedModelViewSet):
    queryset = Vehicle.objects.select_related("company", "area", "owner_user")
    serializer_class = VehicleSerializer
    permission_classes = [ReadOnlyOrStaff]

    def get_serializer_class(self):
        if self.request.method in {"POST", "PUT", "PATCH"}:
            return VehicleWriteSerializer
        return VehicleSerializer

    def destroy(self, request, *args, **kwargs):
        VehicleAdminService().delete(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


class DroneViewSet(CompanyScopedModelViewSet):
    queryset = Drone.objects.select_related("company", "area", "owner_user")
    serializer_class = DroneSerializer
    permission_classes = [ReadOnlyOrStaff]

    def get_serializer_class(self):
        if self.request.method in {"POST", "PUT", "PATCH"}:
            return DroneWriteSerializer
        return DroneSerializer

    def destroy(self, request, *args, **kwargs):
        DroneAdminService().delete(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)
