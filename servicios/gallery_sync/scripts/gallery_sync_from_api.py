#!/usr/bin/env python3
"""Sync faces gallery from the central API manifest."""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ALLOWED_FILES = {
    "embeddings.npz",
    "gallery.faiss",
    "idx_to_cedula.json",
    "metadata.json",
    "state.json",
    "version",
}


def log(message: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


load_env(Path(env_first("GALLERY_ENV_FILE", default="/robiotec/gallery/.env")))

API_BASE = env_first(
    "GALLERY_API_BASE",
    "FACES_GALLERY_API_BASE",
    default="https://robio-ai.com/api/faces-gallery",
).rstrip("/")
TOKEN = env_first("GALLERY_SYNC_TOKEN", "FACES_GALLERY_TOKEN", "GALLERY_TOKEN")
LOCAL_PATH = Path(env_first("GALLERY_LOCAL_PATH", "LOCAL_PATH", default="/robiotec/gallery/data"))
STATE_FILE = Path(env_first("GALLERY_SYNC_STATE_FILE", default="/robiotec/gallery/.sync_state.json"))
VERIFY_TLS = env_bool("GALLERY_VERIFY_TLS", True)
INCLUDE_HASHES = env_bool("GALLERY_INCLUDE_HASHES", True)


def ssl_context():
    if VERIFY_TLS:
        return None
    return ssl._create_unverified_context()


def request(url: str) -> bytes:
    if not TOKEN:
        raise RuntimeError("Falta GALLERY_SYNC_TOKEN/FACES_GALLERY_TOKEN")
    req = Request(
        url,
        headers={
            "Accept": "application/json",
            "X-Robiotec-Faces-Token": TOKEN,
        },
    )
    try:
        with urlopen(req, timeout=60, context=ssl_context()) as response:
            return response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"No se pudo conectar a {url}: {exc}") from exc


def fetch_manifest() -> dict[str, Any]:
    url = f"{API_BASE}/manifest?include_hashes={'true' if INCLUDE_HASHES else 'false'}"
    payload = json.loads(request(url).decode("utf-8"))
    if not isinstance(payload, dict) or not payload.get("available"):
        raise RuntimeError("Manifest de galeria no disponible")
    files = payload.get("files")
    if not isinstance(files, list):
        raise RuntimeError("Manifest de galeria invalido")
    return payload


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_matches(path: Path, info: dict[str, Any]) -> bool:
    if not path.is_file():
        return False
    try:
        stat = path.stat()
    except OSError:
        return False
    size = int(info.get("size") or -1)
    if size >= 0 and stat.st_size != size:
        return False
    expected_hash = str(info.get("sha256") or "").strip()
    if expected_hash and sha256(path) != expected_hash:
        return False
    return True


def download_file(info: dict[str, Any]) -> bool:
    name = Path(str(info.get("name") or "")).name
    if name not in ALLOWED_FILES:
        log(f"Ignorando archivo no permitido en manifest: {name}")
        return False

    target = LOCAL_PATH / name
    if local_matches(target, info):
        return False

    url = f"{API_BASE}/files/{quote(name, safe='')}"
    tmp = target.with_name(f".{name}.tmp.{os.getpid()}")
    raw = request(url)
    tmp.write_bytes(raw)

    expected_size = int(info.get("size") or -1)
    if expected_size >= 0 and tmp.stat().st_size != expected_size:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Tamano invalido para {name}")

    expected_hash = str(info.get("sha256") or "").strip()
    if expected_hash and sha256(tmp) != expected_hash:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Hash invalido para {name}")

    mtime = int(info.get("mtime") or time.time())
    os.utime(tmp, (mtime, mtime))
    tmp.replace(target)
    log(f"Actualizado {target}")
    return True


def save_state(manifest: dict[str, Any], downloaded: int) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": manifest.get("version"),
        "file_count": len(manifest.get("files") or []),
        "downloaded": downloaded,
        "updated_at": time.time(),
    }
    STATE_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    LOCAL_PATH.mkdir(parents=True, exist_ok=True)
    manifest = fetch_manifest()
    downloaded = 0
    expected = set()
    for info in manifest.get("files") or []:
        if not isinstance(info, dict):
            continue
        name = Path(str(info.get("name") or "")).name
        if name in ALLOWED_FILES:
            expected.add(name)
        if download_file(info):
            downloaded += 1

    for name in sorted(ALLOWED_FILES - expected):
        stale = LOCAL_PATH / name
        if stale.exists():
            stale.unlink()
            log(f"Eliminado archivo obsoleto {stale}")

    save_state(manifest, downloaded)
    log(
        "Sync de galeria completo: version=%s archivos=%d descargados=%d"
        % (manifest.get("version"), len(expected), downloaded)
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"ERROR: {exc}")
        raise
