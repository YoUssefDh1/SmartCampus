"""PostgreSQL connection used by the database tooling and backend."""

import psycopg

from app.core.config import get_settings


def get_connection() -> psycopg.Connection:
    """Open a PostgreSQL connection using the configured DATABASE_URL."""
    database_url = get_settings().database_url
    dsn = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    return psycopg.connect(dsn, autocommit=True)
