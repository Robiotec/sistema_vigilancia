from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path
from secrets import compare_digest
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.core.config import Settings, get_settings

router = APIRouter(prefix="/faces-gallery", tags=["faces-gallery"])

ALLOWED_FACE_GALLERY_FILES = {
    "embeddings.npz",
    "gallery.faiss",
    "metadata.json",
    "idx_to_cedula.json",
    "state.json",
    "version",
}


def _require_faces_token(
    request: Request,
    x_robiotec_faces_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    expected = settings.faces_gallery_token.strip()
    if not expected:
        raise HTTPException(status_code=503, detail="faces_gallery_disabled")

    supplied = (x_robiotec_faces_token or "").strip()
    auth = request.headers.get("Authorization", "").strip()
    if not supplied and auth.lower().startswith("bearer "):
        supplied = auth.split(" ", 1)[1].strip()
    if not supplied or not compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid_faces_gallery_token")


def _gallery_dir(settings: Settings) -> Path:
    return Path(settings.faces_gallery_dir).expanduser().resolve()


def _safe_gallery_file(settings: Settings, filename: str) -> Path:
    clean_name = Path(filename or "").name
    if clean_name not in ALLOWED_FACE_GALLERY_FILES:
        raise HTTPException(status_code=404, detail="faces_gallery_file_not_found")
    gallery_dir = _gallery_dir(settings)
    file_path = (gallery_dir / clean_name).resolve()
    try:
        file_path.relative_to(gallery_dir)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="faces_gallery_file_not_found") from exc
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="faces_gallery_file_not_found")
    return file_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_info(path: Path, *, include_hash: bool = False) -> dict[str, Any]:
    stat = path.stat()
    info: dict[str, Any] = {
        "name": path.name,
        "size": stat.st_size,
        "mtime": int(stat.st_mtime),
    }
    if include_hash:
        info["sha256"] = _sha256(path)
    return info


def _read_version(settings: Settings) -> str | None:
    try:
        version_file = _safe_gallery_file(settings, "version")
    except HTTPException:
        return None
    try:
        return version_file.read_text(encoding="utf-8").strip()[:120] or None
    except OSError:
        return None


@router.get("/manifest", dependencies=[Depends(_require_faces_token)])
def faces_gallery_manifest(
    include_hashes: bool = Query(default=False),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for filename in sorted(ALLOWED_FACE_GALLERY_FILES):
        try:
            file_path = _safe_gallery_file(settings, filename)
        except HTTPException:
            continue
        files.append(_file_info(file_path, include_hash=include_hashes))
    return {
        "available": bool(files),
        "version": _read_version(settings),
        "files": files,
    }


@router.get("/metadata", dependencies=[Depends(_require_faces_token)])
def faces_gallery_metadata(settings: Settings = Depends(get_settings)) -> Any:
    metadata_path = _safe_gallery_file(settings, "metadata.json")
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="faces_gallery_metadata_invalid") from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="faces_gallery_metadata_unavailable") from exc


@router.get("/files/{filename}", dependencies=[Depends(_require_faces_token)])
def faces_gallery_file(filename: str, settings: Settings = Depends(get_settings)) -> FileResponse:
    file_path = _safe_gallery_file(settings, filename)
    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=file_path.name,
    )
