from config.celery import app
from apps.streaming.services import MediaMTXClient


@app.task(name="apps.streaming.tasks.sync_stream_status")
def sync_stream_status() -> dict[str, object]:
    result = MediaMTXClient().list_paths()
    if not result.ok:
        return {"ok": False, "error": result.error}
    return {"ok": True, "paths": len(result.value or [])}
