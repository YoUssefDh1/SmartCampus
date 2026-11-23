"""2. Champs obligatoires et formats.

Pour chaque ressource : un champ obligatoire absent, vide ou mal formé est refusé (422
VALIDATION_ERROR, champ fautif cité dans `details`) et RIEN n'est écrit en base.
"""
import pytest

from tests.helpers import (API, CURRENT_YEAR, IIT, assert_error, code, make_curriculum, make_fee, make_program,
                           make_subject)

pytestmark = pytest.mark.usefixtures("catalog_cleanup")


@pytest.fixture(scope="module")
def ctx(client):
    program = make_program(client)
    return {"program": program, "subject": make_subject(client), "curriculum": make_curriculum(client, program["id"]),
            "fee": make_fee(client, program["id"])}


def valid_payloads(ctx) -> dict[str, tuple[str, dict]]:
    pid = ctx["program"]["id"]
    return {
        "programs": (f"{API}/catalog/programs", {"code": code(), "name": "Formation", "cycle": "master"}),
        "specialties": (f"{API}/catalog/programs/{pid}/specialties", {"name": "Spécialité"}),
        "subjects": (f"{API}/catalog/subjects", {"code": code(), "name": "Matière"}),
        "curricula": (f"{API}/catalog/curricula", {"program_id": pid, "academic_year": "2030-2031"}),
        "curriculum-subjects": (f"{API}/catalog/curricula/{ctx['curriculum']['id']}/subjects",
                                {"subject_id": ctx["subject"]["id"], "study_year": 1, "semester": 1}),
        "admission-requirements": (f"{API}/catalog/admission-requirements",
                                   {"program_id": pid, "kind": "document", "description": "Pièce d'identité"}),
        "tuition-fees": (f"{API}/catalog/tuition-fees",
                         {"program_id": pid, "academic_year": "2031-2032", "fee_type": "other", "amount": 10}),
        "payment-plans": (f"{API}/catalog/payment-plans",
                          {"program_id": pid, "academic_year": CURRENT_YEAR, "name": "Plan " + code(),
                           "installments": [{"label": "Unique", "percentage": 100}]}),
    }


REQUIRED = [
    ("programs", "code"), ("programs", "name"), ("programs", "cycle"),
    ("specialties", "name"),
    ("subjects", "code"), ("subjects", "name"),
    ("curricula", "program_id"), ("curricula", "academic_year"),
    ("curriculum-subjects", "subject_id"), ("curriculum-subjects", "study_year"), ("curriculum-subjects", "semester"),
    ("admission-requirements", "program_id"), ("admission-requirements", "kind"),
    ("admission-requirements", "description"),
    ("tuition-fees", "program_id"), ("tuition-fees", "academic_year"), ("tuition-fees", "fee_type"),
    ("tuition-fees", "amount"),
    ("payment-plans", "program_id"), ("payment-plans", "academic_year"), ("payment-plans", "name"),
    ("payment-plans", "installments"),
]


def test_les_payloads_de_reference_sont_acceptes(client, ctx):
    """Témoin : sans cette preuve, un 422 plus bas pourrait venir d'un autre champ."""
    for name, (url, body) in valid_payloads(ctx).items():
        r = client.post(url, headers=IIT, json=body)
        assert r.status_code == 201, (name, r.text)


@pytest.mark.parametrize("resource,field", REQUIRED, ids=[f"{r}.{f}" for r, f in REQUIRED])
def test_champ_obligatoire_absent(client, ctx, db, resource, field):
    url, body = valid_payloads(ctx)[resource]
    body.pop(field)
    before = db.execute("SELECT count(*) FROM audit_log").fetchone()[0]
    err = assert_error(client.post(url, headers=IIT, json=body), 422, "VALIDATION_ERROR")
    assert any(d["field"].endswith(field) for d in err["details"]), err["details"]
    assert db.execute("SELECT count(*) FROM audit_log").fetchone()[0] == before     # rien n'a été écrit


