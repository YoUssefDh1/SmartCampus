"""Configuration des tests. Les tests du catalogue utilisent la base PostgreSQL de DATABASE_URL
(migrations + seed appliqués) ; ils sont ignorés si la base est injoignable."""
import os

# Avant tout import de l'application : mode démo de l'authentification (en-tête X-Dev-Role).
os.environ.setdefault("ENVIRONMENT", "development")
os.environ["AUTH_DEV_MODE"] = "true"

import psycopg  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db.session import get_connection  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="session")
def db():
    """Connexion directe (préparation / nettoyage). Ignore les tests si la base n'est pas prête."""
    try:
        conn = get_connection()
        ready = conn.execute("SELECT to_regclass('public.payment_plan') IS NOT NULL").fetchone()[0]
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL injoignable : lancer `docker compose up -d`.")
    if not ready:
        pytest.skip("Migration 002 absente : lancer `python -m app.db.migrate` puis `python -m app.db.seed`.")
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def catalog_cleanup(db):
    """Supprime, à la fin de chaque module, tout ce que les tests ont créé (codes « T-… »).
    Ordre : comptes de test (et leurs préinscriptions) d'abord, puis formations, puis matières."""
    yield
    db.execute("DELETE FROM app_user WHERE email LIKE 'test-%@smartcampus.test'")
    db.execute("DELETE FROM program WHERE code LIKE 'T-%'")
    db.execute("DELETE FROM subject WHERE code LIKE 'T-%'")


@pytest.hookimpl(optionalhook=True)
def pytest_html_report_title(report):
    """Titre du rapport HTML (python -m pytest --html=rapport_tests.html --self-contained-html)."""
    report.title = "SmartCampus AI - Tests des API du catalogue"
