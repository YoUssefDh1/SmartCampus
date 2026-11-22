"""Hachage des mots de passe, JWT et dépendances d'autorisation.

Deux niveaux de contrôle (SA-28) :
1. RBAC global — `require_roles(...)` lit la claim `role` du jeton puis vérifie le
   compte en base (un compte désactivé est refusé même avec un jeton valide).
2. Périmètre — `check_resource_ownership(...)` pour les ressources d'un candidat et
   `check_school_scope(...)` pour l'isolation IIT / ISB des gestionnaires.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.db.session import get_dict_connection
from app.models.user import MANAGER_SCOPE, Role, UserAccount
from app.services import user_service
from app.services.guest_service import GuestSession, fetch_guest_session, touch_guest_session

bearer_scheme = HTTPBearer(auto_error=False)

# Argon2id, sel aléatoire généré par la bibliothèque (exigence SA-28).
_password_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


@dataclass
class TokenPayload:
    sub: str | None = None
    session_id: str | None = None
    role: str | None = None
    token_type: str | None = None
    exp: int | None = None

    @property
    def is_guest(self) -> bool:
        return self.role == Role.GUEST.value


def create_guest_access_token(session_id: str, expires_at: datetime | None = None) -> str:
    """Génère le JWT visiteur : sub=guest_<id>, role=guest, exp calée sur la session."""
    settings = get_settings()
    if expires_at is None:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.guest_session_ttl_hours)
    payload = {
        "sub": f"guest_{session_id}",
        "session_id": str(session_id),
        "role": Role.GUEST.value,
        "iat": datetime.now(timezone.utc),
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_user_access_token(user: UserAccount) -> str:
    """JWT d'un compte authentifié : courte durée, renouvelé via /auth/refresh."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "role": user.role,
        "school_scope": user.school_scope,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, verify_expiry: bool = True) -> TokenPayload:
    settings = get_settings()
    options = None if verify_expiry else {"verify_exp": False}
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
                            options=options)
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Session invitée expirée ou jeton invalide.")
    except jwt.InvalidTokenError:
        raise UnauthorizedError("Session invitée expirée ou jeton invalide.")
    return TokenPayload(
        sub=claims.get("sub"),
        session_id=claims.get("session_id"),
        role=claims.get("role"),
        token_type=claims.get("type"),
        exp=claims.get("exp"),
    )


def decode_guest_token(guest_token: str, expected_session_id: str) -> TokenPayload:
    """Preuve de possession d'une session visiteur (SA-29) : le JWT signé remis par POST /auth/guest.

    L'expiration n'est pas contrôlée ici : c'est `guest_session.expires_at` en base qui
    fait foi, afin qu'une session expirée réponde 400 GUEST_SESSION_EXPIRED et non 401.
    """
    invalid = ForbiddenError("Jeton invité invalide pour cette session.", code="INVALID_GUEST_TOKEN")
    try:
        payload = decode_token(guest_token, verify_expiry=False)
    except UnauthorizedError:
        raise invalid
    if not payload.is_guest or payload.session_id != str(expected_session_id):
        raise invalid
    return payload


def get_current_guest_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> GuestSession:
    """Vérifie le JWT puis le TTL en base à chaque requête (contrôle inline, SA-25)."""
    if credentials is None:
        raise UnauthorizedError("Jeton d'authentification manquant.")

    payload = decode_token(credentials.credentials)
    if not payload.is_guest or not payload.session_id:
        raise ForbiddenError("Le jeton fourni n'est pas un jeton invité valide.")

    with get_dict_connection() as connection:
        session = fetch_guest_session(connection, payload.session_id)
        if session is None:
            raise UnauthorizedError("Session invitée introuvable.")
        if session.expired:
            raise UnauthorizedError("Session invitée expirée ou jeton invalide.")
        touch_guest_session(connection, session.id)
    return session


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UserAccount:
    """Compte authentifié derrière un jeton `role != guest`."""
    if credentials is None:
        raise UnauthorizedError("Jeton d'authentification manquant.")

    payload = decode_token(credentials.credentials)
    if payload.is_guest:
        raise ForbiddenError("Un jeton visiteur ne donne pas accès à un compte utilisateur.")

    with get_dict_connection() as connection:
        user = user_service.fetch_user_by_id(connection, payload.sub)
    if user is None:
        raise UnauthorizedError("Compte introuvable.")
    if not user.is_active:
        raise UnauthorizedError("Ce compte a été désactivé.", code="ACCOUNT_DISABLED")
    return user


def require_roles(*roles: Role):
    """Dépendance RBAC : 403 si le rôle du compte n'est pas autorisé (admin excepté)."""
    allowed = {role.value for role in roles}

    def dependency(current_user: UserAccount = Depends(get_current_user)) -> UserAccount:
        if current_user.is_admin or current_user.role in allowed:
            return current_user
        raise ForbiddenError("Privilèges insuffisants pour accéder à cette ressource.",
                             code="PERMISSION_DENIED")

    return dependency


def check_resource_ownership(resource_owner_id: str, current_user: UserAccount) -> bool:
    """Niveau 2 du contrôle d'accès : le propriétaire, ou un admin."""
    if current_user.is_admin or current_user.id == str(resource_owner_id):
        return True
    raise ForbiddenError("Accès non autorisé à cette ressource spécifique.",
                         code="RESOURCE_ACCESS_DENIED")


def check_school_scope(current_user: UserAccount, school: str) -> bool:
    """Isolation multi-établissement : un gestionnaire IIT ne voit pas les dossiers ISB."""
    if current_user.is_admin:
        return True
    allowed = MANAGER_SCOPE.get(current_user.role)
    if allowed and allowed == school.strip().upper():
        return True
    raise ForbiddenError("Privilèges insuffisants pour accéder à cette ressource.",
                         code="PERMISSION_DENIED")
