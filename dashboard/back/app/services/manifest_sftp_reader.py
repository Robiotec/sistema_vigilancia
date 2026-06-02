"""Lectura incremental de manifest.jsonl remoto por SFTP.

No ejecuta Python remoto. Usa solo sftp.stat() + sftp.open().read()
desde el offset persistido en PostgreSQL.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import paramiko
import psycopg2
from psycopg2.extras import RealDictCursor

from back.app.config import Settings

_log = logging.getLogger(__name__)

# Máximo de bytes a leer por ciclo para evitar bloqueos bajo ráfagas.
_MAX_READ_BYTES = 4 * 1024 * 1024  # 4 MB

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS remote_manifest_cursors (
    source_name    text             PRIMARY KEY,
    remote_path    text             NOT NULL,
    offset_bytes   bigint           NOT NULL DEFAULT 0,
    file_size      bigint,
    file_mtime     double precision,
    last_line_hash text,
    updated_at     timestamptz      NOT NULL DEFAULT now()
)
"""


class ManifestSFTPReader:
    """Lee líneas JSONL nuevas de un manifest remoto de forma incremental.

    El cursor (offset de bytes) se persiste en remote_manifest_cursors.
    La tabla se crea automáticamente al primer uso.

    Flujo recomendado (garantía at-least-once):
        rows, new_cursor = reader.read_new_lines(sftp)
        # ... persistir rows en DB ...
        if new_cursor:
            reader.save_cursor(new_cursor)   # avanzar SOLO tras éxito
    """

    _schema_ensured: bool = False  # flag de clase, por proceso

    def __init__(self, settings: Settings, source_name: str, remote_path: str) -> None:
        self._settings = settings
        self._source_name = source_name
        self._remote_path = remote_path

    @property
    def remote_path(self) -> str:
        return self._remote_path

    # ------------------------------------------------------------------ public

    def read_new_lines(
        self, sftp: paramiko.SFTPClient
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """Devuelve (nuevas_filas, nuevo_cursor).

        El caller debe llamar save_cursor(nuevo_cursor) DESPUÉS de persistir
        las filas en la base de datos, para garantizar at-least-once delivery.
        Devuelve ([], None) si no hay datos nuevos o si ocurre un error SFTP.
        """
        self._ensure_schema()
        cursor = self._load_cursor()
        offset = cursor["offset_bytes"]

        try:
            stat = sftp.stat(self._remote_path)
        except FileNotFoundError:
            _log.warning("[manifest:%s] archivo remoto no encontrado: %s", self._source_name, self._remote_path)
            return [], None
        except Exception as exc:
            _log.error("[manifest:%s] sftp.stat falló: %s", self._source_name, exc)
            return [], None

        current_size = int(getattr(stat, "st_size", 0) or 0)
        current_mtime = float(getattr(stat, "st_mtime", 0.0) or 0.0)

        # Detección de truncado / rotación
        if current_size < offset:
            _log.warning(
                "[manifest:%s] truncado/rotado (era %d bytes, ahora %d) — reiniciando offset",
                self._source_name, offset, current_size,
            )
            offset = 0
            cursor["last_line_hash"] = ""

        if current_size == offset:
            return [], None  # sin datos nuevos

        read_length = min(current_size - offset, _MAX_READ_BYTES)

        try:
            with sftp.open(self._remote_path, "rb") as fh:
                fh.seek(offset)
                raw_bytes = fh.read(read_length)
        except Exception as exc:
            _log.error("[manifest:%s] error leyendo bytes: %s", self._source_name, exc)
            return [], None

        # Dividir en líneas completas; descartar línea parcial al final
        text = raw_bytes.decode("utf-8", errors="replace")
        last_nl = text.rfind("\n")
        if last_nl == -1:
            # Sin ninguna línea completa aún — no avanzar offset
            return [], None

        complete_text = text[: last_nl + 1]
        advance_bytes = len(complete_text.encode("utf-8", errors="replace"))
        new_offset = offset + advance_bytes

        # Parsear JSONL
        items: list[dict[str, Any]] = []
        last_hash = cursor.get("last_line_hash") or ""
        for raw_line in complete_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                items.append(row)
            last_hash = hashlib.sha256(line.encode("utf-8")).hexdigest()

        new_cursor: dict[str, Any] = {
            "source_name": self._source_name,
            "remote_path": self._remote_path,
            "offset_bytes": new_offset,
            "file_size": current_size,
            "file_mtime": current_mtime,
            "last_line_hash": last_hash,
        }

        if items:
            _log.info(
                "[manifest:%s] +%d líneas nuevas (+%d bytes, offset→%d)",
                self._source_name, len(items), advance_bytes, new_offset,
            )
        return items, new_cursor

    def seed_to_end(self, sftp: paramiko.SFTPClient) -> int:
        """Avanza el cursor al final del archivo sin procesar líneas.

        Úsalo en el primer arranque (sin cursor previo) para evitar inundar
        Telegram con eventos históricos. Devuelve el tamaño saltado en bytes.
        """
        self._ensure_schema()
        try:
            stat = sftp.stat(self._remote_path)
            current_size = int(getattr(stat, "st_size", 0) or 0)
            current_mtime = float(getattr(stat, "st_mtime", 0.0) or 0.0)
        except Exception:
            return 0

        self.save_cursor({
            "source_name": self._source_name,
            "remote_path": self._remote_path,
            "offset_bytes": current_size,
            "file_size": current_size,
            "file_mtime": current_mtime,
            "last_line_hash": "",
        })
        _log.info("[manifest:%s] seeded a EOF offset=%d", self._source_name, current_size)
        return current_size

    def save_cursor(self, cursor: dict[str, Any]) -> None:
        """Persiste el cursor en PostgreSQL (llamar solo tras procesar rows con éxito)."""
        self._save_cursor(cursor)

    def _save_cursor(self, cursor: dict[str, Any]) -> None:
        try:
            with self._db() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO remote_manifest_cursors
                            (source_name, remote_path, offset_bytes,
                             file_size, file_mtime, last_line_hash, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, now())
                        ON CONFLICT (source_name) DO UPDATE SET
                            remote_path    = EXCLUDED.remote_path,
                            offset_bytes   = EXCLUDED.offset_bytes,
                            file_size      = EXCLUDED.file_size,
                            file_mtime     = EXCLUDED.file_mtime,
                            last_line_hash = EXCLUDED.last_line_hash,
                            updated_at     = now()
                        """,
                        (
                            cursor["source_name"],
                            cursor["remote_path"],
                            cursor["offset_bytes"],
                            cursor.get("file_size"),
                            cursor.get("file_mtime"),
                            cursor.get("last_line_hash") or None,
                        ),
                    )
                conn.commit()
        except Exception as exc:
            _log.error("[manifest:%s] no se pudo guardar cursor: %s", self._source_name, exc)

    def current_offset(self) -> int:
        """Devuelve el offset actual persistido (0 si no existe cursor)."""
        return self._load_cursor()["offset_bytes"]

    # ----------------------------------------------------------------- private

    def _load_cursor(self) -> dict[str, Any]:
        default: dict[str, Any] = {
            "source_name": self._source_name,
            "remote_path": self._remote_path,
            "offset_bytes": 0,
            "file_size": None,
            "file_mtime": None,
            "last_line_hash": "",
        }
        try:
            with self._db() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        "SELECT * FROM remote_manifest_cursors WHERE source_name = %s",
                        (self._source_name,),
                    )
                    row = cur.fetchone()
            if row:
                return {
                    "source_name": str(row["source_name"]),
                    "remote_path": str(row["remote_path"]),
                    "offset_bytes": int(row["offset_bytes"] or 0),
                    "file_size": row.get("file_size"),
                    "file_mtime": row.get("file_mtime"),
                    "last_line_hash": str(row.get("last_line_hash") or ""),
                }
        except Exception as exc:
            _log.warning("[manifest:%s] no se pudo leer cursor: %s", self._source_name, exc)
        return default

    def _ensure_schema(self) -> None:
        if ManifestSFTPReader._schema_ensured:
            return
        try:
            with self._db() as conn:
                with conn.cursor() as cur:
                    cur.execute(_CREATE_TABLE_SQL)
                conn.commit()
            ManifestSFTPReader._schema_ensured = True
        except Exception as exc:
            _log.warning("[manifest] no se pudo asegurar tabla de cursores: %s", exc)

    def _db(self):
        db_url = self._settings.database_url
        if db_url.startswith("postgresql+psycopg://"):
            db_url = db_url.replace("postgresql+psycopg://", "postgresql://", 1)
        return psycopg2.connect(db_url)
