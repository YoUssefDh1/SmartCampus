"""Schémas partagés par toutes les routes."""
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str = Field(examples=["FORBIDDEN"])
    message: str = Field(examples=["Vous n'avez pas accès à ce dossier."])
    details: list = Field(default_factory=list)
    request_id: str | None = Field(default=None, examples=["req_9f2c1a"])


class ErrorResponse(BaseModel):
    error: ErrorDetail


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    app: str
    version: str
    environment: str
