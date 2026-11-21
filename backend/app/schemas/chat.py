from typing import Any, Literal

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
