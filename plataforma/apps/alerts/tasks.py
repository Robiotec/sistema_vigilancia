from config.celery import app


@app.task(name="apps.alerts.tasks.dispatch_pending_alerts")
def dispatch_pending_alerts() -> dict[str, object]:
    return {"ok": True, "sent": 0}
