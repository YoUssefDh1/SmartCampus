"""3. Relations entre les données.

Références vers des éléments inexistants ou incohérents refusées ; compteurs dérivés à jour ;
suppression en cascade de ce qui appartient à une formation ; suppression refusée (409) quand
un élément est encore utilisé ailleurs (ON DELETE RESTRICT du schéma).
"""
import uuid

import pytest

from tests.helpers import (ADMIN, API, CURRENT_YEAR, IIT, assert_error, code, make_curriculum, make_fee, make_plan,
                           make_program, make_requirement, make_specialty, make_subject, publish, seed_program)

pytestmark = pytest.mark.usefixtures("catalog_cleanup")
MISSING = str(uuid.uuid4())


def test_reference_vers_une_formation_inexistante(client):
    assert_error(client.post(f"{API}/catalog/programs/{MISSING}/specialties", headers=IIT, json={"name": "X Y"}),
                 404, "NOT_FOUND")
    for url, body in [
        ("tuition-fees", {"academic_year": CURRENT_YEAR, "fee_type": "tuition", "amount": 1}),
        ("admission-requirements", {"kind": "document", "description": "Pièce"}),
        ("payment-plans", {"academic_year": CURRENT_YEAR, "name": "Plan P", "installments": [{"label": "U", "amount": 1}]}),
        ("curricula", {"academic_year": CURRENT_YEAR}),
    ]:
        err = assert_error(client.post(f"{API}/catalog/{url}", headers=IIT, json={"program_id": MISSING, **body}),
                           404, "NOT_FOUND")
        assert err["message"] == "Formation introuvable.", url


def test_reference_vers_ecole_matiere_ou_formation_exigee_inexistante(client):
    err = assert_error(client.post(f"{API}/catalog/programs", headers=ADMIN, json={
        "institution_id": MISSING, "code": code(), "name": "Sans école", "cycle": "other"}), 422, "VALIDATION_ERROR")
    assert err["message"] == "École introuvable."
    p = make_program(client)
    cur = make_curriculum(client, p["id"])
    err = assert_error(client.post(f"{API}/catalog/curricula/{cur['id']}/subjects", headers=IIT, json={
        "subject_id": MISSING, "study_year": 1, "semester": 1}), 422, "VALIDATION_ERROR")
    assert err["message"] == "Matière introuvable."
    err = assert_error(client.post(f"{API}/catalog/admission-requirements", headers=IIT, json={
        "program_id": p["id"], "kind": "prior_diploma", "description": "Diplôme", "required_program_id": MISSING}),
        422, "VALIDATION_ERROR")
    assert err["message"] == "La formation exigée n'existe pas."


def test_specialite_d_une_autre_formation_refusee(client):
    a, b = make_program(client), make_program(client)
    sp_b = make_specialty(client, b["id"])
    err = assert_error(client.post(f"{API}/catalog/curricula", headers=IIT, json={
        "program_id": a["id"], "specialty_id": sp_b["id"], "academic_year": CURRENT_YEAR}), 422, "VALIDATION_ERROR")
    assert "n'appartient pas" in err["message"]
    cur = make_curriculum(client, a["id"])
    assert_error(client.patch(f"{API}/catalog/curricula/{cur['id']}", headers=IIT,
                              json={"specialty_id": sp_b["id"]}), 422, "VALIDATION_ERROR")


def test_une_formation_ne_peut_pas_s_exiger_elle_meme(client):
    p = make_program(client)
    assert_error(client.post(f"{API}/catalog/admission-requirements", headers=IIT, json={
        "program_id": p["id"], "kind": "prior_diploma", "description": "Elle-même", "required_program_id": p["id"]}),
        422, "VALIDATION_ERROR")
    req = make_requirement(client, p["id"])
    assert_error(client.patch(f"{API}/catalog/admission-requirements/{req['id']}", headers=IIT,
                              json={"required_program_id": p["id"]}), 422, "VALIDATION_ERROR")


def test_element_d_un_autre_programme_introuvable(client):
    p = make_program(client)
    s = make_subject(client)
    c1, c2 = make_curriculum(client, p["id"]), make_curriculum(client, p["id"], version=2, is_active=False)
    item = client.post(f"{API}/catalog/curricula/{c1['id']}/subjects", headers=IIT,
                       json={"subject_id": s["id"], "study_year": 1, "semester": 1}).json()["subjects"][0]
    assert_error(client.patch(f"{API}/catalog/curricula/{c2['id']}/subjects/{item['id']}", headers=IIT,
                              json={"credits": 3}), 404, "NOT_FOUND")
    assert_error(client.delete(f"{API}/catalog/curricula/{c2['id']}/subjects/{item['id']}", headers=IIT),
                 404, "NOT_FOUND")


