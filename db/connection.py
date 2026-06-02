from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Generator, Iterable, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

try:
    from .config import db_config
except ImportError:
    from config import db_config

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Error general de base de datos."""


class DatabasePool:
    def __init__(self) -> None:
        self._pool: Optional[ConnectionPool] = None

    @property
    def is_open(self) -> bool:
        return self._pool is not None

    def open(self, retries: int = 5, delay: float = 2.0) -> None:
        if self._pool is not None:
            logger.info("El pool ya está inicializado.")
            return

        last_error: Optional[Exception] = None

        for attempt in range(1, retries + 1):
            try:
                logger.info(
                    "Intentando abrir pool PostgreSQL (intento %s/%s)...",
                    attempt,
                    retries,
                )

                self._pool = ConnectionPool(
                    conninfo=db_config.dsn,
                    min_size=db_config.min_size,
                    max_size=db_config.max_size,
                    timeout=db_config.timeout,
                    check=ConnectionPool.check_connection,
                    kwargs={"row_factory": dict_row, "autocommit": False},
                    open=True,
                )

                with self._pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1 AS ok;")
                        result = cur.fetchone()

                        if not result or result["ok"] != 1:
                            raise DatabaseError("Health check inválido.")

                logger.info("Pool PostgreSQL inicializado correctamente.")
                return

            except Exception as exc:
                last_error = exc
                logger.exception("Fallo al abrir el pool: %s", exc)
                time.sleep(delay)

        raise DatabaseError(
            f"No se pudo inicializar el pool PostgreSQL tras {retries} intentos."
        ) from last_error

    def close(self) -> None:
        if self._pool is not None:
            logger.info("Cerrando pool PostgreSQL...")
            self._pool.close()
            self._pool = None
            logger.info("Pool PostgreSQL cerrado.")

    @contextmanager
    def connection(self) -> Generator[psycopg.Connection[Any], None, None]:
        if self._pool is None:
            raise DatabaseError("El pool no está inicializado. Llama a open().")

        with self._pool.connection() as conn:
            yield conn

    def health_check(self) -> bool:
        try:
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 AS ok;")
                    row = cur.fetchone()
                    return bool(row and row["ok"] == 1)
        except Exception as exc:
            logger.error("Health check falló: %s", exc)
            return False

    def fetch_one(
        self,
        query: str,
        params: Optional[Iterable[Any]] = None,
    ) -> Optional[dict[str, Any]]:
        try:
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params or ())
                    return cur.fetchone()
        except Exception as exc:
            logger.exception("Error en fetch_one: %s", exc)
            raise DatabaseError("Error ejecutando fetch_one.") from exc

    def fetch_all(
        self,
        query: str,
        params: Optional[Iterable[Any]] = None,
    ) -> list[dict[str, Any]]:
        try:
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params or ())
                    rows = cur.fetchall()
                    return list(rows)
        except Exception as exc:
            logger.exception("Error en fetch_all: %s", exc)
            raise DatabaseError("Error ejecutando fetch_all.") from exc

    def execute(
        self,
        query: str,
        params: Optional[Iterable[Any]] = None,
    ) -> None:
        try:
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params or ())
        except Exception as exc:
            logger.exception("Error en execute: %s", exc)
            raise DatabaseError("Error ejecutando sentencia SQL.") from exc

    def execute_returning_one(
        self,
        query: str,
        params: Optional[Iterable[Any]] = None,
    ) -> Optional[dict[str, Any]]:
        try:
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params or ())
                    return cur.fetchone()
        except Exception as exc:
            logger.exception("Error en execute_returning_one: %s", exc)
            raise DatabaseError("Error ejecutando sentencia con RETURNING.") from exc


db = DatabasePool()


if __name__ == "__main__":
    try:
        db.open()

        print("Pool abierto exitosamente.")
        print("Health check:", db.health_check())

        results = db.fetch_all("""
            SELECT
                c.id,
                c.name,
                c.unique_code,
                c.active,
                c.rtsp_url,
                c.ip,
                c.channel,
                c.uses_rbox,
                c.rbox_id,

                r.name AS rbox_name,
                r.serial AS rbox_serial

            FROM cameras c
            LEFT JOIN rboxes r
                ON c.rbox_id = r.id
            ORDER BY c.id;
        """)

        for row in results:
            print(" RESULTADO ".center(60, "="))

            print(f"""
id: {row["id"]}
name: {row["name"]}
unique_code: {row["unique_code"]}
active: {row["active"]}
url: {row["rtsp_url"]}
ip: {row["ip"]}
channel: {row["channel"]}
uses_rbox: {row["uses_rbox"]}
rbox_id: {row["rbox_id"]}
""")

            if row["uses_rbox"]:
                print(f"""
RBOX:
  name: {row["rbox_name"]}
  serial: {row["rbox_serial"]}
""")
            else:
                print("RBOX: No usa RBox")

    except DatabaseError as exc:
        print("Error al abrir el pool:", exc)

    finally:
        db.close()