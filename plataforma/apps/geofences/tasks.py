from config.celery import app


@app.task(name="apps.geofences.tasks.process_pending_geofence_alerts")
def process_pending_geofence_alerts() -> dict[str, object]:
    return {"ok": True, "processed": 0}
