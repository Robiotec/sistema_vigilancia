from rest_framework.routers import DefaultRouter

from apps.devices.views import CameraViewSet, DroneViewSet, RBoxViewSet, VehicleViewSet

router = DefaultRouter()
router.register("rboxes", RBoxViewSet, basename="rbox")
router.register("cameras", CameraViewSet, basename="camera")
router.register("vehicles", VehicleViewSet, basename="vehicle")
router.register("drones", DroneViewSet, basename="drone")

urlpatterns = router.urls
