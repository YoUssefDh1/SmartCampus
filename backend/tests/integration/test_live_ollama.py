import os

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_connection
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LLM_INTEGRATION") != "1",
    reason="Set RUN_LLM_INTEGRATION=1 to run against the configured live Ollama model.",
)

client = TestClient(app, raise_server_exceptions=False)


def test_live_ollama_chat_handles_languages_and_follow_up():
    guest_response = client.post("/api/v1/auth/guest")
    assert guest_response.status_code == 201, guest_response.text
    guest = guest_response.json()
    headers = {"Authorization": f"Bearer {guest['access_token']}"}

    try:
        first = client.post(
            "/api/v1/chat/message",
            json={"message": "J'aime les maths et la programmation."},
            headers=headers,
        )
        assert first.status_code == 200, first.text
        first_body = first.json()
        assert first_body["reply"].strip()
        assert first_body["language"] == "fr"

        follow_up = client.post(
            "/api/v1/chat/message",
            json={
                "session_id": first_body["session_id"],
                "message": "nheb na3ref chnoua najem na9ra",
            },
            headers=headers,
        )
        assert follow_up.status_code == 200, follow_up.text
        assert follow_up.json()["reply"].strip()
        assert follow_up.json()["session_id"] == first_body["session_id"]
        assert follow_up.json()["language"] == "arabizi"

        tunisian = client.post(
            "/api/v1/chat/message",
            json={"message": "شنوة أحسن تكوين نجم نعملو؟"},
            headers=headers,
        )
        assert tunisian.status_code == 200, tunisian.text
        assert tunisian.json()["reply"].strip()
        assert tunisian.json()["language"] == "tn-arabic"
    finally:
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM conversation WHERE guest_session_id = %s",
                (guest["session_id"],),
            )
            connection.execute(
                "DELETE FROM guest_session WHERE id = %s",
                (guest["session_id"],),
            )
