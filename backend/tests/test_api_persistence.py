"""1. Enregistrement et récupération des données.

Chaque donnée envoyée à l'API doit être enregistrée telle quelle dans PostgreSQL, puis renvoyée à
l'identique par les routes de lecture (gestion ET publique). Les tests vérifient les deux côtés :
la réponse HTTP et la ligne réellement écrite en base.
"""
from decimal import Decimal

import pytest

from tests.helpers import (API, CURRENT_YEAR, IIT, code, days, make_curriculum, make_fee, make_plan, make_program,
                           make_subject, publish)

pytestmark = pytest.mark.usefixtures("catalog_cleanup")


def test_formation_enregistree_et_relue_a_l_identique(client, db):
    """Tous les champs envoyés sont relus à l'identique (gestion, publique et base), accents et arabe compris."""
    sent = {"code": code(), "name": "Licence en gestion — الإجازة في التصرف", "cycle": "bachelor",
            "duration_years": 3, "degree": "Licence nationale", "capacity": 45, "teaching_languages": ["FR", "ar", "fr"],
            "description": "Économie, comptabilité « appliquée »", "career_outcomes": "Contrôleur de gestion"}
    created = make_program(client, **sent)

    for key in ("name", "cycle", "duration_years", "degree", "capacity", "description", "career_outcomes"):
        assert created[key] == sent[key], key
    assert created["teaching_languages"] == ["fr", "ar"]          # normalisées : minuscules, sans doublon
    assert created["school"] == "IIT" and created["level"] == "Licence"

    managed = client.get(f"{API}/catalog/programs/{created['id']}", headers=IIT).json()
    public = client.get(f"{API}/programs/{created['id']}").json()
    for key in ("name", "code", "description", "capacity", "teaching_languages"):
        assert managed[key] == created[key] == public[key], key

    row = db.execute("""SELECT p.code, p.name, p.capacity, p.teaching_languages, i.code
                          FROM program p JOIN institution i ON i.id = p.institution_id WHERE p.id = %s""",
                     (created["id"],)).fetchone()
    assert row == (sent["code"], sent["name"], 45, ["fr", "ar"], "IIT")


def test_code_normalise_en_majuscules(client, db):
    created = make_program(client, code="t-minus-" + code()[2:].lower())
    assert created["code"] == created["code"].upper()
    assert db.execute("SELECT code FROM program WHERE id = %s", (created["id"],)).fetchone()[0] == created["code"]


def test_modification_partielle_ne_touche_que_les_champs_envoyes(client, db):
    p = make_program(client, capacity=10, degree="Licence", description="Avant")
    before = db.execute("SELECT created_at, updated_at FROM program WHERE id = %s", (p["id"],)).fetchone()

    r = client.patch(f"{API}/catalog/programs/{p['id']}", headers=IIT, json={"capacity": 99})
    assert r.status_code == 200
    after = r.json()
    assert after["capacity"] == 99
    assert (after["degree"], after["description"], after["name"]) == ("Licence", "Avant", p["name"])

    created_at, updated_at = db.execute("SELECT created_at, updated_at FROM program WHERE id = %s",
                                        (p["id"],)).fetchone()
    assert created_at == before[0] and updated_at > before[1]   # trigger updated_at du schéma


def test_montants_et_dates_exacts(client, db):
    p = make_program(client)
    fee = make_fee(client, p["id"], amount="7000.55", valid_from="2026-09-01", valid_until="2027-08-31",
                   description="Frais annuels")
    assert fee["amount"] == 7000.55 and fee["currency"] == "TND"
    assert (fee["valid_from"], fee["valid_until"]) == ("2026-09-01", "2027-08-31")
    assert fee["status"] == "draft"                                  # toujours créé en brouillon
    row = db.execute("SELECT amount, currency, valid_from::text, valid_until::text, status FROM tuition_fee "
                     "WHERE id = %s", (fee["id"],)).fetchone()
    assert row == (Decimal("7000.55"), "TND", "2026-09-01", "2027-08-31", "draft")


def test_modalite_de_paiement_et_echeances(client, db):
    p = make_program(client)
    plan = make_plan(client, p["id"], name="Trois tranches", payment_methods=["check", "cash"], discount_percent=2.5,
                     installments=[{"label": "Inscription", "percentage": 50, "due_description": "À l'inscription"},
                                   {"label": "Janvier", "percentage": 25, "due_date": "2027-01-15"},
                                   {"label": "Avril", "percentage": 25, "due_date": "2027-04-15"}])
    assert [i["position"] for i in plan["installments"]] == [1, 2, 3]
    assert [i["label"] for i in plan["installments"]] == ["Inscription", "Janvier", "Avril"]
    assert plan["installments"][1]["due_date"] == "2027-01-15" and plan["discount_percent"] == 2.5
    rows = db.execute("SELECT position, label, percentage FROM payment_installment WHERE payment_plan_id = %s "
                      "ORDER BY position", (plan["id"],)).fetchall()
    assert rows == [(1, "Inscription", Decimal("50.00")), (2, "Janvier", Decimal("25.00")), (3, "Avril", Decimal("25.00"))]

    # PATCH avec échéances = remplacement complet (anciennes lignes supprimées en base)
    r = client.patch(f"{API}/catalog/payment-plans/{plan['id']}", headers=IIT,
                     json={"installments": [{"label": "Comptant", "amount": 6000}]})
    assert [i["label"] for i in r.json()["installments"]] == ["Comptant"]
    assert db.execute("SELECT count(*) FROM payment_installment WHERE payment_plan_id = %s",
                      (plan["id"],)).fetchone()[0] == 1
    # PATCH sans échéances = elles ne bougent pas
    r = client.patch(f"{API}/catalog/payment-plans/{plan['id']}", headers=IIT, json={"conditions": "Pénalités"})
    assert r.json()["conditions"] == "Pénalités" and len(r.json()["installments"]) == 1