INVALID = [
    ("programs", "name", ""), ("programs", "name", "   "), ("programs", "name", "A"), ("programs", "name", "x" * 201),
    ("programs", "code", "ING INFO"), ("programs", "code", "x" * 31), ("programs", "cycle", "doctorat"),
    ("programs", "duration_years", 0), ("programs", "capacity", -1), ("programs", "teaching_languages", ["x"]),
    ("programs", "teaching_languages", "fr"),
    ("specialties", "name", ""),
    ("subjects", "code", "a b"),
    ("curricula", "academic_year", "2026-2028"), ("curricula", "academic_year", "26-27"),
    ("curricula", "version", 0), ("curricula", "program_id", "pas-un-uuid"),
    ("curriculum-subjects", "semester", 0), ("curriculum-subjects", "study_year", 9),
    ("curriculum-subjects", "credits", 61), ("curriculum-subjects", "coefficient", -1),
    ("admission-requirements", "kind", "age"), ("admission-requirements", "category", "autre"),
    ("admission-requirements", "description", "ab"), ("admission-requirements", "min_average", 21),
    ("tuition-fees", "amount", -1), ("tuition-fees", "amount", "100.123"), ("tuition-fees", "amount", "abc"),
    ("tuition-fees", "currency", "tnd"), ("tuition-fees", "currency", "DINAR"), ("tuition-fees", "study_year", 9),
    ("tuition-fees", "fee_type", "monthly"), ("tuition-fees", "valid_from", "31/08/2027"),
    ("payment-plans", "installments", []), ("payment-plans", "payment_methods", ["bitcoin"]),
    ("payment-plans", "discount_percent", 150),
    ("payment-plans", "installments", [{"label": "Sans montant"}]),
    ("payment-plans", "installments", [{"label": "A", "percentage": 60}, {"label": "B", "percentage": 30}]),
    ("payment-plans", "installments", [{"label": f"T{i}", "amount": 1} for i in range(13)]),
]


def _short(value) -> str:
    if isinstance(value, str) and len(value) > 12:
        return f"texte-{len(value)}-car"
    if isinstance(value, list) and len(value) > 2:
        return f"{len(value)}-elements"
    text = repr(value).replace("'", "")
    return {"": "vide", "   ": "espaces"}.get(value, text) if isinstance(value, str) else text


@pytest.mark.parametrize("resource,field,value", INVALID, ids=[f"{r}.{f}={_short(v)}" for r, f, v in INVALID])
def test_valeur_invalide(client, ctx, resource, field, value):
    url, body = valid_payloads(ctx)[resource]
    body[field] = value
    err = assert_error(client.post(url, headers=IIT, json=body), 422, "VALIDATION_ERROR")
    assert err["details"], err


@pytest.mark.parametrize("resource", ["programs", "subjects", "tuition-fees", "payment-plans"])
def test_champ_inconnu_refuse(client, ctx, resource):
    """Faute de frappe dans un nom de champ : refusée au lieu d'être ignorée en silence."""
    url, body = valid_payloads(ctx)[resource]
    assert_error(client.post(url, headers=IIT, json={**body, "montant_typo": 1}), 422, "VALIDATION_ERROR")


def test_regles_croisees(client, ctx):
    pid = ctx["program"]["id"]
    # Période inversée
    err = assert_error(client.post(f"{API}/catalog/tuition-fees", headers=IIT, json={
        "program_id": pid, "academic_year": "2032-2033", "fee_type": "tuition", "amount": 1,
        "valid_from": "2027-09-01", "valid_until": "2027-01-01"}), 422, "VALIDATION_ERROR")
    assert "postérieure" in str(err["details"])
    # « Moyenne minimale » sans la moyenne
    err = assert_error(client.post(f"{API}/catalog/admission-requirements", headers=IIT, json={
        "program_id": pid, "kind": "minimum_average", "description": "Moyenne"}), 422, "VALIDATION_ERROR")
    assert "min_average" in str(err["details"])
    # Somme des pourcentages
    err = assert_error(client.post(f"{API}/catalog/payment-plans", headers=IIT, json={
        "program_id": pid, "academic_year": CURRENT_YEAR, "name": "Faux", "installments": [
            {"label": "A", "percentage": 50}, {"label": "B", "percentage": 20}]}), 422, "VALIDATION_ERROR")
    assert "100" in str(err["details"])


