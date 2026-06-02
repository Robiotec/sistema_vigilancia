import os
import threading

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

_DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "207.246.68.223"),
    "port": int(os.environ.get("DB_PORT", "5432")),
    "database": os.environ.get("DB_NAME", "robiotec_vms"),
    "user": os.environ.get("DB_USER", "robiotec_app"),
    "password": os.environ.get("DB_PASSWORD", "Robiotec@2026"),
    "sslmode": "require",
}

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = psycopg2.pool.ThreadedConnectionPool(minconn=2, maxconn=10, **_DB_CONFIG)
    return _pool


def fetch_all(query, params=None):
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchall()
    finally:
        pool.putconn(conn)


def execute(query, params=None):
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


def execute_returning(query, params=None):
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


if __name__ == "__main__":
    try:
        rows = fetch_all("SELECT * FROM notification_email_recipients")
        for row in rows:
            print(row)
    except Exception as e:
        print(f"Error al conectar a PostgreSQL: {e}")
            
