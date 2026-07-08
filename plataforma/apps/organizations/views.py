from apps.core.api import CompanyScopedReadOnlyModelViewSet
from apps.organizations.models import Area, Company
from apps.organizations.serializers import AreaSerializer, CompanySerializer


class CompanyViewSet(CompanyScopedReadOnlyModelViewSet):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    company_lookup = ""


class AreaViewSet(CompanyScopedReadOnlyModelViewSet):
    queryset = Area.objects.select_related("company")
    serializer_class = AreaSerializer
