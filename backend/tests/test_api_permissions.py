"""4. Autorisations d'accès.

- Routes publiques /programs : ouvertes à tous (candidats, visiteurs, agent IA).
- Routes /catalog : sans authentification -> 401 ; rôle non autorisé -> 403 ; la vérification du rôle
  passe AVANT la recherche de l'élément (un rôle interdit ne peut pas savoir si un id existe).
- Responsable IIT / ISB : uniquement les formations de son école (lecture et écriture).
- Direction : lecture seule. Administrateur : tout.
- Jetons JWT : signature, expiration, compte actif et rôle relus en base.
"""
import os
import time
import uuid

import jwt
import pytest

from app.core.config import get_settings
from tests.helpers import (ADMIN, ADVISOR, API, CANDIDATE, CURRENT_YEAR, DIRECTION, IIT, INTERVIEWER, ISB,
                           assert_error, code, make_curriculum, make_fee, make_program, seed_program)

pytestmark = pytest.mark.usefixtures("catalog_cleanup")
X, Y = str(uuid.uuid4()), str(uuid.uuid4())


def token(claims: dict, secret: str | None = None, exp_in: int | None = 600) -> str:
    s = get_settings()
    payload = {**claims, **({"exp": int(time.time()) + exp_in} if exp_in is not None else {})}
    return jwt.encode(payload, secret or s.jwt_secret, algorithm=s.jwt_algorithm)


