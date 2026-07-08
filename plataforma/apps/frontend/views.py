from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from django.views.generic import TemplateView

from apps.accounts.roles import LegacyRoleService


@dataclass(frozen=True)
class SidebarLink:
    permission: str
    href: str
    title: str
    copy: str
    icon_svg: str


SIDEBAR_LINKS = (
    SidebarLink(
        "dashboard",
        "/",
        "Inicio",
        "Centro de mando",
        '<svg viewBox="0 0 24 24" focusable="false"><path d="M4 10.8 12 4l8 6.8v8.4a1.8 1.8 0 0 1-1.8 1.8H5.8A1.8 1.8 0 0 1 4 19.2Z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.8"/><path d="M9 21v-6h6v6" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.8"/></svg>',
    ),
    SidebarLink(
        "map",
        "/mapa/",
        "Mapa",
        "Flota y recorridos",
        '<svg viewBox="0 0 24 24" focusable="false"><path d="M12 21s6-5.1 6-10a6 6 0 0 0-12 0c0 4.9 6 10 6 10Z" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="11" r="2.2" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>',
    ),
    SidebarLink(
        "map",
        "/geocercas/",
        "Geocercas",
        "Zonas y eventos",
        '<svg viewBox="0 0 24 24" focusable="false"><path d="m5 8 6-3 8 4v8l-7 3-7-4Z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.8"/><path d="M11 5v7l8 5M5 8l7 4v8" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.8"/></svg>',
    ),
    SidebarLink(
        "cameras",
        "/camaras/",
        "Camaras",
        "Video en vivo",
        '<svg viewBox="0 0 24 24" focusable="false"><path d="M4 8.5A2.5 2.5 0 0 1 6.5 6h7A2.5 2.5 0 0 1 16 8.5v7a2.5 2.5 0 0 1-2.5 2.5h-7A2.5 2.5 0 0 1 4 15.5Z" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="m16 10 4-2.2v8.4L16 14" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.8"/><circle cx="10" cy="12" r="2.3" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>',
    ),
    SidebarLink(
        "events",
        "/eventos/",
        "Eventos",
        "Camaras e IA",
        '<svg viewBox="0 0 24 24" focusable="false"><path d="M4 6.5h16M4 12h16M4 17.5h10" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.8"/><circle cx="18" cy="17.5" r="2" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>',
    ),
    SidebarLink(
        "vehicles",
        "/gestion-kilometros/",
        "Kilometros",
        "Reporte diario",
        '<svg viewBox="0 0 24 24" focusable="false"><path d="M5 18h14M7 18l3-10h4l3 10M9 12h6" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"/></svg>',
    ),
    SidebarLink(
        "reports",
        "/reportes/",
        "Reportes",
        "Personal y placas",
        '<svg viewBox="0 0 24 24" focusable="false"><path d="M5 19V5M5 19h14M9 16v-5M13 16V8M17 16v-8" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"/></svg>',
    ),
    SidebarLink(
        "notifications",
        "/notificaciones/",
        "Alertas",
        "Correo y Telegram",
        '<svg viewBox="0 0 24 24" focusable="false"><path d="M5 8.2A4.2 4.2 0 0 1 9.2 4h5.6A4.2 4.2 0 0 1 19 8.2v6.4l1.4 2.4H3.6L5 14.6Z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.8"/><path d="M10 20h4" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.8"/></svg>',
    ),
    SidebarLink(
        "admin_users",
        "/administracion/dispositivos/",
        "Dispositivos",
        "Camaras, RBox y flota",
        '<svg viewBox="0 0 24 24" focusable="false"><path d="M5 6.5h14M5 12h14M5 17.5h14" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.8"/><circle cx="9" cy="6.5" r="1.5" fill="currentColor"/><circle cx="15" cy="12" r="1.5" fill="currentColor"/><circle cx="11" cy="17.5" r="1.5" fill="currentColor"/></svg>',
    ),
    SidebarLink(
        "admin_users",
        "/usuarios/",
        "Usuarios",
        "Accesos y empresas",
        '<svg viewBox="0 0 24 24" focusable="false"><path d="M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM16.5 10.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM3.8 20a4.2 4.2 0 0 1 8.4 0M13 19.5a3.5 3.5 0 0 1 7 0" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.8"/></svg>',
    ),
    SidebarLink(
        "admin_users",
        "/servicios/",
        "Servicios",
        "Systemd y endpoints",
        '<svg viewBox="0 0 24 24" focusable="false"><path d="M5 7.5h14M5 12h14M5 16.5h14" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.8"/><circle cx="8" cy="7.5" r="1.3" fill="currentColor"/><circle cx="16" cy="12" r="1.3" fill="currentColor"/><circle cx="10" cy="16.5" r="1.3" fill="currentColor"/></svg>',
    ),
    SidebarLink(
        "profile",
        "/perfil/",
        "Perfil",
        "Cuenta y seguridad",
        '<svg viewBox="0 0 24 24" focusable="false"><circle cx="12" cy="8" r="3.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M5 20a7 7 0 0 1 14 0" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.8"/></svg>',
    ),
)


class RolePageMixin(LoginRequiredMixin):
    required_page_permission = "dashboard"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        role_service = LegacyRoleService()
        if not role_service.can_access_page(request.user, self.required_page_permission):
            target = role_service.default_path_for_user(request.user)
            if target != request.path:
                return HttpResponseRedirect(target)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        role_service = LegacyRoleService()
        permissions = role_service.page_permissions_for_user(self.request.user)
        links = [
            {
                "href": link.href,
                "title": link.title,
                "copy": link.copy,
                "icon_svg": mark_safe(link.icon_svg),
                "is_current": self.request.path == link.href,
            }
            for link in SIDEBAR_LINKS
            if link.permission in permissions
        ]
        context["sidebar_links"] = links
        context["dashboard_links"] = [link for link in links if link["href"] != "/perfil/"]
        context["page_permissions"] = permissions
        return context


class DashboardShellView(RolePageMixin, TemplateView):
    template_name = "dashboard/index.html"


class DeviceAdminView(RolePageMixin, TemplateView):
    required_page_permission = "admin_users"
    template_name = "dashboard/device_admin.html"


class CameraViewerView(RolePageMixin, TemplateView):
    required_page_permission = "cameras"
    template_name = "dashboard/cameras.html"


class FleetMapView(RolePageMixin, TemplateView):
    required_page_permission = "map"
    template_name = "dashboard/map.html"


class GeofenceAdminView(RolePageMixin, TemplateView):
    required_page_permission = "map"
    template_name = "dashboard/geofences.html"


class FleetKilometersView(RolePageMixin, TemplateView):
    required_page_permission = "vehicles"
    template_name = "dashboard/fleet_kilometers.html"


class DetectionReportsView(RolePageMixin, TemplateView):
    required_page_permission = "reports"
    template_name = "dashboard/reports.html"


class ProfileView(RolePageMixin, TemplateView):
    required_page_permission = "profile"
    template_name = "dashboard/profile.html"


class NotificationsView(RolePageMixin, TemplateView):
    required_page_permission = "notifications"
    template_name = "dashboard/notifications.html"


class EventHistoryView(RolePageMixin, TemplateView):
    required_page_permission = "events"
    template_name = "dashboard/events.html"


class UserAccessAdminView(RolePageMixin, TemplateView):
    required_page_permission = "admin_users"
    template_name = "dashboard/users.html"


class OperationsView(RolePageMixin, TemplateView):
    required_page_permission = "admin_users"
    template_name = "dashboard/operations.html"
