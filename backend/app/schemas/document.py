"""Metadata schemas for official document management."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

DocumentType = Literal["brochure", "regulation", "curriculum", "admission_conditions", "equivalence_rules", "other"]
DocumentStatus = Literal["draft", "active", "archived", "deleted"]


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Annotated[str, Field(min_length=1, max_length=250)] | None = None
    description: Annotated[str, Field(max_length=5000)] | None = None
    doc_type: DocumentType | None = None
    program_id: UUID | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set:
            raise ValueError("Au moins un champ doit être fourni.")
        if self.model_fields_set.intersection({"title", "doc_type", "program_id"}):
            null_fields = [
                name for name in ("title", "doc_type", "program_id")
                if name in self.model_fields_set and getattr(self, name) is None
            ]
            if null_fields:
                raise ValueError(f"Ces champs ne peuvent pas être vides : {', '.join(null_fields)}.")
        return self

    def changes(self) -> dict:
        return self.model_dump(exclude_unset=True)


class DocumentOut(BaseModel):
    id: UUID
    institution_id: UUID
    school: str
    program_id: UUID
    program_code: str
    program_name: str
    title: str
    description: str | None
    doc_type: DocumentType
    status: DocumentStatus
    original_filename: str
    current_version_id: UUID | None
    current_version_number: int | None
    current_mime_type: str | None
    current_size_bytes: int | None
    current_checksum_sha256: str | None
    current_uploaded_at: datetime | None
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class DocumentVersionOut(BaseModel):
    id: UUID
    document_id: UUID
    version_number: int
    original_filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    language: str | None
    uploaded_by_id: UUID
    uploaded_at: datetime
    is_current: bool
