from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import AccountAdminError, UserAccessAdminService
from apps.core.permissions import AccountAdminPermission


class AccessOverviewView(APIView):
    permission_classes = [AccountAdminPermission]

    def get(self, request):
        try:
            return Response(UserAccessAdminService().overview(request.user))
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)


class UserAdminView(APIView):
    permission_classes = [AccountAdminPermission]

    def post(self, request):
        try:
            user = UserAccessAdminService().create_user(request.user, request.data)
        except AccountAdminError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response({"ok": True, "user": user}, status=status.HTTP_201_CREATED)


class UserAdminDetailView(APIView):
    permission_classes = [AccountAdminPermission]

    def put(self, request, user_id):
        try:
            user = UserAccessAdminService().update_user(request.user, str(user_id), request.data)
        except FileNotFoundError:
            return Response({"ok": False, "error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        except AccountAdminError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response({"ok": True, "user": user})

    def delete(self, request, user_id):
        try:
            UserAccessAdminService().delete_user(request.user, str(user_id))
        except FileNotFoundError:
            return Response({"ok": False, "error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        except AccountAdminError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response({"ok": True})


class CompanyAdminView(APIView):
    permission_classes = [AccountAdminPermission]

    def post(self, request):
        try:
            company = UserAccessAdminService().create_company(request.user, request.data)
        except AccountAdminError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response({"ok": True, "company": company}, status=status.HTTP_201_CREATED)


class CompanyAdminDetailView(APIView):
    permission_classes = [AccountAdminPermission]

    def put(self, request, company_id):
        try:
            company = UserAccessAdminService().update_company(request.user, str(company_id), request.data)
        except FileNotFoundError:
            return Response({"ok": False, "error": "Organizacion no encontrada"}, status=status.HTTP_404_NOT_FOUND)
        except AccountAdminError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response({"ok": True, "company": company})

    def delete(self, request, company_id):
        try:
            UserAccessAdminService().delete_company(request.user, str(company_id))
        except FileNotFoundError:
            return Response({"ok": False, "error": "Organizacion no encontrada"}, status=status.HTTP_404_NOT_FOUND)
        except AccountAdminError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response({"ok": True})
