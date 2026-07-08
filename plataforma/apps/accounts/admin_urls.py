from django.urls import path

from apps.accounts.admin_views import AccessOverviewView, CompanyAdminDetailView, CompanyAdminView, UserAdminDetailView, UserAdminView

urlpatterns = [
    path("access/", AccessOverviewView.as_view(), name="account-access-overview"),
    path("users/", UserAdminView.as_view(), name="account-users"),
    path("users/<uuid:user_id>/", UserAdminDetailView.as_view(), name="account-user-detail"),
    path("companies/", CompanyAdminView.as_view(), name="account-companies"),
    path("companies/<uuid:company_id>/", CompanyAdminDetailView.as_view(), name="account-company-detail"),
]
