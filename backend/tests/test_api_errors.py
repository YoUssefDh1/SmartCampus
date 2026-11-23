"""5. Gestion des erreurs.

Toutes les erreurs ont le même format (code, message, details, request_id) ; les messages sont
compréhensibles et ne divulguent rien d'interne (SQL, noms de tables) ; une écriture refusée
n'écrit RIEN (transaction annulée) ; base indisponible -> 503 clair, sans bloquer le reste.
"""
import uuid

import pytest
from psycopg_pool import PoolTimeout

from app.db import session
from tests.helpers import (API, CURRENT_YEAR, IIT, assert_error, code, days, make_fee, make_plan, make_program,
                           make_requirement, make_specialty, make_subject, publish)

pytestmark = pytest.mark.usefixtures("catalog_cleanup")
MISSING = str(uuid.uuid4())
LEAKS = ("violates", "constraint \"", "SELECT", "INSERT", "psycopg", "Traceback", "DETAIL")


def no_leak(response) -> None:
    for word in LEAKS:
        assert word not in response.text, f"fuite « {word} » : {response.text}"


def test_identifiant_de_requete_renvoye(client):
    r = client.get(f"{API}/catalog/programs", headers={"X-Request-ID": "trace-1234"})
    assert assert_error(r, 401, "UNAUTHORIZED")["request_id"] == "trace-1234"
    r = client.get(f"{API}/programs")
    assert r.headers["X-Request-ID"].startswith("req_")                       # généré si absent


NOT_FOUND_CASES = [
    (f"/catalog/programs/{MISSING}", "Formation introuvable."),
    (f"/catalog/specialties/{MISSING}", "Spécialité introuvable."),
    (f"/catalog/subjects/{MISSING}", "Matière introuvable."),
    (f"/catalog/curricula/{MISSING}", "Programme pédagogique introuvable."),
    (f"/catalog/admission-requirements/{MISSING}", "Condition d'admission introuvable."),
    (f"/catalog/tuition-fees/{MISSING}", "Tarif introuvable."),
    (f"/catalog/payment-plans/{MISSING}", "Modalité de paiement introuvable."),
    (f"/programs/{MISSING}", "Formation introuvable."),
]


@pytest.mark.parametrize("path,message", NOT_FOUND_CASES,
                         ids=["formation", "specialite", "matiere", "programme-pedagogique", "condition-admission",
                              "tarif", "modalite-paiement", "fiche-publique"])
def test_404_message_precis(client, path, message):
    headers = IIT if path.startswith("/catalog") else {}
    assert assert_error(client.get(API + path, headers=headers), 404, "NOT_FOUND")["message"] == message


def test_404_sur_modification_et_suppression(client):
    for method in ("PATCH", "DELETE"):
        r = client.request(method, f"{API}/catalog/tuition-fees/{MISSING}", headers=IIT,
                           json={"amount": 1} if method == "PATCH" else None)
        assert_error(r, 404, "NOT_FOUND")
    assert_error(client.post(f"{API}/catalog/tuition-fees/{MISSING}/status", headers=IIT,
                             json={"status": "published"}), 404, "NOT_FOUND")


def test_suppression_deux_fois(client):
    s = make_subject(client)
    first = client.delete(f"{API}/catalog/subjects/{s['id']}", headers=IIT)
    assert first.status_code == 204 and first.content == b""          # 204 : corps vide
    assert_error(client.delete(f"{API}/catalog/subjects/{s['id']}", headers=IIT), 404, "NOT_FOUND")


def test_methode_non_autorisee(client):
    assert_error(client.put(f"{API}/catalog/programs/{MISSING}", headers=IIT, json={}), 405, "METHOD_NOT_ALLOWED")
    assert_error(client.delete(f"{API}/programs/{MISSING}"), 405, "METHOD_NOT_ALLOWED")


@pytest.fixture(scope="module")
def prog(client):
    return make_program(client)


DUPLICATES = {
    "formation-meme-code": lambda c, p: ("/catalog/programs", {"code": p["code"], "name": "Copie", "cycle": "other"},
                                           "code de formation"),
    "specialite-meme-nom": lambda c, p: (f"/catalog/programs/{p['id']}/specialties",
                                           {"name": make_specialty(c, p["id"])["name"]}, "spécialité existe déjà"),
    "matiere-meme-code-autre-casse": lambda c, p: ("/catalog/subjects",
                                                      {"code": make_subject(c)["code"].lower(), "name": "Copie"},
                                                      "code de matière"),
    "tarif-meme-cle": lambda c, p: ("/catalog/tuition-fees",
                                      {"program_id": p["id"], "academic_year": make_fee(
                                          c, p["id"], academic_year="2040-2041")["academic_year"],
                                       "fee_type": "tuition", "amount": 2}, "tarif de ce type"),
    "modalite-meme-nom-autre-casse": lambda c, p: ("/catalog/payment-plans",
                                                      {"program_id": p["id"], "academic_year": CURRENT_YEAR,
                                                       "name": make_plan(c, p["id"])["name"].upper(),
                                                       "installments": [{"label": "U", "percentage": 100}]},
                                                      "porte déjà ce nom"),
}


