"""Comptes utilisateurs : rôles et lecture de la table `app_user` (schema.sql).

Le dépôt n'a pas d'ORM (psycopg brut) : ce module porte les dataclasses et les
règles qui dépendent du rôle, partagées par la couche sécurité et les services.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Role(str, Enum):
    """`guest` n'est pas un compte : il n'existe que comme claim de JWT visiteur (SA-25)."""

    GUEST = "guest"
    CANDIDATE = "candidate"
    IIT_MANAGER = "iit_manager"
    ISB_MANAGER = "isb_manager"
    INTERVIEWER = "interviewer"
    ADVISOR = "advisor"  # le conseiller de SA-3, cible des escalades
    DIRECTION = "direction"
    ADMIN = "admin"


ACCOUNT_ROLES = frozenset(role.value for role in Role if role is not Role.GUEST)

# Périmètre école des gestionnaires : isole les dossiers IIT des dossiers ISB.
MANAGER_SCOPE = {Role.IIT_MANAGER.value: "IIT", Role.ISB_MANAGER.value: "ISB"}


@dataclass
class UserAccount:
    id: str
    email: str
    first_name: str
    last_name: str
    role: str
    institution_code: str | None
    is_active: bool
    created_at: datetime

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def school_scope(self) -> str | None:
        """`iit` ou `isb` pour un gestionnaire rattaché à une école, None sinon."""
        return self.institution_code.lower() if self.institution_code else None

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN.value

    @property
    def is_candidate(self) -> bool:
        return self.role == Role.CANDIDATE.value


def row_to_account(row: dict) -> UserAccount:
    return UserAccount(
        id=str(row["id"]),
        email=row["email"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        role=row["role"],
        institution_code=row["institution_code"],
        is_active=row["is_active"],
        created_at=row["created_at"],
    )


def split_full_name(full_name: str) -> tuple[str, str]:
    """Le contrat SA-28 échange un `full_name` ; `app_user` stocke prénom et nom séparés."""
    parts = full_name.split()
    if len(parts) < 2:
        raise ValueError("Indiquez un prénom et un nom séparés par une espace.")
    return " ".join(parts[:-1]), parts[-1]
