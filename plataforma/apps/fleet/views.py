from datetime import date

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api import CompanyScopedReadOnlyModelViewSet
from apps.core.permissions import ReadOnlyOrStaff
from apps.devices.models import Drone, Vehicle
from apps.fleet.geointel import GeoIntelError, GeoIntelService
from apps.fleet.models import VehicleTelemetry
from apps.fleet.serializers import VehicleTelemetrySerializer
from apps.fleet.services import FleetMapService


class VehicleTelemetryViewSet(CompanyScopedReadOnlyModelViewSet):
    queryset = VehicleTelemetry.objects.select_related("vehicle")
    serializer_class = VehicleTelemetrySerializer
    company_lookup = "vehicle__company_id"
    permission_classes = [ReadOnlyOrStaff]


class FleetLatestLocationsView(APIView):
    permission_classes = [ReadOnlyOrStaff]

    def get(self, request):
        active_only = str(request.query_params.get("active_only", "true")).lower() not in {"0", "false", "no"}
        payload = FleetMapService().latest_locations(
            company_id=request.query_params.get("company_id"),
            active_only=active_only,
        )
        return Response(payload)


class VehicleRouteView(APIView):
    permission_classes = [ReadOnlyOrStaff]

    def get(self, request, vehicle_id: str):
        get_object_or_404(Vehicle, id=vehicle_id)
        target_day = self._target_day(request.query_params.get("date"))
        payload = FleetMapService().route_for_day(vehicle_id=vehicle_id, target_day=target_day)
        return Response(payload)

    @staticmethod
    def _target_day(raw_date: str | None) -> date:
        if not raw_date:
            return timezone.localdate()
        try:
            return date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ValidationError({"date": "Formato invalido. Usa YYYY-MM-DD."}) from exc


class DroneRouteView(APIView):
    permission_classes = [ReadOnlyOrStaff]

    def get(self, request, drone_id: str):
        get_object_or_404(Drone, id=drone_id)
        target_day = VehicleRouteView._target_day(request.query_params.get("date"))
        payload = FleetMapService().route_for_day_drone(drone_id=drone_id, target_day=target_day)
        return Response(payload)


class ArcomConcessionsView(APIView):
    permission_classes = [ReadOnlyOrStaff]

    def get(self, request):
        bbox = request.query_params.get("bbox", "")
        limit = request.query_params.get("limit", 120)
        try:
            return Response(GeoIntelService().arcom_concessions(bbox, limit))
        except GeoIntelError:
            return Response({"type": "FeatureCollection", "features": [], "count": 0, "error": "arcom_unavailable"}, status=503)


class ArcomConcessionLookupView(APIView):
    permission_classes = [ReadOnlyOrStaff]

    def get(self, request):
        try:
            lat = float(request.query_params.get("lat", ""))
            lon = float(request.query_params.get("lon", ""))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"lat": "Latitud invalida.", "lon": "Longitud invalida."}) from exc
        try:
            return Response(GeoIntelService().arcom_concession_lookup(lat, lon))
        except GeoIntelError:
            return Response({"found": False, "concession": None, "error": "arcom_unavailable"}, status=503)


class OsintLayersView(APIView):
    permission_classes = [ReadOnlyOrStaff]

    def get(self, request):
        bbox = request.query_params.get("bbox", "")
        limit = request.query_params.get("limit", 2000)
        layer = request.query_params.get("layer", "")
        try:
            return Response(GeoIntelService().osint_layers(bbox, limit, layer))
        except GeoIntelError:
            return Response({"type": "FeatureCollection", "features": [], "count": 0, "error": "osint_unavailable"}, status=503)
