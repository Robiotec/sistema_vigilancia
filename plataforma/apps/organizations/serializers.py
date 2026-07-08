from rest_framework import serializers

from apps.organizations.models import Area, Company


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "ruc", "address", "active"]


class AreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Area
        fields = ["id", "company_id", "name", "active"]
