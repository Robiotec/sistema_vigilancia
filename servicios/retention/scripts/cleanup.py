#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psycopg


ROOT_DIR = Path(os.environ.get("ROBIOTEC_ROOT", "/root/robiotec"))
APICENTRAL_ENV = ROOT_DIR / "apicentral" / ".env"
DASHBOARD_ENV = ROOT_DIR / "dashboard" / ".env"


@dataclass(frozen=True)
class DbRetentionRule:
    table: str
    column: str
    days_env: str
    default_days: int
    extra_condition: str = ""


DB_RULES = (
    DbRetentionRule("vehicle_telemetry", "received_at", "ROBIOTEC_TELEMETRY_RETENTION_DAYS", 180),
    DbRetentionRule("drone_telemetry", "received_at", "ROBIOTEC_TELEMETRY_RETENTION_DAYS", 180),
    DbRetentionRule("camera_event_history", "detected_at", "ROBIOTEC_EVENT_RETENTION_DAYS", 365),
    DbRetentionRule("geofence_alerts", "recorded_at", "ROBIOTEC_EVENT_RETENTION_DAYS", 365),
    DbRetentionRule(
        "camera_alert_outbox",
        "created_at",
        "ROBIOTEC_EVENT_RETENTION_DAYS",
        365,
        " AND status IN ('sent', 'failed')",
    ),
    DbRetentionRule("stream_access_tokens", "expires_at", "ROBIOTEC_TOKEN_RETENTION_DAYS", 30),
    DbRetentionRule("device_publish_tokens", "expires_at", "ROBIOTEC_TOKEN_RETENTION_DAYS", 30),
)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "si"}


def env_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name, "")
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


def database_dsn() -> str:
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        raise RuntimeError("DATABASE_URL no esta configurado para la limpieza de retencion")
    return raw.replace("postgresql+psycopg://", "postgresql://", 1)


def table_exists(conn: psycopg.Connection, table: str, column: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema = 'public'
                AND table_name = %s
                AND column_name = %s
            )
            """,
            (table, column),
        )
        return bool(cur.fetchone()[0])


def db_condition(rule: DbRetentionRule) -> str:
    return (
        f"{rule.column} IS NOT NULL "
        f"AND {rule.column} < NOW() - (%s * INTERVAL '1 day')"
        f"{rule.extra_condition}"
    )


def cleanup_database(dry_run: bool) -> int:
    batch_size = env_int("ROBIOTEC_RETENTION_BATCH_SIZE", 10000)
    statement_timeout_ms = env_int("ROBIOTEC_RETENTION_STATEMENT_TIMEOUT_MS", 60000)
    total_deleted = 0

    with psycopg.connect(database_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = {statement_timeout_ms}")
        for rule in DB_RULES:
            days = env_int(rule.days_env, rule.default_days)
            if not table_exists(conn, rule.table, rule.column):
                print(f"[db] omite public.{rule.table}: columna {rule.column} no existe")
                continue

            condition = db_condition(rule)
            with conn.cursor() as cur:
                cur.execute(f"SELECT count(*) FROM public.{rule.table} WHERE {condition}", (days,))
                pending = int(cur.fetchone()[0])

            print(f"[db] public.{rule.table}: {pending} filas mayores a {days} dias")
            if dry_run or pending == 0:
                continue

            deleted_for_table = 0
            while True:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        DELETE FROM public.{rule.table}
                        WHERE ctid IN (
                          SELECT ctid
                          FROM public.{rule.table}
                          WHERE {condition}
                          LIMIT %s
                        )
                        """,
                        (days, batch_size),
                    )
                    deleted = cur.rowcount
                conn.commit()
                deleted_for_table += deleted
                total_deleted += deleted
                if deleted < batch_size:
                    break
            print(f"[db] public.{rule.table}: {deleted_for_table} filas eliminadas")

    return total_deleted


