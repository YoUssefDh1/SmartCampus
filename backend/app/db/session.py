"""PostgreSQL connection used by the database tooling and backend."""

import atexit
import threading
from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from app.core.config import get_settings
from app.core.errors import DatabaseUnavailableError

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def _dsn() -> str:
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def get_connection() -> psycopg.Connection:
    """Open a PostgreSQL connection using the configured DATABASE_URL (tooling: migrate, seed)."""
    return psycopg.connect(_dsn(), autocommit=True)


def get_dict_connection() -> psycopg.Connection:
    """Open a PostgreSQL connection that returns rows keyed by column name."""
    connection = get_connection()
    connection.row_factory = dict_row
    return connection


def get_pool() -> ConnectionPool:
    """Pool shared by the API. Connections are in autocommit mode and return rows as dicts;
    services wrap their writes in `with conn.transaction():`."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                s = get_settings()
                _pool = ConnectionPool(
                    _dsn(), min_size=1, max_size=s.db_pool_max_size, timeout=s.db_pool_timeout_seconds,
                    kwargs={"autocommit": True, "row_factory": dict_row}, open=True, name="smartcampus",
                )
                atexit.register(close_pool)
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_db() -> Iterator[psycopg.Connection]:
    """FastAPI dependency: one pooled connection per request."""
    try:
        cm = get_pool().connection()
        conn = cm.__enter__()
    except (PoolTimeout, psycopg.OperationalError) as exc:
        raise DatabaseUnavailableError(
            "Base de données injoignable. Vérifiez que PostgreSQL est lancé (docker compose up -d).") from exc
    try:
        yield conn
    except BaseException as exc:
        cm.__exit__(type(exc), exc, exc.__traceback__)
        raise
    else:
        cm.__exit__(None, None, None)
