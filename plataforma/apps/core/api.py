"""Reusable DRF base classes."""

from __future__ import annotations

from rest_framework import viewsets


class CompanyScopedReadOnlyModelViewSet(viewsets.ReadOnlyModelViewSet):
    """Shared read-only endpoint with optional company filtering."""

    company_lookup = "company_id"
    lookup_field = "id"

    def get_queryset(self):
        queryset = super().get_queryset()
        company_id = self.request.query_params.get("company_id")
        if company_id and self.company_lookup:
            queryset = queryset.filter(**{self.company_lookup: company_id})
        return queryset


class CompanyScopedModelViewSet(viewsets.ModelViewSet):
    """Shared CRUD endpoint with optional company filtering."""

    company_lookup = "company_id"
    lookup_field = "id"

    def get_queryset(self):
        queryset = super().get_queryset()
        company_id = self.request.query_params.get("company_id")
        if company_id and self.company_lookup:
            queryset = queryset.filter(**{self.company_lookup: company_id})
        return queryset
