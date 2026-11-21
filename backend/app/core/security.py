"""Rôles de la plateforme (figés en SA-5). La logique JWT/RBAC est codée par le Membre 4 (SA-28)."""
from enum import Enum


class Role(str, Enum):
    GUEST = "guest"
    CANDIDATE = "candidate"
    IIT_MANAGER = "iit_manager"
    ISB_MANAGER = "isb_manager"
    INTERVIEWER = "interviewer"
    DIRECTION = "direction"
    ADMIN = "admin"
