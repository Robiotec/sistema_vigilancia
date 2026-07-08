from __future__ import annotations

from django.db import connection
from django.test import TransactionTestCase

from apps.accounts.models import LegacyUser, Role, UserRole
from apps.alerts.models import CameraEventHistory, NotificationEmailRecipient, NotificationTelegramChat
from apps.devices.models import Camera, Drone, RBox, Vehicle
from apps.fleet.models import DroneTelemetry, VehicleRouteSegment, VehicleTelemetry
from apps.geofences.models import Geofence, GeofenceAlert, VehicleGeofenceState
from apps.organizations.models import Area, Company
from apps.reports.models import FleetDailyReportSetting
from apps.streaming.models import StreamConfig, StreamPath


class LegacySchemaTestCase(TransactionTestCase):
    legacy_models = [
        Company,
        Role,
        LegacyUser,
        UserRole,
        Area,
        RBox,
        Vehicle,
        Drone,
        Camera,
        VehicleTelemetry,
        DroneTelemetry,
        VehicleRouteSegment,
        Geofence,
        VehicleGeofenceState,
        GeofenceAlert,
        CameraEventHistory,
        NotificationEmailRecipient,
        NotificationTelegramChat,
        FleetDailyReportSetting,
        StreamPath,
        StreamConfig,
    ]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._create_legacy_schema()

    @classmethod
    def tearDownClass(cls):
        cls._drop_legacy_schema()
        super().tearDownClass()

    @classmethod
    def _pre_setup(cls):
        super()._pre_setup()
        cls._clear_legacy_rows()

    @classmethod
    def _create_legacy_schema(cls):
        existing = set(connection.introspection.table_names())
        with connection.schema_editor() as schema_editor:
            for model in cls.legacy_models:
                if model._meta.db_table not in existing:
                    schema_editor.create_model(model)
                    existing.add(model._meta.db_table)

    @classmethod
    def _drop_legacy_schema(cls):
        existing = set(connection.introspection.table_names())
        with connection.schema_editor() as schema_editor:
            for model in reversed(cls.legacy_models):
                if model._meta.db_table in existing:
                    schema_editor.delete_model(model)
                    existing.remove(model._meta.db_table)

    @classmethod
    def _clear_legacy_rows(cls):
        existing = set(connection.introspection.table_names())
        with connection.cursor() as cursor:
            for model in reversed(cls.legacy_models):
                table_name = model._meta.db_table
                if table_name in existing:
                    cursor.execute(f"DELETE FROM {connection.ops.quote_name(table_name)}")
