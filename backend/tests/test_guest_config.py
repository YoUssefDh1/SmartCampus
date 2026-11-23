from datetime import datetime, timezone

from app.core.config import Settings
from app.services import guest_service


def test_guest_session_uses_configured_ttl(monkeypatch):
    settings = Settings(_env_file=None, guest_session_ttl_hours=3)
    monkeypatch.setattr(guest_service, "get_settings", lambda: settings)

    class Result:
        def fetchone(self):
            now = datetime.now(timezone.utc)
            return {
                "id": "00000000-0000-0000-0000-000000000001",
                "created_at": now,
                "expires_at": now,
                "last_seen_at": now,
                "claimed_at": None,
            }

    class Connection:
        params = None

        def execute(self, query, params):
            assert "make_interval(hours => %s)" in query
            self.params = params
            return Result()

    connection = Connection()
    session = guest_service.create_guest_session(connection)

    assert connection.params == (3,)
    assert session.id == "00000000-0000-0000-0000-000000000001"
