"""
Core Observability Tracer and LangSmith Integration Engine.
Coordinates spans, LLM calls, guardrail evaluations, and MCP events for each request.
"""
from __future__ import annotations

import contextvars
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import get_settings
from app.observability.models import (
    GuardrailRecord,
    LLMCallRecord,
    MCPCallRecord,
    SpanRecord,
    TraceDetail,
)
from app.observability.pricing import estimate_llm_cost
from app.observability.store import save_trace_detail

logger = logging.getLogger("ai_analyst.observability.tracer")

# Request-scoped ContextVar to hold current trace ID
_current_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_current_trace_id", default=None
)

# In-memory tracking of active traces
_active_traces: dict[str, TraceDetail] = {}
_active_spans: dict[str, SpanRecord] = {}


def get_current_trace_id() -> Optional[str]:
    return _current_trace_id.get()


def set_current_trace_id(trace_id: str) -> None:
    _current_trace_id.set(trace_id)


class Tracer:
    def __init__(self):
        self._langsmith_client = None
        self._init_langsmith()

    def _init_langsmith(self):
        settings = get_settings()
        api_key = getattr(settings, "langsmith_api_key", "") or os.getenv("LANGSMITH_API_KEY", "")
        tracing_enabled = (
            getattr(settings, "langsmith_tracing", False)
            or os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
        )

        if tracing_enabled and api_key:
            try:
                from langsmith import Client
                endpoint = getattr(settings, "langsmith_endpoint", "https://api.smith.langchain.com") or os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
                self._langsmith_client = Client(api_key=api_key, api_url=endpoint)
                logger.info("LangSmith client initialized for project: %s", getattr(settings, "langsmith_project", "ai-analyst-agent"))
            except Exception as e:
                logger.warning("Failed to initialize LangSmith client: %s", e)
                self._langsmith_client = None

    def start_trace(self, trace_id: str, user_question: str, thread_id: Optional[str] = None) -> TraceDetail:
        now_iso = datetime.now(timezone.utc).isoformat()
        detail = TraceDetail(
            trace_id=trace_id,
            thread_id=thread_id,
            created_at=now_iso,
            user_question=user_question,
            status="running",
        )
        _active_traces[trace_id] = detail
        set_current_trace_id(trace_id)

        # Create root LangSmith run if client is available
        if self._langsmith_client:
            try:
                settings = get_settings()
                project = getattr(settings, "langsmith_project", "ai-analyst-agent") or "ai-analyst-agent"
                run = self._langsmith_client.create_run(
                    name="ai_analyst_request",
                    run_type="chain",
                    inputs={"user_question": user_question, "thread_id": thread_id},
                    project_name=project,
                    id=trace_id,
                    metadata={"thread_id": thread_id, "trace_id": trace_id},
                )
                detail.langsmith_run_id = str(trace_id)
                detail.langsmith_url = f"https://smith.langchain.com/o/default/projects/p/{project}/r/{trace_id}"
            except Exception as e:
                logger.debug("LangSmith start_trace run creation skipped: %s", e)

        save_trace_detail(detail)
        return detail

    def start_span(
        self,
        node_name: str,
        span_type: str = "node",
        input_data: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> SpanRecord:
        tid = trace_id or get_current_trace_id() or str(uuid.uuid4())
        span_id = f"{tid}_{node_name}_{int(time.time() * 1000)}"
        now_iso = datetime.now(timezone.utc).isoformat()

        span = SpanRecord(
            span_id=span_id,
            trace_id=tid,
            node_name=node_name,
            span_type=span_type,
            start_time=now_iso,
            status="running",
            input_data=input_data,
        )
        _active_spans[span_id] = span

        trace = _active_traces.get(tid)
        if trace:
            # If there's an existing running span for the same node (e.g. before interrupt), reuse it
            existing = next((s for s in reversed(trace.spans) if s.node_name == node_name and s.status == "running"), None)
            if existing:
                _active_spans[existing.span_id] = existing
                return existing

            trace.spans.append(span)
            
            # Send child span to LangSmith
            if self._langsmith_client and trace.langsmith_run_id:
                try:
                    span_run_id = str(uuid.uuid4())
                    self._langsmith_client.create_run(
                        name=f"Node: {node_name}",
                        run_type="tool" if span_type == "mcp" else "chain",
                        inputs=input_data or {},
                        parent_run_id=trace.langsmith_run_id,
                        project_name=getattr(get_settings(), "langsmith_project", "ai-analyst-agent") or "ai-analyst-agent",
                        id=span_run_id,
                        metadata={"node_name": node_name, "trace_id": tid},
                    )
                    span.metadata = span.metadata or {}
                    span.metadata["langsmith_run_id"] = span_run_id
                except Exception as e:
                    logger.debug("LangSmith span creation skipped: %s", e)

            save_trace_detail(trace)

        return span

    def end_span(
        self,
        span_id: str,
        output_data: Optional[dict[str, Any]] = None,
        status: str = "completed",
        error: Optional[str] = None,
    ) -> Optional[SpanRecord]:
        span = _active_spans.get(span_id)
        if not span:
            return None

        now_dt = datetime.now(timezone.utc)
        start_dt = datetime.fromisoformat(span.start_time.replace("Z", "+00:00"))
        duration_ms = (now_dt - start_dt).total_seconds() * 1000.0

        span.end_time = now_dt.isoformat()
        span.duration_ms = round(duration_ms, 2)
        span.status = status
        span.output_data = output_data
        span.error = error

        # Update child span in LangSmith
        if self._langsmith_client and span.metadata and "langsmith_run_id" in span.metadata:
            try:
                self._langsmith_client.update_run(
                    run_id=span.metadata["langsmith_run_id"],
                    outputs=output_data or {"status": status},
                    error=error,
                    end_time=now_dt,
                )
            except Exception as e:
                logger.debug("LangSmith span update skipped: %s", e)

        trace = _active_traces.get(span.trace_id)
        if trace:
            save_trace_detail(trace)

        return span

    def record_llm_call(
        self,
        node_name: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_text: str,
        duration_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        error: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> LLMCallRecord:
        tid = trace_id or get_current_trace_id() or str(uuid.uuid4())
        call_id = f"llm_{tid}_{int(time.time() * 1000)}"
        cost_usd = estimate_llm_cost(model, prompt_tokens, completion_tokens)

        record = LLMCallRecord(
            call_id=call_id,
            trace_id=tid,
            node_name=node_name,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_text=response_text,
            duration_ms=round(duration_ms, 2),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens or (prompt_tokens + completion_tokens),
            estimated_cost_usd=cost_usd,
            timestamp=datetime.now(timezone.utc).isoformat(),
            error=error,
        )

        trace = _active_traces.get(tid)
        if trace:
            trace.llm_calls.append(record)
            trace.prompt_tokens += prompt_tokens
            trace.completion_tokens += completion_tokens
            trace.total_tokens += (total_tokens or (prompt_tokens + completion_tokens))
            trace.estimated_cost_usd = round(trace.estimated_cost_usd + cost_usd, 8)

            # Send LLM generation run to LangSmith
            if self._langsmith_client and trace.langsmith_run_id:
                try:
                    llm_run_id = str(uuid.uuid4())
                    project_name = getattr(get_settings(), "langsmith_project", "ai-analyst-agent") or "ai-analyst-agent"
                    self._langsmith_client.create_run(
                        name=f"LLM: {node_name}",
                        run_type="llm",
                        inputs={
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ]
                        },
                        parent_run_id=trace.langsmith_run_id,
                        project_name=project_name,
                        id=llm_run_id,
                        extra={"metadata": {"model": model, "cost_usd": cost_usd, "total_tokens": record.total_tokens}},
                    )
                    self._langsmith_client.update_run(
                        run_id=llm_run_id,
                        outputs={"generations": [{"text": response_text}]},
                        error=error,
                        end_time=datetime.now(timezone.utc),
                    )
                except Exception as e:
                    logger.debug("LangSmith LLM run skipped: %s", e)

            save_trace_detail(trace)

        return record

    def record_guardrail_decision(
        self,
        decision: str,
        rule_name: str,
        reason: str,
        sql: Optional[str] = None,
        estimated_rows: Optional[int] = None,
        user_decision: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> GuardrailRecord:
        tid = trace_id or get_current_trace_id() or str(uuid.uuid4())
        record_id = f"gr_{tid}_{int(time.time() * 1000)}"

        record = GuardrailRecord(
            record_id=record_id,
            trace_id=tid,
            decision=decision,
            rule_name=rule_name,
            reason=reason,
            sql=sql,
            estimated_rows=estimated_rows,
            user_decision=user_decision,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        trace = _active_traces.get(tid)
        if trace:
            trace.guardrail_records.append(record)
            trace.guardrail_decision = decision
            trace.guardrail_reason = reason
            save_trace_detail(trace)

        return record

    def record_mcp_call(
        self,
        tool_name: str,
        duration_ms: float,
        ok: bool,
        rows_count: int = 0,
        error: Optional[str] = None,
        langgraph_mcp_agreement: bool = True,
        subprocess_startup_ms: Optional[float] = None,
        trace_id: Optional[str] = None,
    ) -> MCPCallRecord:
        tid = trace_id or get_current_trace_id() or str(uuid.uuid4())
        event_id = f"mcp_{tid}_{int(time.time() * 1000)}"

        record = MCPCallRecord(
            event_id=event_id,
            trace_id=tid,
            tool_name=tool_name,
            duration_ms=round(duration_ms, 2),
            ok=ok,
            rows_count=rows_count,
            error=error,
            langgraph_mcp_agreement=langgraph_mcp_agreement,
            subprocess_startup_ms=subprocess_startup_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        trace = _active_traces.get(tid)
        if trace:
            trace.mcp_calls.append(record)
            if not langgraph_mcp_agreement:
                trace.mcp_validation_agreed = False
            save_trace_detail(trace)

        return record

    def end_trace(
        self,
        trace_id: str,
        final_answer: Optional[str] = None,
        status: str = "success",
        error: Optional[str] = None,
        validated_sql: Optional[str] = None,
        raw_sql: Optional[str] = None,
        rows_affected: Optional[int] = None,
        intent: Optional[str] = None,
        sql_operation: Optional[str] = None,
        retry_count: int = 0,
    ) -> Optional[TraceDetail]:
        trace = _active_traces.get(trace_id)
        if not trace:
            return None

        now_dt = datetime.now(timezone.utc)
        start_dt = datetime.fromisoformat(trace.created_at.replace("Z", "+00:00"))
        duration_ms = (now_dt - start_dt).total_seconds() * 1000.0

        trace.final_answer = final_answer
        trace.status = status
        trace.error = error
        trace.validated_sql = validated_sql
        trace.raw_sql = raw_sql or trace.raw_sql
        trace.rows_affected = rows_affected
        trace.intent = intent or trace.intent
        trace.sql_operation = sql_operation or trace.sql_operation
        trace.retry_count = retry_count
        trace.first_attempt_success = (retry_count == 0 and status == "success")
        trace.duration_ms = round(duration_ms, 2)

        # Check intent alignment
        if trace.intent and trace.sql_operation:
            # e.g., READ -> SELECT, INSERT -> INSERT, UPDATE -> UPDATE, DELETE -> DELETE
            expected_op = "SELECT" if trace.intent == "READ" else trace.intent
            trace.intent_aligned = (expected_op == trace.sql_operation)

        # Update root LangSmith run if available
        if self._langsmith_client and trace.langsmith_run_id:
            try:
                self._langsmith_client.update_run(
                    run_id=trace.langsmith_run_id,
                    outputs={
                        "answer": final_answer,
                        "status": status,
                        "sql": validated_sql,
                        "rows_affected": rows_affected,
                    },
                    error=error,
                    end_time=now_dt,
                )
            except Exception as e:
                logger.debug("LangSmith update_run skipped: %s", e)

        save_trace_detail(trace)
        return trace


# Global singleton instance
tracer = Tracer()
