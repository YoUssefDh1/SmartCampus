from fastapi.testclient import TestClient

from app.core.errors import ForbiddenError
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_health_ok():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "X-Request-ID" in r.headers


def test_swagger_and_openapi_available():
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    assert "/api/v1/chat/message" in spec["paths"]


def test_not_found_uses_error_format():
    r = client.get("/api/v1/inconnu")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND" and err["request_id"]


def test_stub_returns_501_in_error_format():
    r = client.post("/api/v1/chat/message")
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "NOT_IMPLEMENTED"


def test_business_error_and_unexpected_error():
    @app.get("/_test/forbidden")
    def forbidden():
        raise ForbiddenError("Vous n'avez pas accès à ce dossier.")

    @app.get("/_test/boom")
    def boom():
        raise RuntimeError("secret interne")

    r = client.get("/_test/forbidden")
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    r = client.get("/_test/boom")
    assert r.status_code == 500
    assert "secret" not in r.text  # aucun détail interne exposé


# Les tests du catalogue (formations, tarifs, admission) sont dans test_catalog.py.
