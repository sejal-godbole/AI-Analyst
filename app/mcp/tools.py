"""
The actual tool implementations exposed by the MCP server.

This module owns no LLM logic — it's pure "controlled execution layer":
inspect the schema, or execute a SQL statement that has already passed
LangGraph-side validation and guardrails, after re-validating it here too
(defense in depth — the MCP server does not blindly trust its caller).
"""
from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.database.connection import get_connection
from app.database.schema_inspector import inspect_schema as _inspect_schema
from app.security.guardrails import evaluate_guardrails
from app.security.sql_validator import validate_sql


def tool_inspect_schema() -> dict:
    """MCP tool: inspect_schema. Returns table/column/PK/FK metadata only."""
    return _inspect_schema()


def tool_preview_query(sql: str) -> dict:
    """
    MCP tool: preview_query.
    Returns an EXPLAIN-based estimated row count for a statement WITHOUT
    executing it, so guardrails can decide whether confirmation is needed
    for broad UPDATE/DELETE statements.
    """
    schema = _inspect_schema()
    validation = validate_sql(sql, schema)
    if not validation.is_valid:
        return {"ok": False, "error": "; ".join(validation.errors)}

    explain_sql = f"EXPLAIN {sql.strip().rstrip(';')}"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(explain_sql)
                rows = cur.fetchall()
        # Parse the "rows=N" estimate out of all plan lines (taking the maximum).
        estimated_rows = None
        for row in rows:
            line = str(list(row.values())[0])
            if "rows=" in line:
                try:
                    val = int(line.split("rows=")[1].split(" ")[0])
                    if estimated_rows is None or val > estimated_rows:
                        estimated_rows = val
                except (ValueError, IndexError):
                    pass
        return {"ok": True, "estimated_rows": estimated_rows}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def tool_execute_query(sql: str, max_rows: int | None = None) -> dict[str, Any]:
    """
    MCP tool: execute_query.

    Re-validates SQL server-side (never trusts the caller), enforces the
    max-row limit for SELECTs, and executes within a transaction that is
    rolled back on any error.
    """
    settings = get_settings()
    max_rows = max_rows or settings.max_rows

    schema = _inspect_schema()
    validation = validate_sql(sql, schema)
    if not validation.is_valid:
        return {"ok": False, "error": "; ".join(validation.errors), "rows": [], "row_count": 0}

    decision = evaluate_guardrails(validation)
    if not decision.allowed:
        return {"ok": False, "error": decision.reason, "rows": [], "row_count": 0}

    clean_sql = sql.strip().rstrip(";")
    op = validation.operation

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                if op == "SELECT":
                    # Enforce a hard row cap even if the LLM forgot LIMIT.
                    capped_sql = f"SELECT * FROM ({clean_sql}) AS _sub LIMIT {max_rows}"
                    cur.execute(capped_sql)
                    rows = cur.fetchall()
                    conn.commit()
                    return {
                        "ok": True,
                        "operation": op,
                        "rows": [dict(r) for r in rows],
                        "row_count": len(rows),
                    }
                else:
                    cur.execute(clean_sql)
                    affected = cur.rowcount
                    conn.commit()
                    return {
                        "ok": True,
                        "operation": op,
                        "rows": [],
                        "row_count": affected,
                    }
    except Exception as e:
        return {"ok": False, "error": str(e), "rows": [], "row_count": 0}
