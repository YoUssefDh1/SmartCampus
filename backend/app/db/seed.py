"""Load the repository's repeatable demonstration data."""

import json
from pathlib import Path

from app.core.security import hash_password
from app.db.session import get_dict_connection
from app.models.user import split_full_name
from app.services import user_service

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INITIAL_MIGRATION = "001_initial_schema"
DEMO_USERS = PROJECT_ROOT / "data" / "demo" / "users.json"


def seed_demo_users(connection) -> int:
    """Comptes de démonstration (SA-28). Idempotent : un email déjà présent est ignoré."""
    if not DEMO_USERS.exists():
        return 0
    created = 0
    for entry in json.loads(DEMO_USERS.read_text(encoding="utf-8")):
        if user_service.email_exists(connection, entry["email"]):
            continue
        first_name, last_name = split_full_name(entry["full_name"])
        user_service.create_account(
            connection,
            email=entry["email"],
            password_hash=hash_password(entry["password"]),
            first_name=first_name,
            last_name=last_name,
            role=entry["role"],
            institution_code=entry.get("school_scope"),
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

        applied = connection.execute(
            "SELECT 1 FROM smartcampus_schema_migrations WHERE version = %s",
            (INITIAL_MIGRATION,),
        ).fetchone()
        if not applied:
            raise RuntimeError("Run `python -m app.db.migrate` before loading the seed.")

        with connection.transaction():
            connection.execute(sql, prepare=False)
        print("Demonstration seed applied.")

        print(f"Demo users created: {seed_demo_users(connection)}.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
