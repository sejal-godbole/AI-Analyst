"""
Data models and TypedDicts for the Observability & Telemetry subsystem.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class SpanRecord(BaseModel):
    span_id: str
    trace_id: str
    node_name: str
    span_type: str  # "node" | "llm" | "mcp" | "guardrail"
    start_time: str
    end_time: Optional[str] = None
    duration_ms: float = 0.0
    status: str = "running"  # "running" | "completed" | "failed" | "retried" | "blocked" | "needs_confirmation"
    input_data: Optional[dict[str, Any]] = None
    output_data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class LLMCallRecord(BaseModel):
    call_id: str
    trace_id: str
    node_name: str
    model: str
    system_prompt: str
    user_prompt: str
    response_text: str
    duration_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    timestamp: str
    error: Optional[str] = None


class GuardrailRecord(BaseModel):
    record_id: str
    trace_id: str
    decision: str  # "ALLOWED" | "BLOCKED" | "CONFIRMATION_REQUIRED"
    rule_name: str
    reason: str
    sql: Optional[str] = None
    estimated_rows: Optional[int] = None
    user_decision: Optional[str] = None  # "approved" | "rejected" | None
    timestamp: str


class MCPCallRecord(BaseModel):
    event_id: str
    trace_id: str
    tool_name: str  # "inspect_schema" | "preview_query" | "execute_query"
    duration_ms: float
    ok: bool
    rows_count: int = 0
    error: Optional[str] = None
    langgraph_mcp_agreement: bool = True
    subprocess_startup_ms: Optional[float] = None
    timestamp: str


class TraceSummary(BaseModel):
    trace_id: str
    thread_id: Optional[str] = None
    created_at: str
    user_question: str
    status: str  # "success" | "error" | "rejected" | "awaiting_confirmation"
    final_answer: Optional[str] = None
    duration_ms: float = 0.0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0
    first_attempt_success: bool = True
    retry_count: int = 0
    intent: Optional[str] = None
    sql_operation: Optional[str] = None
    intent_aligned: bool = True
    guardrail_decision: Optional[str] = "ALLOWED"
    guardrail_reason: Optional[str] = None
    raw_sql: Optional[str] = None
    validated_sql: Optional[str] = None
    rows_affected: Optional[int] = None
    error: Optional[str] = None
    langsmith_run_id: Optional[str] = None
    langsmith_url: Optional[str] = None
    mcp_validation_agreed: bool = True


class TraceDetail(TraceSummary):
    spans: list[SpanRecord] = Field(default_factory=list)
    llm_calls: list[LLMCallRecord] = Field(default_factory=list)
    guardrail_records: list[GuardrailRecord] = Field(default_factory=list)
    mcp_calls: list[MCPCallRecord] = Field(default_factory=list)


class DashboardMetrics(BaseModel):
    # Area 1: Requests
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0
    avg_end_to_end_latency_ms: float = 0.0
    p95_end_to_end_latency_ms: float = 0.0

    # Area 2: LLM
    total_llm_calls: int = 0
    first_attempt_sql_success_rate: float = 100.0
    retry_rate: float = 0.0
    avg_llm_latency_ms: float = 0.0
    p95_llm_latency_ms: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_estimated_cost_usd: float = 0.0

    # Area 3: LangGraph Nodes
    node_metrics: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # e.g. {"generate_sql": {"execution_count": 10, "avg_latency_ms": 320.5, "failures": 0, "retries": 1}}

    # Area 4: Guardrails
    guardrails_allowed: int = 0
    guardrails_blocked: int = 0
    guardrails_confirmation_required: int = 0
    guardrail_rejection_rate: float = 0.0
    rule_breakdown: dict[str, int] = Field(default_factory=dict)

    # Area 5: MCP
    mcp_calls_count: int = 0
    mcp_success_rate: float = 100.0
    avg_mcp_latency_ms: float = 0.0
    mcp_subprocess_failures: int = 0
    mcp_agreement_rate: float = 100.0

    # Area 6: Database
    total_rows_affected: int = 0
    avg_db_query_time_ms: float = 0.0
    database_errors_count: int = 0


class SchemaChangeRecord(BaseModel):
    snapshot_id: str
    created_at: str
    schema_hash: str
    table_count: int
    column_count: int
    diff_summary: Optional[str] = None
