from django.urls import path

from apps.alerts.views import (
    NotificationEmailRecipientsView,
    NotificationSettingsView,
    NotificationTelegramChatIdsView,
    NotificationTestEmailView,
    NotificationTestTelegramView,
)

urlpatterns = [
    path("notification-settings/", NotificationSettingsView.as_view(), name="notification-settings"),
    path("notification-email-recipients/", NotificationEmailRecipientsView.as_view(), name="notification-email-recipients"),
    path("notification-telegram-chat-ids/", NotificationTelegramChatIdsView.as_view(), name="notification-telegram-chat-ids"),
    path("notification-settings/test-email/", NotificationTestEmailView.as_view(), name="notification-test-email"),
    path("notification-settings/test-telegram/", NotificationTestTelegramView.as_view(), name="notification-test-telegram"),
]
