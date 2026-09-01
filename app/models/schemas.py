"""Pydantic models for the FastAPI request/response contract."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Natural-language question or instruction.")
    # Set when resuming a paused workflow after the user confirms/rejects a risky write.
    thread_id: Optional[str] = Field(
        default=None,
        description="Conversation/thread id to resume a workflow awaiting confirmation.",
    )
    confirm: Optional[bool] = Field(
        default=None,
        description="If resuming a workflow that requires confirmation: true to proceed, false to cancel.",
    )


class AnalyzeResponse(BaseModel):
    status: str  # "success" | "error" | "awaiting_confirmation" | "rejected"
    answer: Optional[str] = None
    sql: Optional[str] = None
    requires_confirmation: bool = False
    confirmation_message: Optional[str] = None
    thread_id: Optional[str] = None
    error: Optional[str] = None
    rows_affected: Optional[int] = None


class SchemaColumn(BaseModel):
    name: str
    data_type: str
    nullable: bool


class ForeignKey(BaseModel):
    column: str
    references_table: str
    references_column: str


class TableSchema(BaseModel):
    columns: dict[str, str]
    nullable: dict[str, bool] = Field(default_factory=dict)
    primary_keys: list[str] = Field(default_factory=list)
    foreign_keys: list[ForeignKey] = Field(default_factory=list)


class DatabaseSchema(BaseModel):
    tables: dict[str, TableSchema]


class QueryHistoryEntry(BaseModel):
    attempt: int
    sql: Optional[str] = None
    error: Optional[str] = None
