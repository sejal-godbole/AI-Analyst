"""
Writes one audit row per completed (or terminated) agent run.

Never stores full raw result sets — only a short summary string — and never
stores credentials or prompts containing secrets.
"""
from __future__ import annotations

import logging

from app.config import get_settings
from app.database.connection import get_connection

logger = logging.getLogger("ai_analyst.audit")


def write_audit_log(
    *,
    user_question: str,
    intent: str | None,
    generated_sql: str | None,
    validation_status: str,
    execution_status: str,
    error: str | None,
    retry_count: int,
    rows_affected: int | None,
    result_summary: str | None,
    confirmation_required: bool,
    confirmation_status: str | None,
) -> None:
    settings = get_settings()
    table = settings.audit_log_table

    query = f"""
        INSERT INTO {table} (
            user_question, intent, generated_sql, validation_status,
            execution_status, error, retry_count, rows_affected,
            result_summary, confirmation_required, confirmation_status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        user_question,
        intent,
        generated_sql,
        validation_status,
        execution_status,
        error,
        retry_count,
        rows_affected,
        result_summary,
        confirmation_required,
        confirmation_status,
    )

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
            conn.commit()
    except Exception as e:
        # Audit logging must never crash the request.
        logger.warning("Failed to write audit log: %s", e)
