"""Load the repository's repeatable demonstration data."""

from pathlib import Path

from app.db.session import get_connection

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INITIAL_MIGRATION = "001_initial_schema"


def main() -> None:
    seed_path = PROJECT_ROOT / "seed.sql"
    sql = seed_path.read_text(encoding="utf-8")
    connection = get_connection()
    try:
        migration_table = connection.execute(
            "SELECT to_regclass('public.smartcampus_schema_migrations')"
        ).fetchone()[0]
        if not migration_table:
            raise RuntimeError("Run `python -m app.db.migrate` before loading the seed.")

        applied = connection.execute(
            "SELECT 1 FROM smartcampus_schema_migrations WHERE version = %s",
            (INITIAL_MIGRATION,),
        ).fetchone()
        if not applied:
            raise RuntimeError("Run `python -m app.db.migrate` before loading the seed.")

        with connection.transaction():
            connection.execute(sql, prepare=False)
        print("Demonstration seed applied.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
