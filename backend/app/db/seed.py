"""Load the repository's repeatable demonstration data."""

from pathlib import Path

from app.db.migrate import _migration_files
from app.db.session import get_connection

PROJECT_ROOT = Path(__file__).resolve().parents[3]


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

        applied = {row[0] for row in connection.execute(
            "SELECT version FROM smartcampus_schema_migrations").fetchall()}
        missing = [version for version, _ in _migration_files() if version not in applied]
        if missing:
            raise RuntimeError(
                f"Missing migrations {missing}: run `python -m app.db.migrate` before loading the seed.")

        with connection.transaction():
            connection.execute(sql, prepare=False)
        print("Demonstration seed applied.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
