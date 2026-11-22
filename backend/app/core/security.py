"""Rôles de la plateforme (figés en SA-5) et contrôle d'accès (RBAC) des routes.

L'émission des jetons (/auth/login) est codée par le Membre 4 (SA-28). Ce module ne fait que LIRE
le jeton : claims attendus `sub` (uuid du compte app_user ou de la guest_session), `role` et `exp`
(obligatoire : un jeton sans expiration est refusé).
Pour le personnel, le rôle et l'école sont relus dans app_user : un compte désactivé perd
l'accès immédiatement.

Mode démo (AUTH_DEV_MODE=true ET ENVIRONMENT=development) : sans jeton, l'en-tête
`X-Dev-Role` (admin, iit_manager, isb_manager...) simule un utilisateur. Pour un responsable,
l'école est déduite du rôle (iit_manager -> IIT). À désactiver dès que /auth/login existe.
"""
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

import jwt
import psycopg
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.db.session import get_db


class Role(str, Enum):
    GUEST = "guest"
    CANDIDATE = "candidate"
    IIT_MANAGER = "iit_manager"
    ISB_MANAGER = "isb_manager"
    INTERVIEWER = "interviewer"
    ADVISOR = "advisor"
    DIRECTION = "direction"
    ADMIN = "admin"


MANAGER_ROLES = (Role.IIT_MANAGER, Role.ISB_MANAGER)
# Gestion du catalogue : responsables académiques (leur école) et administrateur (toutes les écoles).
CATALOG_WRITE_ROLES = (Role.IIT_MANAGER, Role.ISB_MANAGER, Role.ADMIN)
# Consultation interne du catalogue (brouillons compris).
CATALOG_READ_ROLES = (*CATALOG_WRITE_ROLES, Role.DIRECTION)


@dataclass(frozen=True)
class Actor:
    """Utilisateur authentifié qui appelle la route."""

    user_id: UUID | None
    role: Role
    institution_id: UUID | None = None
    institution_code: str | None = None
    request_id: str | None = None

    @property
    def is_manager(self) -> bool:
        return self.role in MANAGER_ROLES

    def scoped_institution_id(self) -> UUID | None:
        """École imposée à toutes les requêtes de l'utilisateur (None = toutes les écoles)."""
        return self.institution_id if self.is_manager else None

    def can_manage_institution(self, institution_id: UUID | None) -> bool:
        if self.role == Role.ADMIN:
            return True
        return self.is_manager and institution_id is not None and institution_id == self.institution_id


_bearer = HTTPBearer(auto_error=False, description="Jeton JWT obtenu via /auth/login")


def _staff_actor(conn: psycopg.Connection, user_id: UUID, request_id: str | None) -> Actor:
    row = conn.execute(
        """SELECT u.role, u.institution_id, i.code AS institution_code, u.is_active
             FROM app_user u LEFT JOIN institution i ON i.id = u.institution_id
            WHERE u.id = %s""", (user_id,)).fetchone()
    if not row or not row["is_active"]:
        raise UnauthorizedError("Compte introuvable ou désactivé.")
    return Actor(user_id, Role(row["role"]), row["institution_id"], row["institution_code"], request_id)


def _dev_actor(conn: psycopg.Connection, role: Role, user_id: UUID | None, request_id: str | None) -> Actor:
    if user_id:
        return _staff_actor(conn, user_id, request_id)
    inst_id = inst_code = None
    if role in MANAGER_ROLES:
        inst_code = role.value.split("_")[0].upper()
        row = conn.execute("SELECT id FROM institution WHERE code = %s", (inst_code,)).fetchone()
        if not row:
            raise UnauthorizedError(f"Mode démo : l'école {inst_code} n'existe pas (lancer python -m app.db.seed).")
        inst_id = row["id"]
    return Actor(None, role, inst_id, inst_code, request_id)


def get_current_actor(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_dev_role: Role | None = Header(
        None, include_in_schema=get_settings().dev_auth_enabled,
        description="Mode démo uniquement : rôle simulé (admin, iit_manager, isb_manager...)"),
    x_dev_user_id: UUID | None = Header(
        None, include_in_schema=get_settings().dev_auth_enabled,
        description="Mode démo uniquement (optionnel) : identifiant d'un compte app_user existant"),
    conn: psycopg.Connection = Depends(get_db),
) -> Actor:
    settings = get_settings()
    request_id = getattr(request.state, "request_id", None)

    if credentials:
        try:
            # exp obligatoire : un jeton sans date d'expiration resterait valable à vie s'il fuitait.
            claims = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
                                options={"require": ["exp", "sub"]})
            role = Role(claims.get("role"))
            subject = UUID(str(claims.get("sub")))
        except (jwt.PyJWTError, ValueError) as exc:
            raise UnauthorizedError("Jeton invalide ou expiré.") from exc
        if role == Role.GUEST:
            return Actor(None, Role.GUEST, request_id=request_id)
        return _staff_actor(conn, subject, request_id)

    if settings.dev_auth_enabled and x_dev_role:
        return _dev_actor(conn, x_dev_role, x_dev_user_id, request_id)

    raise UnauthorizedError("Authentification requise.")


def require_roles(*roles: Role):
    """Dépendance de route : `actor: Actor = Depends(require_roles(Role.ADMIN, ...))`."""

    def checker(actor: Actor = Depends(get_current_actor)) -> Actor:
        if actor.role not in roles:
            raise ForbiddenError("Votre rôle ne permet pas cette action.")
        return actor

    return checker
