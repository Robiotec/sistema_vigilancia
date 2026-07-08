from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.alerts.services import NotificationChannelService
from apps.core.permissions import AlertRolePermission


class NotificationSettingsView(APIView):
    permission_classes = [AlertRolePermission]

    def get(self, request):
        return Response({"ok": True, "settings": NotificationChannelService().load()})

    def put(self, request):
        try:
            settings = NotificationChannelService().save(request.data if isinstance(request.data, dict) else {})
        except ValueError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "settings": settings})


class NotificationEmailRecipientsView(APIView):
    permission_classes = [AlertRolePermission]

    def get(self, request):
        recipients = NotificationChannelService().email_recipients()
        return Response({"ok": True, "recipients": recipients, "total": len(recipients)})

    def post(self, request):
        try:
            recipients = NotificationChannelService().add_email_recipient(str(request.data.get("email", "")))
        except ValueError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "recipients": recipients, "total": len(recipients)})

    def delete(self, request):
        try:
            recipients = NotificationChannelService().remove_email_recipient(str(request.data.get("email", "")))
        except ValueError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "recipients": recipients, "total": len(recipients)})


class NotificationTelegramChatIdsView(APIView):
    permission_classes = [AlertRolePermission]

    def get(self, request):
        chat_ids = NotificationChannelService().telegram_chat_ids()
        return Response({"ok": True, "chat_ids": chat_ids, "total": len(chat_ids)})

    def post(self, request):
        try:
            chat_ids = NotificationChannelService().add_telegram_chat_id(str(request.data.get("chat_id", "")))
        except ValueError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "chat_ids": chat_ids, "total": len(chat_ids)})

    def delete(self, request):
        try:
            chat_ids = NotificationChannelService().remove_telegram_chat_id(str(request.data.get("chat_id", "")))
        except ValueError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "chat_ids": chat_ids, "total": len(chat_ids)})


class NotificationTestEmailView(APIView):
    permission_classes = [AlertRolePermission]

    def post(self, request):
        try:
            return Response(NotificationChannelService().send_test_email())
        except Exception as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


class NotificationTestTelegramView(APIView):
    permission_classes = [AlertRolePermission]

    def post(self, request):
        try:
            return Response(NotificationChannelService().send_test_telegram())
        except Exception as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
