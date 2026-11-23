from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le message ne peut pas être vide.")
        return value


class ChatSource(BaseModel):
    source_id: str
    title: str
    origin: str
    page: int | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    language: str
    sources: list[ChatSource] = Field(default_factory=list)
    profile_updates: dict[str, Any] = Field(default_factory=dict)
    next_action: Literal[
        "ask_question",
        "explain_program",
        "compare_programs",
        "start_preregistration",
        "handover_human",
    ] = "ask_question"


class ChatMessageItem(BaseModel):
    id: UUID
    role: Literal["user", "assistant", "system"]
    content: str
    language: str | None = None
    sources: list[ChatSource] | None = None
    next_action: str | None = None
    profile_updates: dict[str, Any] | None = None
    created_at: datetime


class ChatSessionItem(BaseModel):
    id: UUID
    status: str
    language: str | None = None
    started_at: datetime
    last_message_at: datetime | None = None
    profile_draft: dict[str, Any] = Field(default_factory=dict)


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionItem]
    total: int


class ChatHistoryResponse(ChatSessionItem):
    guest_session_id: UUID | None = None
    messages: list[ChatMessageItem] = Field(default_factory=list)
    total_messages: int