def test_programme_pedagogique_et_matieres(client, db):
    p = make_program(client)
    s1, s2 = make_subject(client), make_subject(client)
    cur = make_curriculum(client, p["id"])
    for s, sem, cr in ((s1, 1, 5), (s2, 2, 4)):
        r = client.post(f"{API}/catalog/curricula/{cur['id']}/subjects", headers=IIT,
                        json={"subject_id": s["id"], "study_year": 1, "semester": sem, "coefficient": 2.5, "credits": cr})
        assert r.status_code == 201
    detail = client.get(f"{API}/catalog/curricula/{cur['id']}", headers=IIT).json()
    assert [x["subject_code"] for x in detail["subjects"]] == [s1["code"], s2["code"]]
    assert detail["total_credits"] == 9 and detail["subjects_count"] == 2
    assert detail["subjects"][0]["coefficient"] == 2.5
    assert db.execute("SELECT sum(credits) FROM curriculum_subject WHERE curriculum_id = %s",
                      (cur["id"],)).fetchone()[0] == 9
    assert client.get(f"{API}/catalog/subjects/{s1['id']}", headers=IIT).json()["usage_count"] == 1


def test_chaque_ecriture_est_tracee_dans_audit_log(client, db):
    headers = {**IIT, "X-Request-ID": "test-audit-" + code()}
    p = make_program(client, headers=headers)
    fee = make_fee(client, p["id"], headers=headers)
    client.patch(f"{API}/catalog/tuition-fees/{fee['id']}", headers=headers, json={"amount": 5100})
    publish(client, "tuition-fees", fee["id"], headers=headers)
    client.delete(f"{API}/catalog/tuition-fees/{fee['id']}", headers=headers)

    rows = db.execute("SELECT action, actor_label FROM audit_log WHERE request_id = %s ORDER BY id",
                      (headers["X-Request-ID"],)).fetchall()
    assert [a for a, _ in rows] == ["catalog.program.create", "catalog.tuition_fee.create",
                                    "catalog.tuition_fee.update", "catalog.tuition_fee.published",
                                    "catalog.tuition_fee.delete"]
    assert {label for _, label in rows} == {"iit_manager"}


def test_pagination_tri_et_recherche(client):
    token = code("T")[2:]
    for name in ("Alpha", "Bravo", "Charlie"):
        make_program(client, name=f"{name} {token}")
    r = client.get(f"{API}/catalog/programs", headers=IIT, params={"q": token, "size": 2, "page": 1, "sort": "name"})
    assert r.json()["total"] == 3 and [x["name"][:5] for x in r.json()["items"]] == ["Alpha", "Bravo"]
    r = client.get(f"{API}/catalog/programs", headers=IIT, params={"q": token, "size": 2, "page": 2, "sort": "name"})
    assert [x["name"][:7] for x in r.json()["items"]] == ["Charlie"]
    r = client.get(f"{API}/catalog/programs", headers=IIT, params={"q": token, "sort": "-name"})
    assert [x["name"][:5] for x in r.json()["items"]] == ["Charl", "Bravo", "Alpha"]
    r = client.get(f"{API}/catalog/programs", headers=IIT, params={"q": token, "page": 99})
    assert r.json()["items"] == [] and r.json()["total"] == 3


def test_recherche_insensible_aux_accents_et_a_la_casse(client):
    s = make_subject(client, name="Économétrie appliquée")
    for q in ("econometrie", "ÉCONOMÉTRIE", "metrie APPLI"):
        found = client.get(f"{API}/catalog/subjects", headers=IIT, params={"q": q}).json()["items"]
        assert s["id"] in [x["id"] for x in found], q


def test_recherche_resiste_a_l_injection_sql(client, db):
    for q in ("'; DROP TABLE program; --", "%", "_", "\\", "' OR '1'='1"):
        r = client.get(f"{API}/programs", params={"q": q})
        assert r.status_code == 200, q
    assert db.execute("SELECT count(*) FROM program WHERE code IN ('PREPA-INT','ING-INFO','LIC-GEST','MP-FIN')"
                      ).fetchone()[0] == 4


def test_lecture_publique_apres_publication(client):
    p = make_program(client)
    fee = make_fee(client, p["id"], amount="4200", valid_from=days(-1), valid_until=days(30))
    assert client.get(f"{API}/programs/{p['id']}/tuition").json()["fees"] == []
    publish(client, "tuition-fees", fee["id"])
    fees = client.get(f"{API}/programs/{p['id']}/tuition", params={"academic_year": CURRENT_YEAR}).json()["fees"]
    assert [(f["id"], f["amount"]) for f in fees] == [(fee["id"], 4200.0)]
    assert set(fees[0]) == {"id", "academic_year", "study_year", "fee_type", "amount", "currency", "description",
                            "valid_from", "valid_until"}      # aucun champ interne (statut, auteur) côté public