def iter_cleanup_dirs() -> Iterable[Path]:
    default_dirs = [
        ROOT_DIR / "dashboard" / "back" / "app" / "data" / "event_videos",
        ROOT_DIR / "dashboard" / "back" / "app" / "data" / "telegram_clip_crops",
        ROOT_DIR / "dashboard" / "back" / "app" / "data" / "cache",
    ]
    configured = os.environ.get("ROBIOTEC_FILE_CLEANUP_DIRS", "")
    values = [Path(item.strip()) for item in configured.split(",") if item.strip()]
    return values or default_dirs


def cleanup_files(dry_run: bool) -> tuple[int, int]:
    days = env_int("ROBIOTEC_FILE_RETENTION_DAYS", 365)
    max_delete = env_int("ROBIOTEC_FILE_MAX_DELETE", 5000)
    cutoff = time.time() - days * 86400
    total_files = 0
    total_bytes = 0

    for directory in iter_cleanup_dirs():
        if not directory.exists():
            print(f"[files] omite {directory}: no existe")
            continue
        for path in directory.rglob("*"):
            if total_files >= max_delete:
                print(f"[files] limite de {max_delete} archivos alcanzado")
                return total_files, total_bytes
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            if not path.is_file() or stat.st_mtime >= cutoff:
                continue
            total_files += 1
            total_bytes += stat.st_size
            if not dry_run:
                path.unlink(missing_ok=True)

    print(f"[files] {total_files} archivos mayores a {days} dias ({total_bytes / 1048576:.1f} MB)")
    return total_files, total_bytes


def cleanup_minio(dry_run: bool) -> bool:
    if not env_bool("ROBIOTEC_MINIO_RETENTION_ENABLED", True):
        print("[minio] limpieza deshabilitada por ROBIOTEC_MINIO_RETENTION_ENABLED=false")
        return True

    alias = os.environ.get("ROBIOTEC_MINIO_ALIAS", "local").strip()
    bucket = os.environ.get("MINIO_BUCKET", "eventos").strip()
    days = env_int("ROBIOTEC_MINIO_RETENTION_DAYS", 365)
    if not alias or not bucket:
        print("[minio] alias o bucket no configurados")
        return False

    target = f"{alias}/{bucket}/"
    cmd = [
        "mc",
        "rm",
        "--recursive",
        "--force",
        "--older-than",
        f"{days}d",
        "--disable-pager",
        "--no-color",
    ]
    if dry_run:
        cmd.append("--dry-run")
    cmd.append(target)

    print(f"[minio] {'dry-run ' if dry_run else ''}retencion {target} mayor a {days} dias")
    result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    output = result.stdout.strip()
    if output:
        lines = output.splitlines()
        for line in lines[-20:]:
            print(f"[minio] {line}")
    return result.returncode == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Limpieza de retencion Robiotec")
    parser.add_argument("--dry-run", action="store_true", help="Cuenta lo que se limpiaria sin borrar datos")
    parser.add_argument("--skip-minio", action="store_true", help="No ejecutar limpieza de MinIO")
    parser.add_argument("--skip-files", action="store_true", help="No ejecutar limpieza de archivos locales")
    parser.add_argument("--skip-db", action="store_true", help="No ejecutar limpieza de base de datos")
    return parser.parse_args()


def main() -> int:
    load_env_file(APICENTRAL_ENV)
    load_env_file(DASHBOARD_ENV)
    args = parse_args()
    dry_run = args.dry_run or env_bool("ROBIOTEC_RETENTION_DRY_RUN", False)

    print(f"[retention] inicio dry_run={dry_run}")
    ok = True

    if not args.skip_db:
        try:
            deleted = cleanup_database(dry_run=dry_run)
            print(f"[retention] db_deleted={deleted}")
        except Exception as exc:
            ok = False
            print(f"[retention] error en db: {exc}", file=sys.stderr)

    if not args.skip_files:
        try:
            cleanup_files(dry_run=dry_run)
        except Exception as exc:
            ok = False
            print(f"[retention] error en archivos: {exc}", file=sys.stderr)

    if not args.skip_minio:
        ok = cleanup_minio(dry_run=dry_run) and ok

    print(f"[retention] fin ok={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
