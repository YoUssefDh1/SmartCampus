"""Outils communs aux tests d'API : en-têtes de rôle, fabriques de données, vérification du format d'erreur.

Toutes les données créées par les tests ont un code « T-xxxxxxxx » (formations, matières) et sont
supprimées par la fixture `catalog_cleanup` (conftest.py).
"""
import uuid
from datetime import date, timedelta

API = "/api/v1"
TODAY = date.today()
CURRENT_YEAR = f"{TODAY.year}-{TODAY.year + 1}" if TODAY.month >= 9 else f"{TODAY.year - 1}-{TODAY.year}"

# Rôles simulés (mode démo AUTH_DEV_MODE, activé par conftest.py)
ADMIN = {"X-Dev-Role": "admin"}
IIT = {"X-Dev-Role": "iit_manager"}
ISB = {"X-Dev-Role": "isb_manager"}
DIRECTION = {"X-Dev-Role": "direction"}
CANDIDATE = {"X-Dev-Role": "candidate"}
INTERVIEWER = {"X-Dev-Role": "interviewer"}
ADVISOR = {"X-Dev-Role": "advisor"}


def code(prefix: str = "T") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}".upper()


def days(n: int) -> str:
    return str(TODAY + timedelta(days=n))


def assert_error(response, status: int, code_: str) -> dict:
    """Toute erreur respecte le format SA-5 : {"error": {code, message, details, request_id}}."""
    assert response.status_code == status, f"{response.status_code} != {status} : {response.text}"
    body = response.json()
    assert set(body) == {"error"}, body
    err = body["error"]
    assert err["code"] == code_, err
    assert isinstance(err["message"], str) and err["message"].strip(), err
    assert isinstance(err["details"], list), err
    assert err["request_id"] and response.headers["X-Request-ID"] == err["request_id"], err
    return err


def _created(response) -> dict:
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- fabriques
def make_program(client, headers=IIT, **over) -> dict:
    body = {"code": code(), "name": "Formation de test", "cycle": "bachelor", "duration_years": 3,
            "teaching_languages": ["fr"], **over}
    return _created(client.post(f"{API}/catalog/programs", headers=headers, json=body))


def make_specialty(client, program_id, headers=IIT, **over) -> dict:
    body = {"name": f"Spécialité {uuid.uuid4().hex[:6]}", **over}
    return _created(client.post(f"{API}/catalog/programs/{program_id}/specialties", headers=headers, json=body))


def make_subject(client, headers=IIT, **over) -> dict:
    body = {"code": code(), "name": "Matière de test", **over}
    return _created(client.post(f"{API}/catalog/subjects", headers=headers, json=body))


def make_curriculum(client, program_id, headers=IIT, **over) -> dict:
    body = {"program_id": program_id, "academic_year": CURRENT_YEAR, **over}
    return _created(client.post(f"{API}/catalog/curricula", headers=headers, json=body))


def make_fee(client, program_id, headers=IIT, **over) -> dict:
    body = {"program_id": program_id, "academic_year": CURRENT_YEAR, "fee_type": "tuition", "amount": "5000", **over}
    return _created(client.post(f"{API}/catalog/tuition-fees", headers=headers, json=body))


def make_requirement(client, program_id, headers=IIT, **over) -> dict:
    body = {"program_id": program_id, "kind": "document", "description": "Relevé de notes", **over}
    return _created(client.post(f"{API}/catalog/admission-requirements", headers=headers, json=body))


def make_plan(client, program_id, headers=IIT, **over) -> dict:
    body = {"program_id": program_id, "academic_year": CURRENT_YEAR, "name": f"Plan {uuid.uuid4().hex[:6]}",
            "installments": [{"label": "Unique", "percentage": 100}], **over}
    return _created(client.post(f"{API}/catalog/payment-plans", headers=headers, json=body))


def publish(client, resource: str, item_id: str, headers=IIT) -> dict:
    r = client.post(f"{API}/catalog/{resource}/{item_id}/status", headers=headers, json={"status": "published"})
    assert r.status_code == 200, r.text
    return r.json()


def seed_program(db, code_: str) -> str:
    """Identifiant d'une formation du seed (PREPA-INT, ING-INFO, LIC-GEST, MP-FIN)."""
    row = db.execute("SELECT id FROM program WHERE code = %s", (code_,)).fetchone()
    assert row, f"Formation {code_} absente : lancer python -m app.db.seed"
    return str(row[0])
