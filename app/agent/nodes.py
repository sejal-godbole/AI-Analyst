"""
LangGraph node functions with full-stack observability instrumentation.

Each node takes the current AgentState and returns a partial-state dict to
merge in. LLM calls happen in classify_intent / generate_sql / final_answer.
All nodes record spans, latencies, guardrail decisions, and errors with the
Observability Tracer.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

from langgraph.types import interrupt

from app.agent.llm import chat
from app.agent.prompts import (
    FINAL_ANSWER_SYSTEM,
    INTENT_CLASSIFICATION_SYSTEM,
    SQL_GENERATION_SYSTEM,
    build_final_answer_prompt,
    build_sql_generation_prompt,
    build_intent_classification_prompt,
)
from app.agent.state import AgentState
from app.config import get_settings
from app.logging.audit import write_audit_log
from app.mcp import client as mcp_client
from app.observability.schema_tracker import schema_tracker
from app.observability.tracer import get_current_trace_id, set_current_trace_id, tracer
from app.security.guardrails import evaluate_guardrails
from app.security.pii_filter import filter_sensitive_columns
from app.security.sql_validator import validate_sql

logger = logging.getLogger("ai_analyst.nodes")

_VALID_INTENTS = {"READ", "INSERT", "UPDATE", "DELETE", "DESTRUCTIVE", "UNKNOWN"}
_SQL_FENCE_RE = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _strip_sql_fences(text: str) -> str:
    return _SQL_FENCE_RE.sub("", text).strip()


def _safe_chat(
    system: str,
    user: str,
    temperature: float = 0.0,
    node_name: str = "llm_call",
    trace_id: Optional[str] = None,
) -> str:
    """Invokes chat() handling monkeypatched signatures in test suites gracefully."""
    try:
        return chat(system, user, temperature=temperature, node_name=node_name, trace_id=trace_id)
    except TypeError:
        try:
            return chat(system, user, temperature=temperature)
        except TypeError:
            return chat(system, user)


# ---------------------------------------------------------------------------
# Node 1 — receive_question
# ---------------------------------------------------------------------------
async def receive_question(state: AgentState) -> dict:
    settings = get_settings()
    trace_id = state.get("trace_id") or get_current_trace_id() or str(uuid.uuid4())
    set_current_trace_id(trace_id)

    span = tracer.start_span(
        node_name="receive_question",
        span_type="node",
        input_data={"user_question": state["user_question"]},
        trace_id=trace_id,
    )
    logger.info("Question received (trace_id=%s): %s", trace_id, state["user_question"])

    tracer.end_span(
        span.span_id,
        output_data={"status": "initialized", "max_retries": settings.max_retries},
        status="completed",
    )

    return {
        "trace_id": trace_id,
        "retry_count": 0,
        "max_retries": settings.max_retries,
        "query_history": [],
        "validation_errors": [],
        "requires_confirmation": False,
        "confirmation_message": None,
    }


# ---------------------------------------------------------------------------
# Node 2 — inspect_schema
# ---------------------------------------------------------------------------
async def inspect_schema_node(state: AgentState) -> dict:
    trace_id = state.get("trace_id") or get_current_trace_id()
    span = tracer.start_span("inspect_schema", "node", trace_id=trace_id)

    schema = await mcp_client.call_inspect_schema(trace_id=trace_id)
    table_count = len(schema.get("tables", {}))
    logger.info("Schema inspected: %d tables", table_count)

    # Track schema snapshot and diffs
    is_changed, change_rec = schema_tracker.record_and_diff(schema)
    if is_changed:
        logger.info("Database schema change detected: %s", change_rec.diff_summary if change_rec else "")

    tracer.end_span(
        span.span_id,
        output_data={"table_count": table_count, "schema_changed": is_changed},
        status="completed",
    )
    return {"schema": schema}


# ---------------------------------------------------------------------------
# Node 3 — build_schema_context
# ---------------------------------------------------------------------------
async def build_schema_context(state: AgentState) -> dict:
    trace_id = state.get("trace_id") or get_current_trace_id()
    span = tracer.start_span("build_schema_context", "node", trace_id=trace_id)

    schema = state["schema"]
    lines: list[str] = []
    relationships: list[str] = []

    for table_name, table in schema.get("tables", {}).items():
        col_descs = []
        pks = set(table.get("primary_keys", []))
        for col, dtype in table.get("columns", {}).items():
            marker = " (PK)" if col in pks else ""
            col_descs.append(f"{col} {dtype}{marker}")
        lines.append(f"TABLE {table_name}: " + ", ".join(col_descs))

        for fk in table.get("foreign_keys", []):
            relationships.append(
                f"{table_name}.{fk['column']} -> {fk['references_table']}.{fk['references_column']}"
            )

    context = "\n".join(lines)
    if relationships:
        context += "\n\nRELATIONSHIPS:\n" + "\n".join(relationships)

    tracer.end_span(
        span.span_id,
        output_data={"tables_formatted": len(schema.get("tables", {}))},
        status="completed",
    )
    return {"schema_context": context}


# ---------------------------------------------------------------------------
# Node 4 — classify_intent
# ---------------------------------------------------------------------------
async def classify_intent(state: AgentState) -> dict:
    trace_id = state.get("trace_id") or get_current_trace_id()
    span = tracer.start_span("classify_intent", "node", trace_id=trace_id)

    chat_history = state.get("chat_history", [])
    prompt = build_intent_classification_prompt(state["user_question"], chat_history)
    raw = _safe_chat(
        INTENT_CLASSIFICATION_SYSTEM,
        prompt,
        node_name="classify_intent",
        trace_id=trace_id,
    ).strip().upper()

    intent = raw if raw in _VALID_INTENTS else "UNKNOWN"
    logger.info("Classified intent: %s (raw=%r)", intent, raw)

    if intent == "DESTRUCTIVE":
        err = "Destructive administrative statements (DROP/TRUNCATE/ALTER/GRANT/REVOKE) are never allowed."
        tracer.record_guardrail_decision(
            decision="BLOCKED",
            rule_name="Destructive Statement Guardrail",
            reason=err,
            trace_id=trace_id,
        )
        tracer.end_span(span.span_id, output_data={"intent": intent}, status="blocked", error=err)
        return {
            "intent": intent,
            "error_message": err,
            "status": "rejected",
        }

    if intent == "UNKNOWN":
        err = "I am a database assistant and can only answer questions related to the provided database schema."
        tracer.record_guardrail_decision(
            decision="BLOCKED",
            rule_name="Out of Scope Guardrail",
            reason=err,
            trace_id=trace_id,
        )
        tracer.end_span(span.span_id, output_data={"intent": intent}, status="blocked", error=err)
        return {
            "intent": intent,
            "error_message": err,
            "status": "rejected",
        }

    tracer.end_span(span.span_id, output_data={"intent": intent}, status="completed")
    return {"intent": intent}


# ---------------------------------------------------------------------------
# Node 5 — generate_sql
# ---------------------------------------------------------------------------
async def generate_sql(state: AgentState) -> dict:
    trace_id = state.get("trace_id") or get_current_trace_id()
    span = tracer.start_span("generate_sql", "node", trace_id=trace_id)

    history = state.get("query_history", [])
    chat_history = state.get("chat_history", [])
    prompt = build_sql_generation_prompt(
        state["user_question"], state["schema_context"], history, chat_history
    )
    raw_sql = _safe_chat(
        SQL_GENERATION_SYSTEM,
        prompt,
        temperature=0.0,
        node_name="generate_sql",
        trace_id=trace_id,
    )
    sql = _strip_sql_fences(raw_sql)
    logger.info("Generated SQL (attempt %d): %s", state.get("retry_count", 0) + 1, sql)

    tracer.end_span(
        span.span_id,
        output_data={"raw_sql": raw_sql, "generated_sql": sql, "attempt": state.get("retry_count", 0) + 1},
        status="completed",
    )
    return {"raw_sql": raw_sql, "generated_sql": sql}


# ---------------------------------------------------------------------------
# Node 6 — validate_sql
# ---------------------------------------------------------------------------
async def validate_sql_node(state: AgentState) -> dict:
    trace_id = state.get("trace_id") or get_current_trace_id()
    span = tracer.start_span("validate_sql", "node", trace_id=trace_id)

    result = validate_sql(state["generated_sql"], state["schema"])
    history = list(state.get("query_history", []))
    attempt_no = len(history) + 1

    if not result.is_valid:
        error_text = "; ".join(result.errors)
        history.append({"attempt": attempt_no, "sql": state["generated_sql"], "error": error_text})
        logger.warning("SQL validation failed (attempt %d): %s", attempt_no, error_text)

        tracer.end_span(
            span.span_id,
            output_data={"valid": False, "errors": result.errors},
            status="retried" if state.get("retry_count", 0) < state.get("max_retries", 3) else "failed",
            error=error_text,
        )
        return {
            "validation_errors": result.errors,
            "validated_sql": None,
            "query_history": history,
            "error_message": error_text,
        }

    logger.info("SQL validation passed (attempt %d).", attempt_no)
    tracer.end_span(
        span.span_id,
        output_data={"valid": True, "operation": result.operation, "sql": state["generated_sql"]},
        status="completed",
    )
    return {
        "validation_errors": [],
        "validated_sql": state["generated_sql"],
        "error_message": None,
    }


# ---------------------------------------------------------------------------
# Node 7 — safety_check
# ---------------------------------------------------------------------------
async def safety_check(state: AgentState) -> dict:
    trace_id = state.get("trace_id") or get_current_trace_id()
    span = tracer.start_span("safety_check", "node", trace_id=trace_id)

    result = validate_sql(state["validated_sql"], state["schema"])
    estimated_rows = None

    if result.operation in ("UPDATE", "DELETE"):
        preview = await mcp_client.call_preview_query(state["validated_sql"], trace_id=trace_id)
        if preview.get("ok"):
            estimated_rows = preview.get("estimated_rows")

    decision = evaluate_guardrails(result, estimated_row_count=estimated_rows)

    if not decision.allowed:
        logger.warning("Guardrails rejected SQL: %s", decision.reason)
        tracer.record_guardrail_decision(
            decision="BLOCKED",
            rule_name="Unsafe Query Guardrail",
            reason=decision.reason,
            sql=state["validated_sql"],
            estimated_rows=estimated_rows,
            trace_id=trace_id,
        )
        tracer.end_span(
            span.span_id,
            output_data={"decision": "BLOCKED", "reason": decision.reason},
            status="blocked",
            error=decision.reason,
        )
        return {
            "safety_status": "unsafe",
            "error_message": decision.reason,
            "status": "rejected",
        }

    if decision.requires_confirmation:
        row_note = f" (~{estimated_rows} rows)" if estimated_rows is not None else ""
        message = (
            f"This operation will run:\n\n{state['validated_sql']}\n\n"
            f"Estimated impact{row_note}. Do you want to continue?"
        )
        tracer.record_guardrail_decision(
            decision="CONFIRMATION_REQUIRED",
            rule_name="Write Confirmation Guardrail",
            reason=decision.reason or "Modifying statement requires human authorization.",
            sql=state["validated_sql"],
            estimated_rows=estimated_rows,
            trace_id=trace_id,
        )
        tracer.end_span(
            span.span_id,
            output_data={"decision": "CONFIRMATION_REQUIRED", "estimated_rows": estimated_rows},
            status="needs_confirmation",
        )
        return {
            "safety_status": "needs_confirmation",
            "requires_confirmation": True,
            "confirmation_message": message,
        }

    tracer.record_guardrail_decision(
        decision="ALLOWED",
        rule_name="Safety Checks Passed",
        reason="Query meets all safety constraints and policies.",
        sql=state["validated_sql"],
        trace_id=trace_id,
    )
    tracer.end_span(
        span.span_id,
        output_data={"decision": "ALLOWED", "operation": result.operation},
        status="completed",
    )
    return {"safety_status": "safe", "requires_confirmation": False}


# ---------------------------------------------------------------------------
# Node 7b — human_confirmation (uses LangGraph interrupt)
# ---------------------------------------------------------------------------
async def human_confirmation(state: AgentState) -> dict:
    trace_id = state.get("trace_id") or get_current_trace_id()
    span = tracer.start_span("human_confirmation", "node", trace_id=trace_id)

    approved = interrupt(
        {
            "message": state["confirmation_message"],
            "sql": state["validated_sql"],
            "trace_id": trace_id,
        }
    )
    user_decision_str = "approved" if approved else "rejected"
    tracer.record_guardrail_decision(
        decision="CONFIRMATION_RESOLVED",
        rule_name="Human In The Loop",
        reason=f"User {user_decision_str} execution.",
        sql=state["validated_sql"],
        user_decision=user_decision_str,
        trace_id=trace_id,
    )
    tracer.end_span(
        span.span_id,
        output_data={"approved": bool(approved)},
        status="completed" if approved else "blocked",
    )
    return {
        "confirmation_approved": bool(approved),
        "status": "success" if approved else "rejected",
        "error_message": None if approved else "Execution rejected by human operator.",
    }


# ---------------------------------------------------------------------------
# Node 8 — execute_query
# ---------------------------------------------------------------------------
async def execute_query_node(state: AgentState) -> dict:
    trace_id = state.get("trace_id") or get_current_trace_id()
    span = tracer.start_span("execute_query", "node", trace_id=trace_id)

    settings = get_settings()
    result = await mcp_client.call_execute_query(
        state["validated_sql"], settings.max_rows, trace_id=trace_id
    )

    if not result.get("ok"):
        history = list(state.get("query_history", []))
        attempt_no = len(history) + 1
        history.append(
            {"attempt": attempt_no, "sql": state["validated_sql"], "error": result.get("error")}
        )
        logger.warning("Execution failed (attempt %d): %s", attempt_no, result.get("error"))
        tracer.end_span(
            span.span_id,
            output_data={"ok": False, "error": result.get("error")},
            status="retried" if state.get("retry_count", 0) < state.get("max_retries", 3) else "failed",
            error=result.get("error"),
        )
        return {
            "execution_result": result,
            "error_message": result.get("error"),
            "query_history": history,
        }

    logger.info(
        "Execution succeeded: operation=%s row_count=%s",
        result.get("operation"),
        result.get("row_count"),
    )
    tracer.end_span(
        span.span_id,
        output_data={"ok": True, "operation": result.get("operation"), "row_count": result.get("row_count")},
        status="completed",
    )
    return {
        "execution_result": result,
        "rows_affected": result.get("row_count"),
        "error_message": None,
    }


# ---------------------------------------------------------------------------
# Node 9 — check_result
# ---------------------------------------------------------------------------
async def check_result(state: AgentState) -> dict:
    trace_id = state.get("trace_id") or get_current_trace_id()
    span = tracer.start_span("check_result", "node", trace_id=trace_id)

    result = state.get("execution_result") or {}

    if not result.get("ok"):
        tracer.end_span(span.span_id, output_data={"ok": False}, status="failed", error=result.get("error"))
        return {"result_validation": {"ok": False, "reason": result.get("error")}}

    operation = result.get("operation")
    row_count = result.get("row_count", 0)

    if operation == "SELECT" and row_count == 0:
        tracer.end_span(span.span_id, output_data={"ok": True, "empty": True}, status="completed")
        return {"result_validation": {"ok": True, "reason": "empty_result_set"}}

    if operation in ("UPDATE", "DELETE") and row_count == 0:
        reason = "Statement executed but affected 0 rows — the WHERE clause may not match any data."
        tracer.end_span(span.span_id, output_data={"ok": False}, status="retried", error=reason)
        return {
            "result_validation": {
                "ok": False,
                "reason": reason,
            }
        }

    tracer.end_span(span.span_id, output_data={"ok": True, "rows": row_count}, status="completed")
    return {"result_validation": {"ok": True, "reason": None}}


def clean_markdown(text: str) -> str:
    text = re.sub(r"\*\*+", "", text)
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("* ") or stripped.startswith("- "):
            lines.append(f"  • {stripped[2:]}")
        else:
            lines.append(line)
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Node 10 — final_answer
# ---------------------------------------------------------------------------
async def final_answer_node(state: AgentState) -> dict:
    trace_id = state.get("trace_id") or get_current_trace_id() or str(uuid.uuid4())
    span = tracer.start_span("final_answer", "node", trace_id=trace_id)

    result = state.get("execution_result") or {}
    operation = result.get("operation")

    if operation == "SELECT":
        rows, redacted = filter_sensitive_columns(result.get("rows", []))
        if redacted:
            logger.info("Redacted sensitive columns from LLM-facing result: %s", redacted)
        summary = f"{len(rows)} row(s):\n{rows[:20]}"
        if redacted:
            summary += f"\nNote: The following sensitive columns were redacted for security: {', '.join(redacted)}."
    else:
        summary = f"{operation} affected {result.get('row_count', 0)} row(s)."

    answer = _safe_chat(
        FINAL_ANSWER_SYSTEM,
        build_final_answer_prompt(state["user_question"], summary),
        temperature=0.2,
        node_name="final_answer",
        trace_id=trace_id,
    )
    answer = clean_markdown(answer)

    write_audit_log(
        user_question=state["user_question"],
        intent=state.get("intent"),
        generated_sql=state.get("validated_sql"),
        validation_status="valid",
        execution_status="success",
        error=None,
        retry_count=state.get("retry_count", 0),
        rows_affected=result.get("row_count"),
        result_summary=summary[:500],
        confirmation_required=state.get("requires_confirmation", False),
        confirmation_status="approved" if state.get("confirmation_approved") else None,
    )

    chat_history = list(state.get("chat_history", []))
    chat_history.append({"question": state["user_question"], "answer": answer})
    chat_history = chat_history[-5:]

    tracer.end_span(span.span_id, output_data={"answer_length": len(answer)}, status="completed")

    # End and finalize trace
    tracer.end_trace(
        trace_id=trace_id,
        final_answer=answer,
        status="success",
        validated_sql=state.get("validated_sql"),
        raw_sql=state.get("raw_sql"),
        rows_affected=result.get("row_count"),
        intent=state.get("intent"),
        sql_operation=operation,
        retry_count=state.get("retry_count", 0),
    )

    return {"final_answer": answer, "status": "success", "chat_history": chat_history}


# ---------------------------------------------------------------------------
# Node 11 — error_terminal
# ---------------------------------------------------------------------------
async def error_terminal(state: AgentState) -> dict:
    trace_id = state.get("trace_id") or get_current_trace_id() or str(uuid.uuid4())
    span = tracer.start_span("error_terminal", "node", trace_id=trace_id)

    error = state.get("error_message") or "Unknown error."
    logger.error("Terminating with error: %s", error)

    write_audit_log(
        user_question=state["user_question"],
        intent=state.get("intent"),
        generated_sql=state.get("generated_sql"),
        validation_status="invalid" if state.get("validation_errors") else "n/a",
        execution_status="failed",
        error=error,
        retry_count=state.get("retry_count", 0),
        rows_affected=None,
        result_summary=None,
        confirmation_required=state.get("requires_confirmation", False),
        confirmation_status="rejected" if state.get("confirmation_approved") is False else None,
    )

    status = state.get("status") or "error"
    final_ans = f"I couldn't complete this request: {error}"

    chat_history = list(state.get("chat_history", []))
    chat_history.append({"question": state["user_question"], "answer": final_ans})
    chat_history = chat_history[-5:]

    tracer.end_span(span.span_id, output_data={"error": error, "status": status}, status="completed")

    tracer.end_trace(
        trace_id=trace_id,
        final_answer=final_ans,
        status=status,
        error=error,
        validated_sql=state.get("validated_sql"),
        raw_sql=state.get("raw_sql"),
        intent=state.get("intent"),
        retry_count=state.get("retry_count", 0),
    )

    return {
        "final_answer": final_ans,
        "status": status,
        "chat_history": chat_history,
    }


# ---------------------------------------------------------------------------
# Node 12 — increment_retry
# ---------------------------------------------------------------------------
async def increment_retry(state: AgentState) -> dict:
    trace_id = state.get("trace_id") or get_current_trace_id()
    span = tracer.start_span("increment_retry", "node", trace_id=trace_id)
    new_count = state.get("retry_count", 0) + 1
    tracer.end_span(span.span_id, output_data={"new_retry_count": new_count}, status="completed")
    return {"retry_count": new_count}
