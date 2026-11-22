"""Inscription, connexion et rotation des jetons de renouvellement (SA-28).

Aucun mot de passe en clair n'atteint la base ou les journaux : seule l'empreinte
Argon2id est stockée. Les jetons de renouvellement sont opaques et conservés hachés
dans `refresh_token`, ce qui permet de les révoquer à chaque usage (rotation).
"""
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.errors import UniqueViolation

from app.core.config import get_settings
from app.core.errors import ConflictError, UnauthorizedError
from app.core.security import create_user_access_token, hash_password, verify_password
from app.models.user import Role, UserAccount, split_full_name
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services import user_service

EMAIL_TAKEN_MESSAGE = "Un compte associé à cette adresse email existe déjà."


@dataclass
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_token_id: str


def _token_hash(refresh_token: str) -> str:
    """Le jeton de renouvellement est aléatoire : une empreinte SHA-256 suffit."""
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def _issue_tokens(connection: psycopg.Connection, user: UserAccount) -> IssuedTokens:
    settings = get_settings()
    refresh_token = secrets.token_urlsafe(48)
    token_id = user_service.store_refresh_token(
        connection,
        user_id=user.id,
        token_hash=_token_hash(refresh_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days),
    )
    return IssuedTokens(
        access_token=create_user_access_token(user),
        refresh_token=refresh_token,
        expires_in=settings.access_token_minutes * 60,
        refresh_token_id=token_id,
    )


def register_candidate(connection: psycopg.Connection, request: RegisterRequest) -> UserAccount:
    if user_service.email_exists(connection, request.email):
        raise ConflictError(EMAIL_TAKEN_MESSAGE, code="EMAIL_ALREADY_EXISTS")

    first_name, last_name = split_full_name(request.full_name)
    try:
        return user_service.create_account(
            connection,
            email=request.email,
            password_hash=hash_password(request.password),
            first_name=first_name,
            last_name=last_name,
            role=Role.CANDIDATE.value,
        )
    except UniqueViolation:  # deux inscriptions simultanées sur le même email
        raise ConflictError(EMAIL_TAKEN_MESSAGE, code="EMAIL_ALREADY_EXISTS")


def login(connection: psycopg.Connection, request: LoginRequest) -> tuple[UserAccount, IssuedTokens]:
    credentials = user_service.fetch_credentials(connection, request.email)
    if credentials is None or not verify_password(request.password, credentials[1]):
        raise UnauthorizedError("Identifiants d'authentification invalides.",
                                code="INVALID_CREDENTIALS")

    user = credentials[0]
    if not user.is_active:
        raise UnauthorizedError("Ce compte a été désactivé.", code="ACCOUNT_DISABLED")

    user_service.mark_login(connection, user.id)
    return user, _issue_tokens(connection, user)


def refresh_tokens(connection: psycopg.Connection, refresh_token: str) -> IssuedTokens:
    stored = user_service.fetch_refresh_token(connection, _token_hash(refresh_token))
    if stored is None or stored["revoked_at"] is not None:
        raise UnauthorizedError("Jeton de renouvellement invalide ou déjà utilisé.",
                                code="INVALID_REFRESH_TOKEN")
    if stored["expires_at"] <= datetime.now(timezone.utc):
        raise UnauthorizedError("Jeton de renouvellement expiré. Veuillez vous reconnecter.",
                                code="INVALID_REFRESH_TOKEN")

    user = user_service.fetch_user_by_id(connection, str(stored["user_id"]))
    if user is None:
        raise UnauthorizedError("Compte introuvable.")
    if not user.is_active:
        raise UnauthorizedError("Ce compte a été désactivé.", code="ACCOUNT_DISABLED")

    with connection.transaction():
        tokens = _issue_tokens(connection, user)
        user_service.revoke_refresh_token(connection, str(stored["id"]),
                                         replaced_by_id=tokens.refresh_token_id)
    return tokens
