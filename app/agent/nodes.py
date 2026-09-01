"""
LangGraph node functions.

Each node takes the current AgentState and returns a partial-state dict to
merge in. LLM calls happen only in classify_intent / generate_sql /
final_answer. Every other node is deterministic Python.
"""
from __future__ import annotations

import logging
import re

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
from app.security.guardrails import evaluate_guardrails
from app.security.pii_filter import filter_sensitive_columns
from app.security.sql_validator import validate_sql

logger = logging.getLogger("ai_analyst.nodes")

_VALID_INTENTS = {"READ", "INSERT", "UPDATE", "DELETE", "DESTRUCTIVE", "UNKNOWN"}
_SQL_FENCE_RE = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _strip_sql_fences(text: str) -> str:
    return _SQL_FENCE_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# Node 1
# ---------------------------------------------------------------------------
async def receive_question(state: AgentState) -> dict:
    settings = get_settings()
    logger.info("Question received: %s", state["user_question"])
    return {
        "retry_count": 0,
        "max_retries": settings.max_retries,
        "query_history": [],
        "validation_errors": [],
        "requires_confirmation": False,
        "confirmation_message": None,
    }


# ---------------------------------------------------------------------------
# Node 2
# ---------------------------------------------------------------------------
async def inspect_schema_node(state: AgentState) -> dict:
    schema = await mcp_client.call_inspect_schema()
    logger.info("Schema inspected: %d tables", len(schema.get("tables", {})))
    return {"schema": schema}


# ---------------------------------------------------------------------------
# Node 3
# ---------------------------------------------------------------------------
async def build_schema_context(state: AgentState) -> dict:
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

    return {"schema_context": context}


# ---------------------------------------------------------------------------
# Node 4
# ---------------------------------------------------------------------------
async def classify_intent(state: AgentState) -> dict:
    chat_history = state.get("chat_history", [])
    prompt = build_intent_classification_prompt(state["user_question"], chat_history)
    raw = chat(INTENT_CLASSIFICATION_SYSTEM, prompt).strip().upper()
    intent = raw if raw in _VALID_INTENTS else "UNKNOWN"
    logger.info("Classified intent: %s (raw=%r)", intent, raw)
    if intent == "DESTRUCTIVE":
        return {
            "intent": intent,
            "error_message": "Destructive administrative statements (DROP/TRUNCATE/ALTER/GRANT/REVOKE) are never allowed.",
            "status": "rejected",
        }
    if intent == "UNKNOWN":
        return {
            "intent": intent,
            "error_message": "I am a database assistant and can only answer questions related to the provided database schema.",
            "status": "rejected",
        }
    return {"intent": intent}


# ---------------------------------------------------------------------------
# Node 5
# ---------------------------------------------------------------------------
async def generate_sql(state: AgentState) -> dict:
    history = state.get("query_history", [])
    chat_history = state.get("chat_history", [])
    prompt = build_sql_generation_prompt(
        state["user_question"], state["schema_context"], history, chat_history
    )
    raw_sql = chat(SQL_GENERATION_SYSTEM, prompt, temperature=0.0)
    sql = _strip_sql_fences(raw_sql)
    logger.info("Generated SQL (attempt %d): %s", state.get("retry_count", 0) + 1, sql)
    return {"generated_sql": sql}


# ---------------------------------------------------------------------------
# Node 6 — validate_sql
# ---------------------------------------------------------------------------
async def validate_sql_node(state: AgentState) -> dict:
    result = validate_sql(state["generated_sql"], state["schema"])
    history = list(state.get("query_history", []))
    attempt_no = len(history) + 1

    if not result.is_valid:
        error_text = "; ".join(result.errors)
        history.append({"attempt": attempt_no, "sql": state["generated_sql"], "error": error_text})
        logger.warning("SQL validation failed (attempt %d): %s", attempt_no, error_text)
        return {
            "validation_errors": result.errors,
            "validated_sql": None,
            "query_history": history,
            "error_message": error_text,
        }

    logger.info("SQL validation passed (attempt %d).", attempt_no)
    return {
        "validation_errors": [],
        "validated_sql": state["generated_sql"],
        "error_message": None,
    }


