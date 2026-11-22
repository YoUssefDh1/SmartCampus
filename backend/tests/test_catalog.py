"""Catalogue : formations et programmes, tarifs, modalités de paiement, conditions d'admission.

Prérequis : base migrée et seed chargé (python -m app.db.migrate && python -m app.db.seed).
Les éléments créés ici ont un code « T-xxxxxxxx » et sont supprimés à la fin.
"""
import time
import uuid
from datetime import date, timedelta

import jwt
import pytest

from app.core.config import get_settings

API = "/api/v1"
ADMIN = {"X-Dev-Role": "admin"}
IIT = {"X-Dev-Role": "iit_manager"}
ISB = {"X-Dev-Role": "isb_manager"}
TODAY = date.today()


def code() -> str:
    return f"T-{uuid.uuid4().hex[:8]}".upper()


pytestmark = pytest.mark.usefixtures("catalog_cleanup")


@pytest.fixture(scope="module")
def iit_program(client):
    r = client.post(f"{API}/catalog/programs", headers=IIT, json={
        "code": code(), "name": "Formation de test", "cycle": "engineering", "duration_years": 3,
        "teaching_languages": ["FR", "en", "fr"], "description": "Formation créée par les tests"})
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- public
def test_public_list_search_and_filters(client, db):
    r = client.get(f"{API}/programs")
    assert r.status_code == 200 and r.json()["total"] >= 4
    assert all(p["is_active"] for p in r.json()["items"])
    r = client.get(f"{API}/programs", params={"school": "ISB"})
    assert r.json()["items"] and all(p["school"] == "ISB" for p in r.json()["items"])
    r = client.get(f"{API}/programs", params={"level": "Ingenierie"})  # libellé sans accent
    assert r.json()["items"] and all(p["cycle"] == "engineering" for p in r.json()["items"])
    r = client.get(f"{API}/programs", params={"q": "genie informatique"})  # recherche sans accent
    assert any(p["code"] == "ING-INFO" for p in r.json()["items"])
    assert client.get(f"{API}/programs", params={"level": "inconnu"}).status_code == 422


def test_public_detail_contains_only_official_information(client):
    program = client.get(f"{API}/programs", params={"q": "ING-INFO"}).json()["items"][0]
    detail = client.get(f"{API}/programs/{program['id']}").json()
    assert detail["level"] == "Ingénierie" and detail["specialties"]
    assert detail["tuition_fees"] and detail["payment_plans"] and detail["admission_requirements"]
    # Le seed contient un tarif 2027-2028 en brouillon : il ne doit jamais sortir.
    assert all(f["academic_year"] != "2027-2028" for f in detail["tuition_fees"])
    tuition = client.get(f"{API}/programs/{program['id']}/tuition", params={"academic_year": "2026-2027"}).json()
    assert {f["fee_type"] for f in tuition["fees"]} == {"registration", "tuition"}
    plans = {p["name"]: p for p in tuition["payment_plans"]}
    assert [i["percentage"] for i in plans["Paiement en 3 tranches"]["installments"]] == [40, 30, 30]