def bearer(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


GUEST = bearer(token({"sub": str(uuid.uuid4()), "role": "guest"}))

WRITE_ROUTES = [
    ("POST", "/catalog/programs"), ("PATCH", f"/catalog/programs/{X}"), ("DELETE", f"/catalog/programs/{X}"),
    ("POST", f"/catalog/programs/{X}/specialties"),
    ("PATCH", f"/catalog/specialties/{X}"), ("DELETE", f"/catalog/specialties/{X}"),
    ("POST", "/catalog/subjects"), ("PATCH", f"/catalog/subjects/{X}"), ("DELETE", f"/catalog/subjects/{X}"),
    ("POST", "/catalog/curricula"), ("PATCH", f"/catalog/curricula/{X}"), ("DELETE", f"/catalog/curricula/{X}"),
    ("POST", f"/catalog/curricula/{X}/duplicate"), ("POST", f"/catalog/curricula/{X}/subjects"),
    ("PATCH", f"/catalog/curricula/{X}/subjects/{Y}"), ("DELETE", f"/catalog/curricula/{X}/subjects/{Y}"),
    *[(m, p.format(r=r, X=X)) for r in ("admission-requirements", "tuition-fees", "payment-plans")
      for m, p in (("POST", "/catalog/{r}"), ("PATCH", "/catalog/{r}/{X}"), ("DELETE", "/catalog/{r}/{X}"),
                   ("POST", "/catalog/{r}/{X}/status"))],
]
READ_ROUTES = [
    "/catalog/institutions", "/catalog/programs", f"/catalog/programs/{X}", f"/catalog/programs/{X}/specialties",
    "/catalog/specialties", f"/catalog/specialties/{X}", "/catalog/subjects", f"/catalog/subjects/{X}",
    "/catalog/curricula", f"/catalog/curricula/{X}",
    *[p.format(r=r, X=X) for r in ("admission-requirements", "tuition-fees", "payment-plans")
      for p in ("/catalog/{r}", "/catalog/{r}/{X}")],
]
DENIED_FOR_WRITE = {"candidat": CANDIDATE, "jury": INTERVIEWER, "conseiller": ADVISOR, "direction": DIRECTION,
                    "visiteur (JWT)": GUEST}
DENIED_FOR_READ = {k: v for k, v in DENIED_FOR_WRITE.items() if k != "direction"}


@pytest.mark.parametrize("method,path", WRITE_ROUTES, ids=[f"{m} {p.replace(X, '{id}').replace(Y, '{id2}')}"
                                                           for m, p in WRITE_ROUTES])
def test_ecriture_refusee_sans_role_autorise(client, method, path):
    body = None if method == "DELETE" else {}
    assert_error(client.request(method, API + path, json=body), 401, "UNAUTHORIZED")
    for who, headers in DENIED_FOR_WRITE.items():
        r = client.request(method, API + path, headers=headers, json=body)
        assert r.status_code == 403, f"{who} : {r.status_code} {r.text}"     # 403 avant 404 / 422
        assert_error(r, 403, "FORBIDDEN")


@pytest.mark.parametrize("path", READ_ROUTES, ids=[p.replace(X, "{id}") for p in READ_ROUTES])
def test_lecture_de_gestion_reservee_au_personnel(client, path):
    assert_error(client.get(API + path), 401, "UNAUTHORIZED")
    for who, headers in DENIED_FOR_READ.items():
        assert client.get(API + path, headers=headers).status_code == 403, who
    for headers in (DIRECTION, ADMIN, IIT, ISB):                   # autorisés : 200 (liste) ou 404 (id inconnu)
        assert client.get(API + path, headers=headers).status_code in (200, 404)


def test_routes_publiques_ouvertes_sans_authentification(client, db):
    pid = seed_program(db, "ING-INFO")
    for path in ("/programs", f"/programs/{pid}", f"/programs/{pid}/tuition", f"/programs/{pid}/admission",
                 f"/programs/{pid}/curriculum"):
        assert client.get(API + path).status_code == 200, path


# --------------------------------------------------------------------------- portée par école
@pytest.fixture(scope="module")
def isb(client, db):
    """Éléments de l'ISB (seed + un programme pédagogique créé par le responsable ISB)."""
    pid = seed_program(db, "LIC-GEST")
    one = lambda sql: str(db.execute(sql, (pid,)).fetchone()[0])  # noqa: E731
    data = {"program": pid,
            "specialty": one("SELECT id FROM specialty WHERE program_id = %s LIMIT 1"),
            "fee": one("SELECT id FROM tuition_fee WHERE program_id = %s LIMIT 1"),
            "requirement": one("SELECT id FROM admission_requirement WHERE program_id = %s LIMIT 1"),
            "plan": one("SELECT id FROM payment_plan WHERE program_id = %s LIMIT 1"),
            "curriculum": make_curriculum(client, pid, headers=ISB, academic_year="2034-2035")["id"],
            "institution_id": one("SELECT institution_id FROM program WHERE id = %s")}
    yield data
    db.execute("DELETE FROM curriculum WHERE id = %s", (data["curriculum"],))   # formation du seed : nettoyer


def test_responsable_iit_ne_touche_pas_a_l_isb(client, isb):
    calls = [
        ("GET", f"/catalog/programs/{isb['program']}", None),
        ("PATCH", f"/catalog/programs/{isb['program']}", {"capacity": 1}),
        ("DELETE", f"/catalog/programs/{isb['program']}", None),
        ("GET", f"/catalog/programs/{isb['program']}/specialties", None),
        ("POST", f"/catalog/programs/{isb['program']}/specialties", {"name": "Intrusion"}),
        ("GET", f"/catalog/specialties/{isb['specialty']}", None),
        ("PATCH", f"/catalog/specialties/{isb['specialty']}", {"name": "Intrusion"}),
        ("GET", f"/catalog/curricula/{isb['curriculum']}", None),
        ("PATCH", f"/catalog/curricula/{isb['curriculum']}", {"description": "Intrusion"}),
        ("POST", "/catalog/curricula", {"program_id": isb["program"], "academic_year": CURRENT_YEAR}),
        ("POST", "/catalog/tuition-fees", {"program_id": isb["program"], "academic_year": CURRENT_YEAR,
                                           "fee_type": "other", "amount": 1}),
        *[(m, f"/catalog/{r}/{isb[k]}", b) for r, k in (("tuition-fees", "fee"), ("admission-requirements",
                                                                                   "requirement"),
                                                        ("payment-plans", "plan"))
          for m, b in (("GET", None), ("PATCH", {"description": "Intrusion"}), ("DELETE", None))],
        *[("POST", f"/catalog/{r}/{isb[k]}/status", {"status": "archived"})
          for r, k in (("tuition-fees", "fee"), ("admission-requirements", "requirement"), ("payment-plans", "plan"))],
    ]
    for method, path, body in calls:
        r = client.request(method, API + path, headers=IIT, json=body)
        assert r.status_code == 403, f"{method} {path} : {r.status_code} {r.text}"
    # Rien n'a changé côté ISB
    assert client.get(f"{API}/catalog/programs/{isb['program']}", headers=ISB).json()["capacity"] == 150


@pytest.mark.parametrize("path", ["programs", "specialties", "curricula", "tuition-fees", "admission-requirements",
                                  "payment-plans"])
def test_listes_filtrees_sur_l_ecole_du_responsable(client, path):
    items = client.get(f"{API}/catalog/{path}", headers=IIT, params={"size": 100}).json()["items"]
    assert items and {i["school"] for i in items} == {"IIT"}
    # Demander une autre école ne contourne pas la règle
    assert client.get(f"{API}/catalog/{path}", headers=IIT, params={"school": "ISB"}).json()["total"] == 0
    assert {i["school"] for i in client.get(f"{API}/catalog/{path}", headers=DIRECTION,
                                            params={"size": 100}).json()["items"]} >= {"IIT", "ISB"}


def test_responsable_ne_peut_pas_deplacer_ni_creer_dans_une_autre_ecole(client, isb):
    p = make_program(client)
    r = client.patch(f"{API}/catalog/programs/{p['id']}", headers=IIT, json={"institution_id": isb["institution_id"]})
    assert_error(r, 403, "FORBIDDEN")
    r = client.post(f"{API}/catalog/programs", headers=IIT, json={
        "institution_id": isb["institution_id"], "code": code(), "name": "Ailleurs", "cycle": "other"})
    assert_error(r, 403, "FORBIDDEN")


def test_administrateur_agit_sur_toutes_les_ecoles(client, isb):
    p = make_program(client, headers=ADMIN, institution_id=isb["institution_id"])
    assert p["school"] == "ISB"
    iit_prog = make_program(client)
    assert client.patch(f"{API}/catalog/programs/{iit_prog['id']}", headers=ADMIN,
                        json={"capacity": 7}).json()["capacity"] == 7
    fee = make_fee(client, p["id"], headers=ADMIN)
    assert client.post(f"{API}/catalog/tuition-fees/{fee['id']}/status", headers=ADMIN,
                       json={"status": "published"}).status_code == 200


def test_direction_lit_tout_mais_ne_modifie_rien(client, isb):
    assert client.get(f"{API}/catalog/programs/{isb['program']}", headers=DIRECTION).status_code == 200
    assert_error(client.patch(f"{API}/catalog/programs/{isb['program']}", headers=DIRECTION, json={"capacity": 1}),
                 403, "FORBIDDEN")


# --------------------------------------------------------------------------- jetons JWT
@pytest.fixture(scope="module")
def isb_manager(db):
    inst = db.execute("SELECT id FROM institution WHERE code = 'ISB'").fetchone()[0]
    return str(db.execute(
        """INSERT INTO app_user (role, institution_id, first_name, last_name, email, password_hash)
           VALUES ('isb_manager', %s, 'Test', 'ISB', %s, 'x') RETURNING id""",
        (inst, f"test-{uuid.uuid4().hex[:8]}@smartcampus.test")).fetchone()[0])


def test_jeton_valide_portee_lue_en_base(client, isb_manager):
    # Le jeton prétend « admin » : le rôle réel (isb_manager) est relu dans app_user.
    tok = token({"sub": isb_manager, "role": "admin"})
    items = client.get(f"{API}/catalog/programs", headers=bearer(tok), params={"size": 100}).json()["items"]
    assert items and {i["school"] for i in items} == {"ISB"}
    # Le jeton est prioritaire sur l'en-tête de démo
    items = client.get(f"{API}/catalog/programs", headers={**bearer(tok), **ADMIN}).json()["items"]
    assert {i["school"] for i in items} == {"ISB"}


@pytest.mark.parametrize("case", ["expire", "sans_expiration", "mauvaise_signature", "compte_inconnu", "sub_invalide",
                                  "texte_quelconque", "algorithme_none"])
def test_jeton_invalide_refuse(client, isb_manager, case):
    tok = {
        "expire": lambda: token({"sub": isb_manager, "role": "isb_manager"}, exp_in=-60),
        "sans_expiration": lambda: token({"sub": isb_manager, "role": "isb_manager"}, exp_in=None),
        "mauvaise_signature": lambda: token({"sub": isb_manager, "role": "isb_manager"}, secret="autre-secret-" * 3),
        "compte_inconnu": lambda: token({"sub": str(uuid.uuid4()), "role": "admin"}),
        "sub_invalide": lambda: token({"sub": "admin", "role": "admin"}),
        "texte_quelconque": lambda: "pas.un.jeton",
        "algorithme_none": lambda: jwt.encode({"sub": isb_manager, "role": "admin", "exp": int(time.time()) + 600},
                                              None, algorithm="none"),
    }[case]()
    assert_error(client.get(f"{API}/catalog/programs", headers=bearer(tok)), 401, "UNAUTHORIZED")


def test_compte_desactive_perd_l_acces_immediatement(client, db, isb_manager):
    tok = token({"sub": isb_manager, "role": "isb_manager"})
    assert client.get(f"{API}/catalog/programs", headers=bearer(tok)).status_code == 200
    db.execute("UPDATE app_user SET is_active = false WHERE id = %s", (isb_manager,))
    try:
        assert_error(client.get(f"{API}/catalog/programs", headers=bearer(tok)), 401, "UNAUTHORIZED")
    finally:
        db.execute("UPDATE app_user SET is_active = true WHERE id = %s", (isb_manager,))


def test_role_de_demo_inconnu(client):
    assert_error(client.get(f"{API}/catalog/programs", headers={"X-Dev-Role": "superadmin"}), 422, "VALIDATION_ERROR")


@pytest.mark.parametrize("env", [{"ENVIRONMENT": "production"}, {"AUTH_DEV_MODE": "false"}],
                         ids=["ENVIRONMENT=production", "AUTH_DEV_MODE=false"])
def test_mode_demo_inactif_hors_developpement(client, env):
    """En production (ou AUTH_DEV_MODE=false), l'en-tête X-Dev-Role n'ouvre plus rien."""
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    get_settings.cache_clear()
    try:
        assert_error(client.get(f"{API}/catalog/programs", headers=ADMIN), 401, "UNAUTHORIZED")
        assert client.get(f"{API}/programs").status_code == 200          # le public reste ouvert
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        get_settings.cache_clear()
    assert client.get(f"{API}/catalog/programs", headers=ADMIN).status_code == 200