# ---------------------------------------------------------------------------
# Node 7 — safety_check
# ---------------------------------------------------------------------------
async def safety_check(state: AgentState) -> dict:
    result = validate_sql(state["validated_sql"], state["schema"])

    estimated_rows = None
    if result.operation in ("UPDATE", "DELETE"):
        preview = await mcp_client.call_preview_query(state["validated_sql"])
        if preview.get("ok"):
            estimated_rows = preview.get("estimated_rows")

    decision = evaluate_guardrails(result, estimated_row_count=estimated_rows)

    if not decision.allowed:
        logger.warning("Guardrails rejected SQL: %s", decision.reason)
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
        return {
            "safety_status": "needs_confirmation",
            "requires_confirmation": True,
            "confirmation_message": message,
        }

    return {"safety_status": "safe", "requires_confirmation": False}


# ---------------------------------------------------------------------------
# Node 7b — human_confirmation (uses LangGraph interrupt)
# ---------------------------------------------------------------------------
async def human_confirmation(state: AgentState) -> dict:
    """
    Pauses the graph using LangGraph's interrupt() mechanism. The FastAPI
    layer surfaces `confirmation_message` to the user and resumes the graph
    via Command(resume=...) once the user responds.
    """
    approved = interrupt(
        {
            "message": state["confirmation_message"],
            "sql": state["validated_sql"],
        }
    )
    return {"confirmation_approved": bool(approved)}


# ---------------------------------------------------------------------------
# Node 8 — execute_query
# ---------------------------------------------------------------------------
async def execute_query_node(state: AgentState) -> dict:
    settings = get_settings()
    result = await mcp_client.call_execute_query(state["validated_sql"], settings.max_rows)

    if not result.get("ok"):
        history = list(state.get("query_history", []))
        attempt_no = len(history) + 1
        history.append(
            {"attempt": attempt_no, "sql": state["validated_sql"], "error": result.get("error")}
        )
        logger.warning("Execution failed (attempt %d): %s", attempt_no, result.get("error"))
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
    return {
        "execution_result": result,
        "rows_affected": result.get("row_count"),
        "error_message": None,
    }


# ---------------------------------------------------------------------------
# Node 9 — check_result
# ---------------------------------------------------------------------------
async def check_result(state: AgentState) -> dict:
    result = state.get("execution_result") or {}

    if not result.get("ok"):
        return {"result_validation": {"ok": False, "reason": result.get("error")}}

    operation = result.get("operation")
    row_count = result.get("row_count", 0)

    if operation == "SELECT" and row_count == 0:
        # Empty result is not an error — it can be a correct answer
        # ("no customers matched") — but flag it so final_answer phrases it clearly.
        return {"result_validation": {"ok": True, "reason": "empty_result_set"}}

    if operation in ("UPDATE", "DELETE") and row_count == 0:
        return {
            "result_validation": {
                "ok": False,
                "reason": "Statement executed but affected 0 rows — the WHERE clause may not match any data.",
            }
        }

    return {"result_validation": {"ok": True, "reason": None}}


def clean_markdown(text: str) -> str:
    # Remove bold/italic markers
    text = re.sub(r"\*\*+", "", text)
    # Convert list bullets to clean plain list markers
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
    result = state.get("execution_result") or {}
    operation = result.get("operation")

    if operation == "SELECT":
        rows, redacted = filter_sensitive_columns(result.get("rows", []))
        if redacted:
            logger.info("Redacted sensitive columns from LLM-facing result: %s", redacted)
        summary = f"{len(rows)} row(s):\n{rows[:20]}"  # cap what's shown to the LLM
        if redacted:
            summary += f"\nNote: The following sensitive columns were redacted for security: {', '.join(redacted)}."
    else:
        summary = f"{operation} affected {result.get('row_count', 0)} row(s)."

    answer = chat(
        FINAL_ANSWER_SYSTEM,
        build_final_answer_prompt(state["user_question"], summary),
        temperature=0.2,
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

    return {"final_answer": answer, "status": "success", "chat_history": chat_history}


# ---------------------------------------------------------------------------
# Node 11 — error_terminal (bounded retries exhausted, or hard rejection)
# ---------------------------------------------------------------------------
async def error_terminal(state: AgentState) -> dict:
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

    return {
        "final_answer": final_ans,
        "status": status,
        "chat_history": chat_history,
    }


# ---------------------------------------------------------------------------
# Node 12 — increment_retry (used on the loop-back edge)
# ---------------------------------------------------------------------------
async def increment_retry(state: AgentState) -> dict:
    return {"retry_count": state.get("retry_count", 0) + 1}