def test_public_errors(client):
    r = client.get(f"{API}/programs/{uuid.uuid4()}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    assert client.get(f"{API}/programs/pas-un-uuid").status_code == 422
    assert client.get(f"{API}/programs/{uuid.uuid4()}/tuition").status_code == 404


# --------------------------------------------------------------------------- accès
def test_management_requires_a_staff_role(client):
    assert client.get(f"{API}/catalog/programs").status_code == 401
    r = client.get(f"{API}/catalog/programs", headers={"X-Dev-Role": "candidate"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    assert client.post(f"{API}/catalog/subjects", headers={"X-Dev-Role": "direction"},
                       json={"code": code(), "name": "Lecture seule"}).status_code == 403
    assert client.get(f"{API}/catalog/programs", headers={"X-Dev-Role": "direction"}).status_code == 200


def test_jwt_staff_token(client, db):
    inst = db.execute("SELECT id FROM institution WHERE code = 'ISB'").fetchone()[0]
    user_id = db.execute(
        """INSERT INTO app_user (role, institution_id, first_name, last_name, email, password_hash)
           VALUES ('isb_manager', %s, 'Test', 'Manager', %s, 'x') RETURNING id""",
        (inst, f"test-{uuid.uuid4().hex[:6]}@smartcampus.test")).fetchone()[0]
    s = get_settings()
    token = jwt.encode({"sub": str(user_id), "role": "isb_manager", "exp": int(time.time()) + 600},
                       s.jwt_secret, algorithm=s.jwt_algorithm)
    r = client.get(f"{API}/catalog/programs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and {p["school"] for p in r.json()["items"]} == {"ISB"}
    assert client.get(f"{API}/catalog/programs", headers={"Authorization": "Bearer faux"}).status_code == 401
    db.execute("UPDATE app_user SET is_active = false WHERE id = %s", (user_id,))
    assert client.get(f"{API}/catalog/programs", headers={"Authorization": f"Bearer {token}"}).status_code == 401


# --------------------------------------------------------------------------- formations
def test_program_crud_and_school_scope(client, iit_program, db):
    pid = iit_program["id"]
    assert iit_program["school"] == "IIT" and iit_program["code"].startswith("T-")
    assert iit_program["teaching_languages"] == ["fr", "en"]

    r = client.patch(f"{API}/catalog/programs/{pid}", headers=IIT, json={"capacity": 30, "degree": "DNI"})
    assert r.status_code == 200 and r.json()["capacity"] == 30
    assert client.patch(f"{API}/catalog/programs/{pid}", headers=IIT, json={"name": None}).status_code == 422
    # Un responsable ISB ne voit pas et ne modifie pas une formation de l'IIT.
    assert client.get(f"{API}/catalog/programs/{pid}", headers=ISB).status_code == 403
    assert client.patch(f"{API}/catalog/programs/{pid}", headers=ISB, json={"capacity": 1}).status_code == 403
    isb_id = str(db.execute("SELECT id FROM institution WHERE code = 'ISB'").fetchone()[0])
    r = client.post(f"{API}/catalog/programs", headers=IIT,
                    json={"institution_id": isb_id, "code": code(), "name": "Interdit", "cycle": "master"})
    assert r.status_code == 403
    # L'administrateur doit choisir l'école.
    r = client.post(f"{API}/catalog/programs", headers=ADMIN, json={"code": code(), "name": "Sans école",
                                                                    "cycle": "other"})
    assert r.status_code == 422
    # Doublon de code dans la même école -> 409 avec message clair.
    r = client.post(f"{API}/catalog/programs", headers=IIT,
                    json={"code": iit_program["code"], "name": "Doublon", "cycle": "other"})
    assert r.status_code == 409 and "code de formation" in r.json()["error"]["message"]

    r = client.get(f"{API}/catalog/programs", headers=IIT, params={"q": "formation de test"})
    assert [p["id"] for p in r.json()["items"]] == [pid]
    r = client.get(f"{API}/catalog/programs", headers=ADMIN, params={"school": "ISB", "q": "formation de test"})
    assert r.json()["total"] == 0

    # Désactivée = invisible côté public, toujours visible côté gestion.
    client.patch(f"{API}/catalog/programs/{pid}", headers=IIT, json={"is_active": False})
    assert client.get(f"{API}/programs/{pid}").status_code == 404
    r = client.get(f"{API}/catalog/programs", headers=IIT, params={"is_active": False, "q": "formation de test"})
    assert r.json()["total"] == 1
    client.patch(f"{API}/catalog/programs/{pid}", headers=IIT, json={"is_active": True})

    actions = {row[0] for row in db.execute(
        "SELECT action FROM audit_log WHERE entity_id = %s", (pid,)).fetchall()}
    assert {"catalog.program.create", "catalog.program.update"} <= actions


def test_specialties_subjects_and_curricula(client, iit_program):
    pid = iit_program["id"]
    sp = client.post(f"{API}/catalog/programs/{pid}/specialties", headers=IIT, json={"name": "IA appliquée"})
    assert sp.status_code == 201, sp.text
    sp = sp.json()
    assert client.post(f"{API}/catalog/programs/{pid}/specialties", headers=IIT,
                       json={"name": "IA appliquée"}).status_code == 409

    subj = client.post(f"{API}/catalog/subjects", headers=IIT, json={"code": code(), "name": "Réseaux de neurones"})
    assert subj.status_code == 201
    subj = subj.json()
    assert client.get(f"{API}/catalog/subjects", headers=IIT, params={"q": "reseaux de neur"}).json()["total"] >= 1

    cur = client.post(f"{API}/catalog/curricula", headers=IIT, json={
        "program_id": pid, "specialty_id": sp["id"], "academic_year": "2026-2027", "description": "V1"})
    assert cur.status_code == 201, cur.text
    cur = cur.json()
    assert client.post(f"{API}/catalog/curricula", headers=IIT, json={
        "program_id": pid, "academic_year": "2026-2028"}).status_code == 422  # années non consécutives

    r = client.post(f"{API}/catalog/curricula/{cur['id']}/subjects", headers=IIT, json={
        "subject_id": subj["id"], "study_year": 1, "semester": 2, "coefficient": 2.5, "credits": 4})
    assert r.status_code == 201 and r.json()["total_credits"] == 4
    item_id = r.json()["subjects"][0]["id"]
    r = client.patch(f"{API}/catalog/curricula/{cur['id']}/subjects/{item_id}", headers=IIT, json={"credits": 6})
    assert r.json()["subjects"][0]["credits"] == 6

    # Copier vers l'année suivante puis activer la copie : l'original reste actif (autre année).
    dup = client.post(f"{API}/catalog/curricula/{cur['id']}/duplicate", headers=IIT,
                      json={"academic_year": "2027-2028", "is_active": True})
    assert dup.status_code == 201 and dup.json()["subjects_count"] == 1
    # Nouvelle version la même année et active -> l'ancienne version est désactivée automatiquement.
    v2 = client.post(f"{API}/catalog/curricula/{cur['id']}/duplicate", headers=IIT,
                     json={"academic_year": "2026-2027", "is_active": True}).json()
    assert v2["version"] == 2
    assert client.get(f"{API}/catalog/curricula/{cur['id']}", headers=IIT).json()["is_active"] is False
    r = client.get(f"{API}/catalog/curricula", headers=IIT, params={"program_id": pid, "academic_year": "2026-2027",
                                                                     "is_active": True})
    assert [c["id"] for c in r.json()["items"]] == [v2["id"]]
    public = client.get(f"{API}/programs/{pid}/curriculum").json()
    assert {c["id"] for c in public["curricula"]} == {v2["id"], dup.json()["id"]}

    # Supprimer une matière encore utilisée -> 409 ; la spécialité utilisée par un programme -> 409.
    r = client.delete(f"{API}/catalog/subjects/{subj['id']}", headers=IIT)
    assert r.status_code == 409 and "programmes pédagogiques" in r.json()["error"]["message"]
    assert client.delete(f"{API}/catalog/specialties/{sp['id']}", headers=IIT).status_code == 409

    r = client.delete(f"{API}/catalog/curricula/{cur['id']}/subjects/{item_id}", headers=IIT)
    assert r.status_code == 200 and r.json()["subjects"] == []
    assert client.delete(f"{API}/catalog/curricula/{cur['id']}", headers=IIT).status_code == 204
    assert client.get(f"{API}/catalog/curricula/{cur['id']}", headers=IIT).status_code == 404


# --------------------------------------------------------------------------- tarifs
def test_tuition_publication_and_validity(client, iit_program):
    pid = iit_program["id"]
    fee = client.post(f"{API}/catalog/tuition-fees", headers=IIT, json={
        "program_id": pid, "academic_year": "2026-2027", "fee_type": "tuition", "amount": "7000.50",
        "valid_from": str(TODAY - timedelta(days=30)), "valid_until": str(TODAY + timedelta(days=200))})
    assert fee.status_code == 201, fee.text
    fee = fee.json()
    assert fee["status"] == "draft" and fee["visibility"] == "draft" and fee["is_currently_valid"] is False
    assert client.get(f"{API}/programs/{pid}/tuition").json()["fees"] == []          # brouillon invisible

    r = client.post(f"{API}/catalog/tuition-fees/{fee['id']}/status", headers=IIT, json={"status": "published"})
    assert r.status_code == 200 and r.json()["visibility"] == "visible" and r.json()["published_at"]
    public = client.get(f"{API}/programs/{pid}/tuition").json()["fees"]
    assert [f["amount"] for f in public] == [7000.5]
    assert client.get(f"{API}/programs", params={"q": iit_program["code"]}).json()["items"][0]["tuition_from"] == 7000.5

    # Même clé (formation, année, type, niveau) -> 409.
    r = client.post(f"{API}/catalog/tuition-fees", headers=IIT, json={
        "program_id": pid, "academic_year": "2026-2027", "fee_type": "tuition", "amount": 1})
    assert r.status_code == 409

    # Période dépassée -> plus visible, et republier est refusé.
    r = client.patch(f"{API}/catalog/tuition-fees/{fee['id']}", headers=IIT, json={
        "valid_from": str(TODAY - timedelta(days=60)), "valid_until": str(TODAY - timedelta(days=1))})
    assert r.json()["visibility"] == "expired"
    assert client.get(f"{API}/programs/{pid}/tuition").json()["fees"] == []
    client.post(f"{API}/catalog/tuition-fees/{fee['id']}/status", headers=IIT, json={"status": "draft"})
    r = client.post(f"{API}/catalog/tuition-fees/{fee['id']}/status", headers=IIT, json={"status": "published"})
    assert r.status_code == 422

    # Dates incohérentes -> 422 (validation ou contrainte SQL).
    assert client.patch(f"{API}/catalog/tuition-fees/{fee['id']}", headers=IIT, json={
        "valid_from": "2027-01-01", "valid_until": "2026-01-01"}).status_code == 422
    assert client.patch(f"{API}/catalog/tuition-fees/{fee['id']}", headers=IIT, json={
        "valid_until": "2000-01-01"}).status_code == 422

    # Archivé = lecture seule ; la clé est libérée pour un nouveau tarif.
    client.post(f"{API}/catalog/tuition-fees/{fee['id']}/status", headers=IIT, json={"status": "archived"})
    assert client.patch(f"{API}/catalog/tuition-fees/{fee['id']}", headers=IIT, json={"amount": 1}).status_code == 409
    r = client.post(f"{API}/catalog/tuition-fees", headers=IIT, json={
        "program_id": pid, "academic_year": "2026-2027", "fee_type": "tuition", "amount": 7200})
    assert r.status_code == 201
    r = client.get(f"{API}/catalog/tuition-fees", headers=IIT, params={"program_id": pid, "status": "archived"})
    assert r.json()["total"] == 1
    assert client.post(f"{API}/catalog/tuition-fees/{fee['id']}/status", headers=ISB,
                       json={"status": "draft"}).status_code == 403


def test_admission_requirements(client, iit_program):
    pid = iit_program["id"]
    r = client.post(f"{API}/catalog/admission-requirements", headers=IIT, json={
        "program_id": pid, "kind": "minimum_average", "description": "Moyenne minimale"})
    assert r.status_code == 422                                   # min_average manquant
    r = client.post(f"{API}/catalog/admission-requirements", headers=IIT, json={
        "program_id": pid, "kind": "minimum_average", "description": "Moyenne d'au moins 13/20",
        "min_average": 13, "academic_year": "2026-2027"})
    assert r.status_code == 201
    req = r.json()
    later = client.post(f"{API}/catalog/admission-requirements", headers=IIT, json={
        "program_id": pid, "kind": "document", "description": "Lettre de motivation",
        "valid_from": str(TODAY + timedelta(days=10))}).json()
    for item in (req, later):
        client.post(f"{API}/catalog/admission-requirements/{item['id']}/status", headers=IIT,
                    json={"status": "published"})

    public = client.get(f"{API}/programs/{pid}/admission", params={"academic_year": "2026-2027"}).json()
    assert [x["description"] for x in public["requirements"]] == ["Moyenne d'au moins 13/20"]
    assert public["requirements"][0]["min_average"] == 13
    r = client.get(f"{API}/catalog/admission-requirements", headers=IIT,
                   params={"program_id": pid, "visibility": "scheduled"})
    assert [x["id"] for x in r.json()["items"]] == [later["id"]]
    r = client.get(f"{API}/catalog/admission-requirements", headers=IIT,
                   params={"program_id": pid, "valid_on": str(TODAY + timedelta(days=11))})
    assert r.json()["total"] == 2
    assert client.post(f"{API}/catalog/admission-requirements", headers=IIT, json={
        "program_id": pid, "kind": "prior_diploma", "description": "Elle-même",
        "required_program_id": pid}).status_code == 422
    assert client.delete(f"{API}/catalog/admission-requirements/{later['id']}", headers=IIT).status_code == 204


def test_payment_plans(client, iit_program):
    pid = iit_program["id"]
    r = client.post(f"{API}/catalog/payment-plans", headers=IIT, json={
        "program_id": pid, "academic_year": "2026-2027", "name": "Deux tranches",
        "installments": [{"label": "1", "percentage": 60}, {"label": "2", "percentage": 30}]})
    assert r.status_code == 422 and "100" in str(r.json()["error"]["details"])
    r = client.post(f"{API}/catalog/payment-plans", headers=IIT, json={
        "program_id": pid, "academic_year": "2026-2027", "name": "Deux tranches",
        "payment_methods": ["bank_transfer", "check", "check"], "discount_percent": 0,
        "installments": [{"label": "Inscription", "percentage": 60, "due_description": "À l'inscription"},
                         {"label": "Solde", "percentage": 40, "due_date": "2027-02-01"}]})
    assert r.status_code == 201, r.text
    plan = r.json()
    assert plan["payment_methods"] == ["bank_transfer", "check"]
    assert [i["position"] for i in plan["installments"]] == [1, 2]

    r = client.patch(f"{API}/catalog/payment-plans/{plan['id']}", headers=IIT, json={
        "installments": [{"label": "Comptant", "amount": 7000}]})
    assert [i["label"] for i in r.json()["installments"]] == ["Comptant"]
    client.post(f"{API}/catalog/payment-plans/{plan['id']}/status", headers=IIT, json={"status": "published"})
    public = client.get(f"{API}/programs/{pid}/tuition").json()["payment_plans"]
    assert [p["name"] for p in public] == ["Deux tranches"] and public[0]["installments"][0]["amount"] == 7000
    assert client.get(f"{API}/catalog/payment-plans", headers=ADMIN,
                      params={"payment_method": "check", "program_id": pid}).json()["total"] == 1


def test_delete_program_cascades(client, db):
    r = client.post(f"{API}/catalog/programs", headers=ADMIN, json={
        "institution_id": str(db.execute("SELECT id FROM institution WHERE code = 'ISB'").fetchone()[0]),
        "code": code(), "name": "À supprimer", "cycle": "bachelor"})
    pid = r.json()["id"]
    client.post(f"{API}/catalog/tuition-fees", headers=ISB, json={
        "program_id": pid, "academic_year": "2026-2027", "fee_type": "registration", "amount": 10})
    assert client.delete(f"{API}/catalog/programs/{pid}", headers=IIT).status_code == 403
    assert client.delete(f"{API}/catalog/programs/{pid}", headers=ISB).status_code == 204
    assert client.get(f"{API}/catalog/programs/{pid}", headers=ADMIN).status_code == 404
    assert db.execute("SELECT count(*) FROM tuition_fee WHERE program_id = %s", (pid,)).fetchone()[0] == 0
