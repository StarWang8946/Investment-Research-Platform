from collections.abc import Generator

import psycopg
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from app.core.config import get_settings

_pool: ConnectionPool | None = None


def create_pool() -> ConnectionPool:
    settings = get_settings()
    return ConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        timeout=settings.db_pool_timeout,
        kwargs={"row_factory": dict_row},
        open=False,
    )


def open_pool() -> None:
    global _pool
    if _pool is None:
        _pool = create_pool()
        _pool.open()


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_pool() -> ConnectionPool:
    if _pool is None:
        open_pool()
    if _pool is None:
        raise RuntimeError("Database connection pool is not initialized")
    return _pool


def get_conn() -> Generator[psycopg.Connection, None, None]:
    with get_pool().connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
