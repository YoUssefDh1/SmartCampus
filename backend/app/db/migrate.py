"""Apply the versioned SQL schema migrations."""

import hashlib
import re
from pathlib import Path

from app.db.session import get_connection

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_DIR = Path(__file__).resolve().parents[2] / "migrations"
INITIAL_MIGRATION = ("001_initial_schema", PROJECT_ROOT / "schema.sql")


def _migration_files() -> list[tuple[str, Path]]:
    migrations = [INITIAL_MIGRATION]
    migrations.extend(
        (path.stem, path) for path in sorted(MIGRATION_DIR.glob("*.sql"))
    )
    versions = [version for version, _ in migrations]
    if len(versions) != len(set(versions)):
        raise RuntimeError("Migration versions must be unique.")
    return migrations


def _without_transaction_wrapper(sql: str) -> str:
    sql = re.sub(r"(?m)^\s*BEGIN\s*;\s*$", "", sql, count=1)
    return re.sub(r"(?m)^\s*COMMIT\s*;\s*$", "", sql, count=1)


def main() -> None:
    connection = get_connection()
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS smartcampus_schema_migrations (
                version text PRIMARY KEY,
                checksum char(64) NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )

        for version, path in _migration_files():
            contents = path.read_bytes()
            checksum = hashlib.sha256(contents).hexdigest()
            applied = connection.execute(
                "SELECT checksum FROM smartcampus_schema_migrations WHERE version = %s",
                (version,),
            ).fetchone()

            if applied:
                if applied[0].strip() != checksum:
                    raise RuntimeError(
                        f"Applied migration {version} was modified. "
                        "Add a new migration instead of editing it."
                    )
                print(f"Already applied: {version}")
                continue

            sql = _without_transaction_wrapper(contents.decode("utf-8"))
            with connection.transaction():
                connection.execute(sql, prepare=False)
                connection.execute(
                    "INSERT INTO smartcampus_schema_migrations (version, checksum) VALUES (%s, %s)",
                    (version, checksum),
                )
            print(f"Applied: {version}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
