"""Load the repository's repeatable demonstration data."""

import json
from pathlib import Path

import psycopg

from app.core.security import hash_password
from app.db.migrate import _migration_files
from app.db.session import get_dict_connection
from app.models.user import split_full_name
from app.services import user_service

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEMO_USERS_PATH = PROJECT_ROOT / "data" / "demo" / "users.json"


def seed_demo_users(connection: psycopg.Connection) -> int:
    users = json.loads(DEMO_USERS_PATH.read_text(encoding="utf-8"))
    created = 0
    for user in users:
        if user_service.email_exists(connection, user["email"]):
            continue

        first_name, last_name = split_full_name(user["full_name"])
        user_service.create_account(
            connection,
            email=user["email"],
            password_hash=hash_password(user["password"]),
            first_name=first_name,
            last_name=last_name,
            role=user["role"],
            institution_code=user["school_scope"],
        )
        created += 1
    return created


def main() -> None:
    seed_path = PROJECT_ROOT / "seed.sql"
    sql = seed_path.read_text(encoding="utf-8")
    connection = get_dict_connection()
    try:
        migration_table = connection.execute(
            "SELECT to_regclass('public.smartcampus_schema_migrations') AS migration_table"
        ).fetchone()["migration_table"]
        if not migration_table:
            raise RuntimeError("Run `python -m app.db.migrate` before loading the seed.")

        applied = {
            row["version"]
            for row in connection.execute(
                "SELECT version FROM smartcampus_schema_migrations"
            ).fetchall()
        }
        missing = [version for version, _ in _migration_files() if version not in applied]
        if missing:
            raise RuntimeError(
                f"Missing migrations {missing}: run `python -m app.db.migrate` before loading the seed.")

        with connection.transaction():
            connection.execute(sql, prepare=False)
        print("Demonstration seed applied.")

        print(f"Demo users created: {seed_demo_users(connection)}.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
