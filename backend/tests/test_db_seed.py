import json

from app.db import seed


def test_seed_demo_users_hashes_passwords_and_is_repeatable(monkeypatch):
    demo_users = json.loads(seed.DEMO_USERS_PATH.read_text(encoding="utf-8"))
    existing_emails = set()
    accounts = {}

    def create_account(_connection, **account):
        existing_emails.add(account["email"])
        accounts[account["email"]] = account

    monkeypatch.setattr(
        seed.user_service,
        "email_exists",
        lambda _connection, email: email in existing_emails,
    )
    monkeypatch.setattr(seed.user_service, "create_account", create_account)
    monkeypatch.setattr(seed, "hash_password", lambda password: f"hashed:{password}")

    assert seed.seed_demo_users(object()) == len(demo_users)
    assert seed.seed_demo_users(object()) == 0
    assert len(accounts) == len(demo_users)

    for user in demo_users:
        account = accounts[user["email"]]
        assert account["password_hash"] == f"hashed:{user['password']}"
        assert "password" not in account
