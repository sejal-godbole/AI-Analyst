"""
Observability storage layer.
Manages database persistence for traces, spans, and telemetry, along with
an in-memory ring buffer for low-latency live monitoring and metric aggregation.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import get_settings
from app.database.connection import get_connection
from app.observability.models import (
    DashboardMetrics,
    GuardrailRecord,
    LLMCallRecord,
    MCPCallRecord,
    SchemaChangeRecord,
    SpanRecord,
    TraceDetail,
    TraceSummary,
)

logger = logging.getLogger("ai_analyst.observability.store")

# Keep last 100 traces in memory for rapid live dashboard response
_LIVE_TRACES: dict[str, TraceDetail] = {}
_RECENT_TRACE_IDS: deque[str] = deque(maxlen=100)


def init_observability_db() -> None:
    """Initialize observability database tables if they do not exist."""
    queries = [
        """
        CREATE TABLE IF NOT EXISTS observability_traces (
            trace_id VARCHAR(128) PRIMARY KEY,
            thread_id VARCHAR(128),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            user_question TEXT NOT NULL,
            status VARCHAR(64) NOT NULL,
            final_answer TEXT,
            duration_ms DOUBLE PRECISION DEFAULT 0.0,
            total_tokens INTEGER DEFAULT 0,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            estimated_cost_usd DOUBLE PRECISION DEFAULT 0.0,
            first_attempt_success BOOLEAN DEFAULT TRUE,
            retry_count INTEGER DEFAULT 0,
            intent VARCHAR(64),
            sql_operation VARCHAR(64),
            intent_aligned BOOLEAN DEFAULT TRUE,
            guardrail_decision VARCHAR(64) DEFAULT 'ALLOWED',
            guardrail_reason TEXT,
            raw_sql TEXT,
            validated_sql TEXT,
            rows_affected INTEGER,
            error TEXT,
            langsmith_run_id VARCHAR(128),
            langsmith_url TEXT,
            mcp_validation_agreed BOOLEAN DEFAULT TRUE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS observability_spans (
            span_id VARCHAR(128) PRIMARY KEY,
            trace_id VARCHAR(128) NOT NULL REFERENCES observability_traces(trace_id) ON DELETE CASCADE,
            node_name VARCHAR(64) NOT NULL,
            span_type VARCHAR(64) NOT NULL,
            start_time TIMESTAMP WITH TIME ZONE NOT NULL,
            end_time TIMESTAMP WITH TIME ZONE,
            duration_ms DOUBLE PRECISION DEFAULT 0.0,
            status VARCHAR(64) NOT NULL,
            input_data JSONB,
            output_data JSONB,
            error TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS observability_llm_calls (
            call_id VARCHAR(128) PRIMARY KEY,
            trace_id VARCHAR(128) NOT NULL REFERENCES observability_traces(trace_id) ON DELETE CASCADE,
            node_name VARCHAR(64) NOT NULL,
            model VARCHAR(128) NOT NULL,
            system_prompt TEXT,
            user_prompt TEXT,
            response_text TEXT,
            duration_ms DOUBLE PRECISION DEFAULT 0.0,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            estimated_cost_usd DOUBLE PRECISION DEFAULT 0.0,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            error TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS observability_guardrails (
            record_id VARCHAR(128) PRIMARY KEY,
            trace_id VARCHAR(128) NOT NULL REFERENCES observability_traces(trace_id) ON DELETE CASCADE,
            decision VARCHAR(64) NOT NULL,
            rule_name VARCHAR(128) NOT NULL,
            reason TEXT NOT NULL,
            sql TEXT,
            estimated_rows INTEGER,
            user_decision VARCHAR(64),
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS observability_mcp_events (
            event_id VARCHAR(128) PRIMARY KEY,
            trace_id VARCHAR(128) NOT NULL REFERENCES observability_traces(trace_id) ON DELETE CASCADE,
            tool_name VARCHAR(128) NOT NULL,
            duration_ms DOUBLE PRECISION DEFAULT 0.0,
            ok BOOLEAN DEFAULT TRUE,
            rows_count INTEGER DEFAULT 0,
            error TEXT,
            langgraph_mcp_agreement BOOLEAN DEFAULT TRUE,
            subprocess_startup_ms DOUBLE PRECISION,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """
    ]

    alter_queries = [
        "ALTER TABLE observability_traces ALTER COLUMN trace_id TYPE VARCHAR(128);",
        "ALTER TABLE observability_spans ALTER COLUMN span_id TYPE VARCHAR(128), ALTER COLUMN trace_id TYPE VARCHAR(128);",
        "ALTER TABLE observability_llm_calls ALTER COLUMN call_id TYPE VARCHAR(128), ALTER COLUMN trace_id TYPE VARCHAR(128);",
        "ALTER TABLE observability_guardrails ALTER COLUMN record_id TYPE VARCHAR(128), ALTER COLUMN trace_id TYPE VARCHAR(128);",
        "ALTER TABLE observability_mcp_events ALTER COLUMN event_id TYPE VARCHAR(128), ALTER COLUMN trace_id TYPE VARCHAR(128);"
    ]

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                for q in queries:
                    cur.execute(q)
                for aq in alter_queries:
                    try:
                        cur.execute(aq)
                    except Exception:
                        pass
            conn.commit()
        logger.info("Observability database tables initialized successfully.")
    except Exception as e:
        logger.warning("Could not initialize observability database tables: %s", e)


def save_trace_detail(detail: TraceDetail) -> None:
    """Store or update trace in memory and PostgreSQL."""
    _LIVE_TRACES[detail.trace_id] = detail
    if detail.trace_id not in _RECENT_TRACE_IDS:
        _RECENT_TRACE_IDS.appendleft(detail.trace_id)

    # Persist to database
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Upsert into observability_traces
                upsert_sql = """
                INSERT INTO observability_traces (
                    trace_id, thread_id, user_question, status, final_answer,
                    duration_ms, total_tokens, prompt_tokens, completion_tokens,
                    estimated_cost_usd, first_attempt_success, retry_count,
                    intent, sql_operation, intent_aligned, guardrail_decision,
                    guardrail_reason, raw_sql, validated_sql, rows_affected,
                    error, langsmith_run_id, langsmith_url, mcp_validation_agreed
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (trace_id) DO UPDATE SET
                    thread_id = EXCLUDED.thread_id,
                    status = EXCLUDED.status,
                    final_answer = EXCLUDED.final_answer,
                    duration_ms = EXCLUDED.duration_ms,
                    total_tokens = EXCLUDED.total_tokens,
                    prompt_tokens = EXCLUDED.prompt_tokens,
                    completion_tokens = EXCLUDED.completion_tokens,
                    estimated_cost_usd = EXCLUDED.estimated_cost_usd,
                    first_attempt_success = EXCLUDED.first_attempt_success,
                    retry_count = EXCLUDED.retry_count,
                    intent = EXCLUDED.intent,
                    sql_operation = EXCLUDED.sql_operation,
                    intent_aligned = EXCLUDED.intent_aligned,
                    guardrail_decision = EXCLUDED.guardrail_decision,
                    guardrail_reason = EXCLUDED.guardrail_reason,
                    raw_sql = EXCLUDED.raw_sql,
                    validated_sql = EXCLUDED.validated_sql,
                    rows_affected = EXCLUDED.rows_affected,
                    error = EXCLUDED.error,
                    langsmith_run_id = EXCLUDED.langsmith_run_id,
                    langsmith_url = EXCLUDED.langsmith_url,
                    mcp_validation_agreed = EXCLUDED.mcp_validation_agreed;
                """
                cur.execute(
                    upsert_sql,
                    (
                        detail.trace_id,
                        detail.thread_id,
                        detail.user_question,
                        detail.status,
                        detail.final_answer,
                        detail.duration_ms,
                        detail.total_tokens,
                        detail.prompt_tokens,
                        detail.completion_tokens,
                        detail.estimated_cost_usd,
                        detail.first_attempt_success,
                        detail.retry_count,
                        detail.intent,
                        detail.sql_operation,
                        detail.intent_aligned,
                        detail.guardrail_decision,
                        detail.guardrail_reason,
                        detail.raw_sql,
                        detail.validated_sql,
                        detail.rows_affected,
                        detail.error,
                        detail.langsmith_run_id,
                        detail.langsmith_url,
                        detail.mcp_validation_agreed,
                    ),
                )

                # Insert spans
                for span in detail.spans:
                    cur.execute(
                        """
                        INSERT INTO observability_spans (
                            span_id, trace_id, node_name, span_type, start_time,
                            end_time, duration_ms, status, input_data, output_data, error
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (span_id) DO UPDATE SET
                            end_time = EXCLUDED.end_time,
                            duration_ms = EXCLUDED.duration_ms,
                            status = EXCLUDED.status,
                            output_data = EXCLUDED.output_data,
                            error = EXCLUDED.error;
                        """,
                        (
                            span.span_id,
                            span.trace_id,
                            span.node_name,
                            span.span_type,
                            span.start_time,
                            span.end_time,
                            span.duration_ms,
                            span.status,
                            json.dumps(span.input_data) if span.input_data else None,
                            json.dumps(span.output_data) if span.output_data else None,
                            span.error,
                        ),
                    )

                # Insert LLM calls
                for llm in detail.llm_calls:
                    cur.execute(
                        """
                        INSERT INTO observability_llm_calls (
                            call_id, trace_id, node_name, model, system_prompt,
                            user_prompt, response_text, duration_ms, prompt_tokens,
                            completion_tokens, total_tokens, estimated_cost_usd,
                            timestamp, error
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (call_id) DO NOTHING;
                        """,
                        (
                            llm.call_id,
                            llm.trace_id,
                            llm.node_name,
                            llm.model,
                            llm.system_prompt,
                            llm.user_prompt,
                            llm.response_text,
                            llm.duration_ms,
                            llm.prompt_tokens,
                            llm.completion_tokens,
                            llm.total_tokens,
                            llm.estimated_cost_usd,
                            llm.timestamp,
                            llm.error,
                        ),
                    )

                # Insert Guardrail records
                for gr in detail.guardrail_records:
                    cur.execute(
                        """
                        INSERT INTO observability_guardrails (
                            record_id, trace_id, decision, rule_name, reason,
                            sql, estimated_rows, user_decision, timestamp
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (record_id) DO NOTHING;
                        """,
                        (
                            gr.record_id,
                            gr.trace_id,
                            gr.decision,
                            gr.rule_name,
                            gr.reason,
                            gr.sql,
                            gr.estimated_rows,
                            gr.user_decision,
                            gr.timestamp,
                        ),
                    )

                # Insert MCP events
                for mcp in detail.mcp_calls:
                    cur.execute(
                        """
                        INSERT INTO observability_mcp_events (
                            event_id, trace_id, tool_name, duration_ms, ok,
                            rows_count, error, langgraph_mcp_agreement,
                            subprocess_startup_ms, timestamp
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (event_id) DO NOTHING;
                        """,
                        (
                            mcp.event_id,
                            mcp.trace_id,
                            mcp.tool_name,
                            mcp.duration_ms,
                            mcp.ok,
                            mcp.rows_count,
                            mcp.error,
                            mcp.langgraph_mcp_agreement,
                            mcp.subprocess_startup_ms,
                            mcp.timestamp,
                        ),
                    )

            conn.commit()
    except Exception as e:
        logger.warning("Failed to persist trace to database (kept in-memory): %s", e)


def get_trace_by_id(trace_id: str) -> Optional[TraceDetail]:
    """Retrieve full trace details."""
    if trace_id in _LIVE_TRACES:
        detail = _LIVE_TRACES[trace_id]
        if not detail.evaluation:
            try:
                from app.evaluation.store import get_live_evaluation
                eval_record = get_live_evaluation(trace_id)
                if eval_record:
                    detail.evaluation = eval_record.model_dump()
            except Exception:
                pass
        return detail

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM observability_traces WHERE trace_id = %s", (trace_id,))
                trace_row = cur.fetchone()
                if not trace_row:
                    return None

                cur.execute("SELECT * FROM observability_spans WHERE trace_id = %s ORDER BY start_time ASC", (trace_id,))
                span_rows = cur.fetchall()

                cur.execute("SELECT * FROM observability_llm_calls WHERE trace_id = %s ORDER BY timestamp ASC", (trace_id,))
                llm_rows = cur.fetchall()

                cur.execute("SELECT * FROM observability_guardrails WHERE trace_id = %s ORDER BY timestamp ASC", (trace_id,))
                gr_rows = cur.fetchall()

                cur.execute("SELECT * FROM observability_mcp_events WHERE trace_id = %s ORDER BY timestamp ASC", (trace_id,))
                mcp_rows = cur.fetchall()

                detail = TraceDetail(
                    trace_id=trace_row["trace_id"],
                    thread_id=trace_row.get("thread_id"),
                    created_at=trace_row["created_at"].isoformat() if hasattr(trace_row["created_at"], "isoformat") else str(trace_row["created_at"]),
                    user_question=trace_row["user_question"],
                    status=trace_row["status"],
                    final_answer=trace_row.get("final_answer"),
                    duration_ms=trace_row.get("duration_ms", 0.0),
                    total_tokens=trace_row.get("total_tokens", 0),
                    prompt_tokens=trace_row.get("prompt_tokens", 0),
                    completion_tokens=trace_row.get("completion_tokens", 0),
                    estimated_cost_usd=trace_row.get("estimated_cost_usd", 0.0),
                    first_attempt_success=trace_row.get("first_attempt_success", True),
                    retry_count=trace_row.get("retry_count", 0),
                    intent=trace_row.get("intent"),
                    sql_operation=trace_row.get("sql_operation"),
                    intent_aligned=trace_row.get("intent_aligned", True),
                    guardrail_decision=trace_row.get("guardrail_decision"),
                    guardrail_reason=trace_row.get("guardrail_reason"),
                    raw_sql=trace_row.get("raw_sql"),
                    validated_sql=trace_row.get("validated_sql"),
                    rows_affected=trace_row.get("rows_affected"),
                    error=trace_row.get("error"),
                    langsmith_run_id=trace_row.get("langsmith_run_id"),
                    langsmith_url=trace_row.get("langsmith_url"),
                    mcp_validation_agreed=trace_row.get("mcp_validation_agreed", True),
                    spans=[
                        SpanRecord(
                            span_id=r["span_id"],
                            trace_id=r["trace_id"],
                            node_name=r["node_name"],
                            span_type=r["span_type"],
                            start_time=r["start_time"].isoformat() if hasattr(r["start_time"], "isoformat") else str(r["start_time"]),
                            end_time=r["end_time"].isoformat() if r.get("end_time") and hasattr(r["end_time"], "isoformat") else str(r.get("end_time")),
                            duration_ms=r.get("duration_ms", 0.0),
                            status=r.get("status", "completed"),
                            input_data=r.get("input_data"),
                            output_data=r.get("output_data"),
                            error=r.get("error"),
                        )
                        for r in span_rows
                    ],
                    llm_calls=[
                        LLMCallRecord(
                            call_id=r["call_id"],
                            trace_id=r["trace_id"],
                            node_name=r["node_name"],
                            model=r["model"],
                            system_prompt=r["system_prompt"] or "",
                            user_prompt=r["user_prompt"] or "",
                            response_text=r["response_text"] or "",
                            duration_ms=r.get("duration_ms", 0.0),
                            prompt_tokens=r.get("prompt_tokens", 0),
                            completion_tokens=r.get("completion_tokens", 0),
                            total_tokens=r.get("total_tokens", 0),
                            estimated_cost_usd=r.get("estimated_cost_usd", 0.0),
                            timestamp=r["timestamp"].isoformat() if hasattr(r["timestamp"], "isoformat") else str(r["timestamp"]),
                            error=r.get("error"),
                        )
                        for r in llm_rows
                    ],
                    guardrail_records=[
                        GuardrailRecord(
                            record_id=r["record_id"],
                            trace_id=r["trace_id"],
                            decision=r["decision"],
                            rule_name=r["rule_name"],
                            reason=r["reason"],
                            sql=r.get("sql"),
                            estimated_rows=r.get("estimated_rows"),
                            user_decision=r.get("user_decision"),
                            timestamp=r["timestamp"].isoformat() if hasattr(r["timestamp"], "isoformat") else str(r["timestamp"]),
                        )
                        for r in gr_rows
                    ],
                    mcp_calls=[
                        MCPCallRecord(
                            event_id=r["event_id"],
                            trace_id=r["trace_id"],
                            tool_name=r["tool_name"],
                            duration_ms=r.get("duration_ms", 0.0),
                            ok=r.get("ok", True),
                            rows_count=r.get("rows_count", 0),
                            error=r.get("error"),
                            langgraph_mcp_agreement=r.get("langgraph_mcp_agreement", True),
                            subprocess_startup_ms=r.get("subprocess_startup_ms"),
                            timestamp=r["timestamp"].isoformat() if hasattr(r["timestamp"], "isoformat") else str(r["timestamp"]),
                        )
                        for r in mcp_rows
                    ],
                )

                try:
                    from app.evaluation.store import get_live_evaluation
                    eval_record = get_live_evaluation(trace_id)
                    if eval_record:
                        detail.evaluation = eval_record.model_dump()
                except Exception:
                    pass

                _LIVE_TRACES[trace_id] = detail
                return detail
    except Exception as e:
        logger.warning("Error fetching trace %s: %s", trace_id, e)
        return None


def list_traces(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    intent: Optional[str] = None,
    search: Optional[str] = None,
) -> list[TraceSummary]:
    """List recent trace summaries with optional filters."""
    # First try PostgreSQL
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                where_clauses = []
                params: list[Any] = []

                if status and status != "all":
                    where_clauses.append("status = %s")
                    params.append(status)
                else:
                    where_clauses.append("status != 'running'")
                if intent and intent != "all":
                    where_clauses.append("intent = %s")
                    params.append(intent)
                if search:
                    where_clauses.append("(user_question ILIKE %s OR trace_id ILIKE %s OR raw_sql ILIKE %s)")
                    params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
                query = f"""
                SELECT trace_id, thread_id, created_at, user_question, status, final_answer,
                       duration_ms, total_tokens, prompt_tokens, completion_tokens,
                       estimated_cost_usd, first_attempt_success, retry_count, intent,
                       sql_operation, intent_aligned, guardrail_decision, guardrail_reason,
                       raw_sql, validated_sql, rows_affected, error, langsmith_run_id,
                       langsmith_url, mcp_validation_agreed
                FROM observability_traces
                {where_sql}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """
                params.extend([limit, offset])
                cur.execute(query, params)
                rows = cur.fetchall()

                return [
                    TraceSummary(
                        trace_id=r["trace_id"],
                        thread_id=r.get("thread_id"),
                        created_at=r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
                        user_question=r["user_question"],
                        status=r["status"],
                        final_answer=r.get("final_answer"),
                        duration_ms=r.get("duration_ms", 0.0),
                        total_tokens=r.get("total_tokens", 0),
                        prompt_tokens=r.get("prompt_tokens", 0),
                        completion_tokens=r.get("completion_tokens", 0),
                        estimated_cost_usd=r.get("estimated_cost_usd", 0.0),
                        first_attempt_success=r.get("first_attempt_success", True),
                        retry_count=r.get("retry_count", 0),
                        intent=r.get("intent"),
                        sql_operation=r.get("sql_operation"),
                        intent_aligned=r.get("intent_aligned", True),
                        guardrail_decision=r.get("guardrail_decision"),
                        guardrail_reason=r.get("guardrail_reason"),
                        raw_sql=r.get("raw_sql"),
                        validated_sql=r.get("validated_sql"),
                        rows_affected=r.get("rows_affected"),
                        error=r.get("error"),
                        langsmith_run_id=r.get("langsmith_run_id"),
                        langsmith_url=r.get("langsmith_url"),
                        mcp_validation_agreed=r.get("mcp_validation_agreed", True),
                    )
                    for r in rows
                ]
    except Exception as e:
        logger.warning("DB trace listing error (falling back to memory): %s", e)

    # In-memory fallback
    results: list[TraceSummary] = []
    for tid in _RECENT_TRACE_IDS:
        t = _LIVE_TRACES.get(tid)
        if not t:
            continue
        if status and status != "all" and t.status != status:
            continue
        if intent and intent != "all" and t.intent != intent:
            continue
        if search and search.lower() not in t.user_question.lower() and search.lower() not in t.trace_id.lower():
            continue
        results.append(t)
    return results[offset : offset + limit]


def get_live_traces() -> list[TraceDetail]:
    """Returns in-memory recent / in-flight traces for live node visualization."""
    return [
        _LIVE_TRACES[tid]
        for tid in _RECENT_TRACE_IDS
        if tid in _LIVE_TRACES
    ][:10]


def calculate_metrics() -> DashboardMetrics:
    """Computes full aggregated metrics for all 6 Dashboard areas."""
    traces = list_traces(limit=200)
    if not traces:
        return DashboardMetrics()

    total_reqs = len(traces)
    success_reqs = sum(1 for t in traces if t.status == "success")
    failed_reqs = sum(1 for t in traces if t.status == "error")
    rejected_reqs = sum(1 for t in traces if t.status == "rejected")

    durations = [t.duration_ms for t in traces if t.duration_ms > 0]
    durations.sort()
    avg_latency = sum(durations) / len(durations) if durations else 0.0
    p95_idx = int(len(durations) * 0.95) if durations else 0
    p95_latency = durations[min(p95_idx, len(durations) - 1)] if durations else 0.0

    # LLM Metrics
    first_attempt_count = sum(1 for t in traces if t.first_attempt_success)
    first_attempt_rate = (first_attempt_count / total_reqs * 100.0) if total_reqs else 100.0
    retry_count_total = sum(t.retry_count for t in traces)
    retry_rate = (sum(1 for t in traces if t.retry_count > 0) / total_reqs * 100.0) if total_reqs else 0.0

    prompt_tokens = sum(t.prompt_tokens for t in traces)
    completion_tokens = sum(t.completion_tokens for t in traces)
    total_tokens = sum(t.total_tokens for t in traces)
    total_cost = sum(t.estimated_cost_usd for t in traces)

    # Collect all detailed spans, LLM calls, guardrail events for loaded traces
    all_spans: list[SpanRecord] = []
    all_llm_calls: list[LLMCallRecord] = []
    all_guardrails: list[GuardrailRecord] = []
    all_mcp_calls: list[MCPCallRecord] = []

    for t in traces[:50]:
        detail = get_trace_by_id(t.trace_id)
        if detail:
            all_spans.extend(detail.spans)
            all_llm_calls.extend(detail.llm_calls)
            all_guardrails.extend(detail.guardrail_records)
            all_mcp_calls.extend(detail.mcp_calls)

    # LLM Latency
    llm_durations = [c.duration_ms for c in all_llm_calls if c.duration_ms > 0]
    llm_durations.sort()
    avg_llm_lat = sum(llm_durations) / len(llm_durations) if llm_durations else 0.0
    p95_llm_idx = int(len(llm_durations) * 0.95) if llm_durations else 0
    p95_llm_lat = llm_durations[min(p95_llm_idx, len(llm_durations) - 1)] if llm_durations else 0.0

    # Node metrics
    node_stats: dict[str, dict[str, Any]] = {}
    for span in all_spans:
        if span.span_type == "node":
            entry = node_stats.setdefault(
                span.node_name,
                {"execution_count": 0, "total_duration": 0.0, "failures": 0, "retries": 0},
            )
            entry["execution_count"] += 1
            entry["total_duration"] += span.duration_ms
            if span.status == "failed":
                entry["failures"] += 1
            if span.status == "retried":
                entry["retries"] += 1

    for n, s in node_stats.items():
        s["avg_latency_ms"] = round(s["total_duration"] / max(1, s["execution_count"]), 2)

    # Guardrails
    allowed_count = sum(1 for g in all_guardrails if g.decision == "ALLOWED") + sum(1 for t in traces if t.guardrail_decision == "ALLOWED")
    blocked_count = sum(1 for g in all_guardrails if g.decision == "BLOCKED") + sum(1 for t in traces if t.guardrail_decision == "BLOCKED")
    confirm_count = sum(1 for g in all_guardrails if g.decision == "CONFIRMATION_REQUIRED") + sum(1 for t in traces if t.guardrail_decision == "CONFIRMATION_REQUIRED")
    total_gr_checks = max(1, allowed_count + blocked_count + confirm_count)
    rejection_rate = round((blocked_count / total_gr_checks) * 100.0, 2)

    rule_counts: dict[str, int] = {}
    for g in all_guardrails:
        rule_counts[g.rule_name] = rule_counts.get(g.rule_name, 0) + 1

    # MCP
    mcp_total = len(all_mcp_calls)
    mcp_ok = sum(1 for m in all_mcp_calls if m.ok)
    mcp_success_rate = (mcp_ok / mcp_total * 100.0) if mcp_total else 100.0
    mcp_latencies = [m.duration_ms for m in all_mcp_calls if m.duration_ms > 0]
    avg_mcp_lat = sum(mcp_latencies) / len(mcp_latencies) if mcp_latencies else 0.0
    mcp_agreed = sum(1 for m in all_mcp_calls if m.langgraph_mcp_agreement)
    mcp_agreement_rate = (mcp_agreed / mcp_total * 100.0) if mcp_total else 100.0

    # Database
    total_rows = sum(t.rows_affected or 0 for t in traces)
    db_exec_calls = [m for m in all_mcp_calls if m.tool_name == "execute_query"]
    db_durations = [m.duration_ms for m in db_exec_calls]
    avg_db_query_time = sum(db_durations) / len(db_durations) if db_durations else 0.0
    db_errors = sum(1 for m in db_exec_calls if not m.ok)

    return DashboardMetrics(
        total_requests=total_reqs,
        successful_requests=success_reqs,
        failed_requests=failed_reqs,
        rejected_requests=rejected_reqs,
        avg_end_to_end_latency_ms=round(avg_latency, 2),
        p95_end_to_end_latency_ms=round(p95_latency, 2),
        total_llm_calls=len(all_llm_calls) or total_reqs,
        first_attempt_sql_success_rate=round(first_attempt_rate, 2),
        retry_rate=round(retry_rate, 2),
        avg_llm_latency_ms=round(avg_llm_lat, 2),
        p95_llm_latency_ms=round(p95_llm_lat, 2),
        total_prompt_tokens=prompt_tokens,
        total_completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        total_estimated_cost_usd=round(total_cost, 6),
        node_metrics=node_stats,
        guardrails_allowed=allowed_count,
        guardrails_blocked=blocked_count,
        guardrails_confirmation_required=confirm_count,
        guardrail_rejection_rate=rejection_rate,
        rule_breakdown=rule_counts,
        mcp_calls_count=mcp_total,
        mcp_success_rate=round(mcp_success_rate, 2),
        avg_mcp_latency_ms=round(avg_mcp_lat, 2),
        mcp_subprocess_failures=sum(1 for m in all_mcp_calls if m.subprocess_startup_ms is not None and not m.ok),
        mcp_agreement_rate=round(mcp_agreement_rate, 2),
        total_rows_affected=total_rows,
        avg_db_query_time_ms=round(avg_db_query_time, 2),
        database_errors_count=db_errors,
    )
