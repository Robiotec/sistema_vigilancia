from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import AccountAdminPermission
from apps.operations.services import OperationsMonitorService


class OperationsOverviewView(APIView):
    permission_classes = [AccountAdminPermission]

    def get(self, request):
        return Response(OperationsMonitorService().overview())