def test_compteurs_derives_a_jour(client):
    p = make_program(client)
    sp = make_specialty(client, p["id"])
    s = make_subject(client)
    assert client.get(f"{API}/catalog/programs/{p['id']}", headers=IIT).json()["specialties_count"] == 1
    cur = make_curriculum(client, p["id"], specialty_id=sp["id"])
    assert client.get(f"{API}/catalog/specialties/{sp['id']}", headers=IIT).json()["curricula_count"] == 1
    detail = client.post(f"{API}/catalog/curricula/{cur['id']}/subjects", headers=IIT,
                         json={"subject_id": s["id"], "study_year": 1, "semester": 1, "credits": 6}).json()
    assert detail["total_credits"] == 6
    assert client.get(f"{API}/catalog/subjects/{s['id']}", headers=IIT).json()["usage_count"] == 1
    client.delete(f"{API}/catalog/curricula/{cur['id']}/subjects/{detail['subjects'][0]['id']}", headers=IIT)
    assert client.get(f"{API}/catalog/subjects/{s['id']}", headers=IIT).json()["usage_count"] == 0


def test_une_seule_version_active_et_versions_uniques(client):
    p = make_program(client)
    v1 = make_curriculum(client, p["id"])
    v2 = make_curriculum(client, p["id"], version=2)                     # activer v2 désactive v1
    assert client.get(f"{API}/catalog/curricula/{v1['id']}", headers=IIT).json()["is_active"] is False
    client.patch(f"{API}/catalog/curricula/{v1['id']}", headers=IIT, json={"is_active": True})
    assert client.get(f"{API}/catalog/curricula/{v2['id']}", headers=IIT).json()["is_active"] is False
    err = assert_error(client.post(f"{API}/catalog/curricula", headers=IIT, json={
        "program_id": p["id"], "academic_year": CURRENT_YEAR, "version": 2}), 409, "CONFLICT")
    assert "version existe déjà" in err["message"]


def test_suppression_en_cascade_de_tout_ce_qui_appartient_a_la_formation(client, db):
    p = make_program(client)
    sp = make_specialty(client, p["id"])
    s = make_subject(client)
    cur = make_curriculum(client, p["id"], specialty_id=sp["id"])
    client.post(f"{API}/catalog/curricula/{cur['id']}/subjects", headers=IIT,
                json={"subject_id": s["id"], "study_year": 1, "semester": 1})
    make_fee(client, p["id"]), make_requirement(client, p["id"]), make_plan(client, p["id"])

    assert client.delete(f"{API}/catalog/programs/{p['id']}", headers=IIT).status_code == 204
    counts = db.execute(
        """SELECT (SELECT count(*) FROM specialty WHERE program_id = %(p)s),
                  (SELECT count(*) FROM curriculum WHERE program_id = %(p)s),
                  (SELECT count(*) FROM curriculum_subject WHERE curriculum_id = %(c)s),
                  (SELECT count(*) FROM tuition_fee WHERE program_id = %(p)s),
                  (SELECT count(*) FROM admission_requirement WHERE program_id = %(p)s),
                  (SELECT count(*) FROM payment_plan WHERE program_id = %(p)s),
                  (SELECT count(*) FROM payment_installment pi
                     WHERE NOT EXISTS (SELECT 1 FROM payment_plan pp WHERE pp.id = pi.payment_plan_id))""",
        {"p": p["id"], "c": cur["id"]}).fetchone()
    assert counts == (0, 0, 0, 0, 0, 0, 0)
    # La matière est un référentiel partagé : elle survit à la formation.
    assert client.get(f"{API}/catalog/subjects/{s['id']}", headers=IIT).status_code == 200


