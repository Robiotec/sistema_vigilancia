from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.profile import ProfileError, ProfileService
from apps.accounts.roles import LegacyRoleService


@method_decorator(ensure_csrf_cookie, name="dispatch")
class LoginView(TemplateView):
    template_name = "accounts/login.html"


class LoginAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        username = str(request.data.get("username") or request.data.get("identity") or "").strip()
        password = str(request.data.get("password") or "")
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response(
                {"ok": False, "detail": "Usuario o clave incorrectos"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        login(request, user)
        roles = LegacyRoleService().role_names_for_user(user)
        role_service = LegacyRoleService()
        return Response(
            {
                "ok": True,
                "user": {
                    "username": user.username,
                    "name": user.get_full_name() or user.first_name or user.username,
                    "roles": roles,
                    "permissions": role_service.permissions_for_user(user),
                },
                "redirect": role_service.default_path_for_user(user),
            }
        )


class LogoutAPIView(APIView):
    def post(self, request):
        logout(request)
        return Response({"ok": True})


class SessionAPIView(APIView):
    def get(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"authenticated": False}, status=status.HTTP_401_UNAUTHORIZED)
        role_service = LegacyRoleService()
        return Response(
            {
                "authenticated": True,
                "user": {
                    "username": user.username,
                    "name": user.get_full_name() or user.first_name or user.username,
                    "roles": role_service.role_names_for_user(user),
                    "permissions": role_service.permissions_for_user(user),
                    "redirect": role_service.default_path_for_user(user),
                },
            }
        )


class ProfileAPIView(APIView):
    def get(self, request):
        try:
            return Response(ProfileService().load(request.user))
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)

    def put(self, request):
        try:
            return Response(ProfileService().update(request.user, request.data if isinstance(request.data, dict) else {}))
        except ProfileError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)