@pytest.mark.parametrize("case", list(DUPLICATES))
def test_doublon_409_message_clair(client, prog, case):
    path, body, expected = DUPLICATES[case](client, prog)
    r = client.post(API + path, headers=IIT, json=body)
    err = assert_error(r, 409, "CONFLICT")
    assert expected in err["message"], err
    no_leak(r)


@pytest.mark.parametrize("resource,maker", [("tuition-fees", make_fee), ("admission-requirements", make_requirement),
                                            ("payment-plans", make_plan)],
                         ids=["tarif", "condition-admission", "modalite-paiement"])
def test_element_archive_non_modifiable(client, prog, resource, maker):
    over = {"academic_year": "2041-2042"} if resource == "tuition-fees" else {}
    item = maker(client, prog["id"], **over)
    client.post(f"{API}/catalog/{resource}/{item['id']}/status", headers=IIT, json={"status": "archived"})
    err = assert_error(client.patch(f"{API}/catalog/{resource}/{item['id']}", headers=IIT,
                                    json={"description": "Interdit"}), 409, "CONFLICT")
    assert "archiv" in err["message"]
    # Restaurer en brouillon rend la modification possible
    client.post(f"{API}/catalog/{resource}/{item['id']}/status", headers=IIT, json={"status": "draft"})
    assert client.patch(f"{API}/catalog/{resource}/{item['id']}", headers=IIT,
                        json={"description": "Autorisé"}).status_code == 200


def test_publier_une_periode_terminee_refuse(client, prog):
    fee = make_fee(client, prog["id"], academic_year="2042-2043", valid_from=days(-30), valid_until=days(-1))
    err = assert_error(client.post(f"{API}/catalog/tuition-fees/{fee['id']}/status", headers=IIT,
                                   json={"status": "published"}), 422, "VALIDATION_ERROR")
    assert "période de validité est déjà terminée" in err["message"]


def test_changer_vers_le_meme_statut_ne_fait_rien(client, prog, db):
    fee = make_fee(client, prog["id"], academic_year="2043-2044")
    first = publish(client, "tuition-fees", fee["id"])
    before = db.execute("SELECT count(*) FROM audit_log WHERE entity_id = %s", (fee["id"],)).fetchone()[0]
    again = publish(client, "tuition-fees", fee["id"])
    assert again["published_at"] == first["published_at"]
    assert db.execute("SELECT count(*) FROM audit_log WHERE entity_id = %s", (fee["id"],)).fetchone()[0] == before


def test_ecriture_refusee_n_ecrit_rien(client, prog, db):
    """Tout ou rien : un PATCH en conflit n'applique AUCUN de ses champs ; une création refusée ne laisse rien."""
    other = make_program(client)
    r = client.patch(f"{API}/catalog/programs/{other['id']}", headers=IIT, json={"code": prog["code"], "capacity": 999})
    assert_error(r, 409, "CONFLICT")
    assert db.execute("SELECT capacity, code FROM program WHERE id = %s", (other["id"],)).fetchone() == (
        None, other["code"])

    plan = make_plan(client, prog["id"])
    count = lambda: db.execute("SELECT count(*) FROM payment_installment").fetchone()[0]  # noqa: E731
    audits = lambda: db.execute("SELECT count(*) FROM audit_log").fetchone()[0]  # noqa: E731
    before = count(), audits()
    r = client.post(f"{API}/catalog/payment-plans", headers=IIT, json={
        "program_id": prog["id"], "academic_year": CURRENT_YEAR, "name": plan["name"],
        "installments": [{"label": "A", "percentage": 50}, {"label": "B", "percentage": 50}]})
    assert_error(r, 409, "CONFLICT")
    assert (count(), audits()) == before                       # ni échéances orphelines, ni trace d'audit


def test_erreurs_de_base_sans_fuite_technique(client, prog):
    for r in (
        client.post(f"{API}/catalog/curricula", headers=IIT, json={"program_id": prog["id"], "academic_year":
                                                                   CURRENT_YEAR, "specialty_id": MISSING}),
        client.post(f"{API}/catalog/programs", headers=IIT, json={"code": prog["code"], "name": "X Y", "cycle": "other"}),
        client.patch(f"{API}/catalog/tuition-fees/{make_fee(client, prog['id'], academic_year='2044-2045')['id']}",
                     headers=IIT, json={"valid_from": "2045-01-01", "valid_until": "2044-01-01"}),
    ):
        assert r.status_code in (409, 422) and r.json()["error"]["message"]
        no_leak(r)


def test_base_indisponible_503(client, monkeypatch):
    class DownPool:
        def connection(self):
            raise PoolTimeout("couldn't get a connection after 5.00 sec")

    monkeypatch.setattr(session, "get_pool", lambda: DownPool())
    for path, headers in (("/programs", {}), ("/catalog/programs", IIT)):
        r = client.get(API + path, headers=headers)
        err = assert_error(r, 503, "DATABASE_UNAVAILABLE")
        assert "PostgreSQL" in err["message"]
        no_leak(r)
    assert client.get(f"{API}/health").status_code == 200       # le reste de l'API continue de répondre
