from rest_framework.routers import DefaultRouter

from apps.organizations.views import AreaViewSet, CompanyViewSet

router = DefaultRouter()
router.register("companies", CompanyViewSet, basename="company")
router.register("areas", AreaViewSet, basename="area")

urlpatterns = router.urls