def test_suppression_refusee_si_encore_utilise(client, db):
    p = make_program(client)
    sp = make_specialty(client, p["id"])
    s = make_subject(client)
    cur = make_curriculum(client, p["id"], specialty_id=sp["id"])
    client.post(f"{API}/catalog/curricula/{cur['id']}/subjects", headers=IIT,
                json={"subject_id": s["id"], "study_year": 1, "semester": 1})

    err = assert_error(client.delete(f"{API}/catalog/subjects/{s['id']}", headers=IIT), 409, "CONFLICT")
    assert "programmes pédagogiques" in err["message"]
    err = assert_error(client.delete(f"{API}/catalog/specialties/{sp['id']}", headers=IIT), 409, "CONFLICT")
    assert "programmes pédagogiques" in err["message"]
    # Rien n'a été supprimé
    assert db.execute("SELECT count(*) FROM subject WHERE id = %s", (s["id"],)).fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM specialty WHERE id = %s", (sp["id"],)).fetchone()[0] == 1


def test_formation_exigee_par_une_autre_ne_peut_pas_etre_supprimee(client, db):
    """Seed : ING-INFO exige PREPA-INT (prérequis) -> supprimer PREPA-INT est refusé, et rien ne bouge."""
    prepa = seed_program(db, "PREPA-INT")
    before = db.execute("SELECT count(*) FROM specialty").fetchone()[0], db.execute(
        "SELECT count(*) FROM tuition_fee WHERE program_id = %s", (prepa,)).fetchone()[0]
    err = assert_error(client.delete(f"{API}/catalog/programs/{prepa}", headers=ADMIN), 409, "CONFLICT")
    assert "conditions d'admission d'autres formations" in err["message"]
    after = db.execute("SELECT count(*) FROM specialty").fetchone()[0], db.execute(
        "SELECT count(*) FROM tuition_fee WHERE program_id = %s", (prepa,)).fetchone()[0]
    assert before == after                           # transaction annulée : aucune cascade partielle


def test_formation_avec_preinscriptions_ne_peut_pas_etre_supprimee(client, db):
    p = make_program(client)
    user_id = db.execute(
        """INSERT INTO app_user (role, first_name, last_name, email, password_hash)
           VALUES ('candidate', 'Test', 'Candidat', %s, 'x') RETURNING id""",
        (f"test-{uuid.uuid4().hex[:8]}@smartcampus.test",)).fetchone()[0]
    try:
        consent_id = db.execute("INSERT INTO consent (candidate_id, purpose, policy_version) "
                                "VALUES (%s, 'data_processing', 'v1') RETURNING id", (user_id,)).fetchone()[0]
        db.execute("""INSERT INTO preregistration (candidate_id, program_id, academic_year, phone, school_level,
                                                   consent_id)
                      VALUES (%s, %s, %s, '+21620000000', 'Bac', %s)""", (user_id, p["id"], CURRENT_YEAR, consent_id))
        err = assert_error(client.delete(f"{API}/catalog/programs/{p['id']}", headers=IIT), 409, "CONFLICT")
        assert "préinscriptions" in err["message"]
        # La bonne réponse métier : désactiver plutôt que supprimer.
        r = client.patch(f"{API}/catalog/programs/{p['id']}", headers=IIT, json={"is_active": False})
        assert r.status_code == 200 and r.json()["is_active"] is False
    finally:
        db.execute("DELETE FROM app_user WHERE id = %s", (user_id,))   # cascade : profil, consentement, dossier


def test_formation_inactive_masque_ses_informations_publiees(client, db):
    p = make_program(client)
    fee = make_fee(client, p["id"])
    publish(client, "tuition-fees", fee["id"])
    assert client.get(f"{API}/programs/{p['id']}/tuition").json()["fees"]
    client.patch(f"{API}/catalog/programs/{p['id']}", headers=IIT, json={"is_active": False})
    assert_error(client.get(f"{API}/programs/{p['id']}/tuition"), 404, "NOT_FOUND")
    assert db.execute("SELECT count(*) FROM v_official_tuition_fee WHERE id = %s", (fee["id"],)).fetchone()[0] == 0
    assert p["id"] not in [x["id"] for x in client.get(f"{API}/programs", params={"size": 100}).json()["items"]]


def test_la_fiche_publique_ne_contient_que_les_donnees_de_la_formation(client, db):
    ing = seed_program(db, "ING-INFO")
    detail = client.get(f"{API}/programs/{ing}").json()
    official = {str(r[0]) for r in db.execute(
        "SELECT id FROM v_official_tuition_fee WHERE program_id = %s", (ing,)).fetchall()}
    assert {f["id"] for f in detail["tuition_fees"]} == official
    names = {s["name"] for s in detail["specialties"]}
    assert names == {r[0] for r in db.execute(
        "SELECT name FROM specialty WHERE program_id = %s AND is_active", (ing,)).fetchall()}
