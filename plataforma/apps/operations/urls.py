from django.urls import path

from apps.operations.views import OperationsOverviewView

urlpatterns = [
    path("overview/", OperationsOverviewView.as_view(), name="operations-overview"),
]
