import requests

from back.app.services.db_pool import fetch_all, execute


MEDIAMTX_URL = "http://127.0.0.1:9997/v3/paths/list"


def get_live_paths():
    try:
        resp = requests.get(MEDIAMTX_URL, timeout=3)
        resp.raise_for_status()

        data = resp.json()

        return {
            item["name"]
            for item in data.get("items", [])
            if item.get("name")
        }

    except Exception as e:
        print(f"[ERROR] No se pudo consultar MediaMTX local: {e}")
        return set()


def sync_cameras_active():
    live_paths = get_live_paths()

    cameras = fetch_all("""
        SELECT id, name, unique_code, active
        FROM cameras
        WHERE deleted_at IS NULL
    """)

    for cam in cameras:
        cam_id = cam["id"]
        name = cam["name"]
        unique_code = cam["unique_code"]

        if not unique_code:
            continue

        is_live = unique_code in live_paths

        if bool(cam["active"]) != is_live:
            execute("""
                UPDATE cameras
                SET active = %s
                WHERE id = %s
            """, [is_live, cam_id])

            print(f"[SYNC] {name} | {unique_code} | active={is_live}")

    print("[OK] Sincronización finalizada")


if __name__ == "__main__":
    sync_cameras_active()