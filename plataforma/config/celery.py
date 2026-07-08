"""Celery application for Robiotec background work."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("robiotec")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
