from django.contrib import admin

from apps.organizations.models import Area, Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "ruc", "active")
    list_filter = ("active",)
    search_fields = ("name", "ruc")


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "active")
    list_filter = ("active", "company")
    search_fields = ("name", "company__name")
