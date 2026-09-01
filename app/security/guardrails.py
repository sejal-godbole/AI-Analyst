"""
Guardrail policy decisions layered on top of sql_validator's parse result.

Decides:
  - is this SQL outright rejected (destructive / no WHERE on DELETE)?
  - does it need human confirmation before executing (broad UPDATE, etc.)?

These decisions are deterministic — they do not depend on what the LLM
*claims* the intent is.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.security.sql_validator import ValidationResult


@dataclass
class GuardrailDecision:
    allowed: bool
    requires_confirmation: bool
    reason: str | None = None


def evaluate_guardrails(
    validation: ValidationResult, estimated_row_count: int | None = None
) -> GuardrailDecision:
    settings = get_settings()

    if not validation.is_valid:
        return GuardrailDecision(
            allowed=False, requires_confirmation=False, reason="SQL failed validation."
        )

    if validation.is_destructive:
        return GuardrailDecision(
            allowed=False,
            requires_confirmation=False,
            reason="Destructive administrative statements (DROP/TRUNCATE/ALTER/GRANT/REVOKE) are never allowed.",
        )

    op = validation.operation

    if op == "SELECT":
        # Reads are always allowed; row limiting is handled separately.
        return GuardrailDecision(allowed=True, requires_confirmation=False)

    if op == "DELETE":
        if not validation.has_where_clause:
            return GuardrailDecision(
                allowed=False,
                requires_confirmation=False,
                reason="DELETE without a WHERE clause would remove all rows and is blocked. "
                "Add a WHERE clause that targets specific row(s).",
            )
        needs_confirm = settings.require_write_confirmation or (
            estimated_row_count is not None
            and estimated_row_count >= settings.confirmation_row_threshold
        )
        return GuardrailDecision(
            allowed=True,
            requires_confirmation=needs_confirm,
            reason="DELETE with WHERE clause; confirmation required by policy."
            if needs_confirm
            else None,
        )

    if op == "UPDATE":
        if not validation.has_where_clause:
            # Broad update — always require confirmation, never silently reject,
            # since the user may genuinely want a bulk update.
            return GuardrailDecision(
                allowed=True,
                requires_confirmation=True,
                reason="UPDATE without a WHERE clause affects every row in the table "
                "and requires explicit confirmation.",
            )
        needs_confirm = settings.require_write_confirmation or (
            estimated_row_count is not None
            and estimated_row_count >= settings.confirmation_row_threshold
        )
        return GuardrailDecision(
            allowed=True,
            requires_confirmation=needs_confirm,
            reason="UPDATE with WHERE clause; confirmation required by policy."
            if needs_confirm
            else None,
        )

    if op == "INSERT":
        needs_confirm = settings.require_write_confirmation
        return GuardrailDecision(
            allowed=True,
            requires_confirmation=needs_confirm,
            reason="INSERT requires confirmation by policy." if needs_confirm else None,
        )

    return GuardrailDecision(
        allowed=False, requires_confirmation=False, reason=f"Unsupported operation: {op}."
    )
