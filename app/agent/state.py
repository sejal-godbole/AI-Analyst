"""
Explicit LangGraph state for the AI Analyst Agent.

Kept as a plain TypedDict (LangGraph's native state shape) so every field's
purpose is easy to read. Nothing here ever contains DATABASE_URL or any
other credential.
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict


class QueryAttempt(TypedDict):
    attempt: int
    sql: Optional[str]
    error: Optional[str]


class AgentState(TypedDict, total=False):
    # --- Input ---
    user_question: str  # the raw natural-language request from the user

    # --- Schema context ---
    schema: dict  # raw metadata from inspect_schema MCP tool
    schema_context: str  # LLM-friendly text rendering of `schema` + relationships

    # --- Intent classification (advisory only — never trusted for security) ---
    intent: str  # READ | INSERT | UPDATE | DELETE | DESTRUCTIVE | UNKNOWN

    # --- SQL generation / validation ---
    generated_sql: Optional[str]  # latest SQL text produced by the LLM
    validated_sql: Optional[str]  # SQL that passed validate_sql()
    validation_errors: list[str]  # errors from the most recent validation attempt

    # --- Safety ---
    safety_status: str  # "safe" | "unsafe" | "needs_confirmation" | "pending"
    requires_confirmation: bool
    confirmation_message: Optional[str]
    confirmation_approved: Optional[bool]  # set after interrupt() resumes

    # --- Execution ---
    execution_result: Optional[dict]  # raw dict returned by the execute_query MCP tool
    rows_affected: Optional[int]

    # --- Result validation ---
    result_validation: Optional[dict]  # {"ok": bool, "reason": str | None}

    # --- Error handling / retries ---
    error_message: Optional[str]
    retry_count: int
    max_retries: int

    # --- History for retry prompts / audit ---
    query_history: list[QueryAttempt]
    chat_history: list[dict]

    # --- Output ---
    final_answer: Optional[str]

    # --- Audit ---
    audit_id: Optional[int]

    # --- Terminal status for the API layer ---
    status: str  # "success" | "error" | "rejected" | "awaiting_confirmation"
