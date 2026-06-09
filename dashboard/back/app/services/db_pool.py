from __future__ import annotations

import threading

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

from back.app.config import get_settings

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                s = get_settings()
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=2,
                    maxconn=10,
                    dsn=s.database_url,
                )
    return _pool


def get_connection() -> psycopg2.extensions.connection:
    """Devuelve una conexión directa (no pooled) para uso transaccional manual."""
    s = get_settings()
    return psycopg2.connect(dsn=s.database_url)


def fetch_all(query: str, params=None) -> list:
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchall()
    finally:
        pool.putconn(conn)


def execute(query: str, params=None) -> None:
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def execute_returning(query: str, params=None) -> list:
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            conn.commit()
            return rows
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
