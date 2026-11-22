"""Schémas Pydantic des routes « Auth » (SA-25 pour les visiteurs, SA-28 pour les comptes)."""
import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, field_validator

from app.core.config import get_settings
from app.models.user import UserAccount, split_full_name

_EMAIL_FORMAT = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalise_email(value: str) -> str:
    value = value.strip()
    if not _EMAIL_FORMAT.match(value):
        raise ValueError("Adresse email invalide.")
    return value.lower()  # l'unicité en base porte sur lower(email)


def _check_password(value: str) -> str:
    minimum = get_settings().password_min_length
    if len(value) < minimum:
        raise ValueError(f"Le mot de passe doit contenir au moins {minimum} caractères.")
    return value


def _check_full_name(value: str) -> str:
    value = value.strip()
    split_full_name(value)  # lève ValueError s'il manque le prénom ou le nom
    return value


Email = Annotated[str, AfterValidator(_normalise_email)]
Password = Annotated[str, AfterValidator(_check_password)]
FullName = Annotated[str, AfterValidator(_check_full_name)]


class GuestTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str = "guest"
    session_id: UUID
    expires_at: datetime = Field(examples=["2026-11-23T14:30:00Z"])


class RegisterRequest(BaseModel):
    email: Email
    password: Password
    full_name: FullName


class LoginRequest(BaseModel):
    email: Email
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ClaimRequest(BaseModel):
    guest_session_id: UUID
    guest_token: str = Field(min_length=16,
                             description="JWT visiteur signé remis par POST /auth/guest.")
    confirm_transfer: bool = True

    @field_validator("confirm_transfer")
    @classmethod
    def _must_be_confirmed(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Le transfert des données doit être explicitement confirmé.")
        return value


class ClaimResponse(BaseModel):
    status: str = "success"
    message: str
    user_id: UUID
    claimed_conversation_ids: list[UUID]
    transferred_messages_count: int
    merged_profile_draft: dict


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    school_scope: str | None = None
    is_active: bool
    created_at: datetime

    @classmethod
    def from_account(cls, user: UserAccount) -> "UserResponse":
        return cls(id=UUID(user.id), email=user.email, full_name=user.full_name, role=user.role,
                   school_scope=user.school_scope, is_active=user.is_active,
                   created_at=user.created_at)


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginResponse(TokenPairResponse):
    user: UserResponse