@pytest.mark.parametrize("url_key,field", [
    ("program", "name"), ("program", "code"), ("program", "is_active"), ("fee", "amount"), ("fee", "fee_type"),
])
def test_patch_refuse_null_sur_champ_obligatoire(client, ctx, url_key, field):
    base = {"program": "programs", "fee": "tuition-fees"}[url_key]
    r = client.patch(f"{API}/catalog/{base}/{ctx[url_key]['id']}", headers=IIT, json={field: None})
    err = assert_error(r, 422, "VALIDATION_ERROR")
    assert field in str(err["details"])


def test_patch_controle_aussi_la_valeur_deja_en_base(client, ctx, db):
    """valid_until seul, antérieur au valid_from déjà enregistré : refusé par la contrainte SQL (422)."""
    fee = make_fee(client, ctx["program"]["id"], academic_year="2033-2034", valid_from="2033-09-01")
    err = assert_error(client.patch(f"{API}/catalog/tuition-fees/{fee['id']}", headers=IIT,
                                    json={"valid_until": "2033-01-01"}), 422, "VALIDATION_ERROR")
    assert "postérieure" in err["message"]
    assert db.execute("SELECT valid_until FROM tuition_fee WHERE id = %s", (fee["id"],)).fetchone()[0] is None


def test_patch_type_minimum_average_sans_moyenne_en_base(client, ctx):
    req = client.post(f"{API}/catalog/admission-requirements", headers=IIT, json={
        "program_id": ctx["program"]["id"], "kind": "document", "description": "Diplôme"}).json()
    err = assert_error(client.patch(f"{API}/catalog/admission-requirements/{req['id']}", headers=IIT,
                                    json={"kind": "minimum_average"}), 422, "VALIDATION_ERROR")
    assert "min_average" in err["message"]


@pytest.mark.parametrize("params", [{"size": 0}, {"size": 101}, {"page": 0}, {"page": "un"}, {"level": "doctorat"},
                                    {"cycle": "doctorat"}, {"sort": "prix"}],
                         ids=["size=0", "size=101", "page=0", "page=un", "level=doctorat", "cycle=doctorat", "sort=prix"])
def test_parametres_de_liste_invalides(client, params):
    assert_error(client.get(f"{API}/programs", params=params), 422, "VALIDATION_ERROR")


@pytest.mark.parametrize("params", [{"visibility": "online"}, {"status": "deleted"}, {"valid_on": "demain"},
                                    {"academic_year": "2026"}, {"program_id": "abc"}],
                         ids=["visibility=online", "status=deleted", "valid_on=demain", "academic_year=2026",
                              "program_id=abc"])
def test_filtres_de_gestion_invalides(client, params):
    assert_error(client.get(f"{API}/catalog/tuition-fees", headers=IIT, params=params), 422, "VALIDATION_ERROR")


@pytest.mark.parametrize("body", [{}, {"status": "deleted"}, {"status": None}, {"status": "published", "x": 1}],
                         ids=["corps-vide", "statut-inconnu", "statut-null", "champ-en-trop"])
def test_changement_de_statut_invalide(client, ctx, body):
    r = client.post(f"{API}/catalog/tuition-fees/{ctx['fee']['id']}/status", headers=IIT, json=body)
    assert_error(r, 422, "VALIDATION_ERROR")


def test_corps_json_mal_forme(client):
    r = client.post(f"{API}/catalog/subjects", headers={**IIT, "Content-Type": "application/json"},
                    content=b'{"code": "T-X", "name": ')
    assert_error(r, 422, "VALIDATION_ERROR")
