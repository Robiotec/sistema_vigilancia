from django.urls import path

from apps.accounts.views import LoginAPIView, LogoutAPIView, ProfileAPIView, SessionAPIView

urlpatterns = [
    path("login/", LoginAPIView.as_view(), name="login"),
    path("logout/", LogoutAPIView.as_view(), name="logout"),
    path("session/", SessionAPIView.as_view(), name="session"),
    path("profile/", ProfileAPIView.as_view(), name="profile"),
]
