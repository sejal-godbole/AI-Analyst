"""
FastAPI route handlers for Observability, Tracing, and Live Metrics Dashboard.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.observability.models import (
    DashboardMetrics,
    SchemaChangeRecord,
    TraceDetail,
    TraceSummary,
)
from app.observability.schema_tracker import schema_tracker
from app.observability.store import (
    calculate_metrics,
    get_live_traces,
    get_trace_by_id,
    init_observability_db,
    list_traces,
)

obs_router = APIRouter(prefix="/api/observability", tags=["Observability"])


@obs_router.get("/metrics", response_model=DashboardMetrics)
async def get_dashboard_metrics() -> DashboardMetrics:
    """Returns aggregated metrics for all 6 Dashboard areas."""
    return calculate_metrics()


@obs_router.get("/traces", response_model=list[TraceSummary])
async def get_traces(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    intent: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
) -> list[TraceSummary]:
    """Returns a list of trace summaries with optional filters."""
    return list_traces(
        limit=limit,
        offset=offset,
        status=status,
        intent=intent,
        search=search,
    )


@obs_router.get("/traces/{trace_id}", response_model=TraceDetail)
async def get_trace_detail(trace_id: str) -> TraceDetail:
    """Returns full trace details including spans, LLM calls, guardrails, and MCP events."""
    detail = get_trace_by_id(trace_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found.")
    return detail


@obs_router.get("/live", response_model=list[TraceDetail])
async def get_live_execution_traces() -> list[TraceDetail]:
    """Returns the most recent in-flight or completed traces for live node visualization."""
    return get_live_traces()


@obs_router.get("/schema-history", response_model=list[SchemaChangeRecord])
async def get_schema_history() -> list[SchemaChangeRecord]:
    """Returns database schema change history and diff snapshots."""
    return schema_tracker.get_history()


@obs_router.get("/graph-definition")
async def get_graph_definition() -> dict:
    """Returns the compiled LangGraph nodes and edges derived dynamically from the compiled StateGraph."""
    from app.agent.graph import compiled_graph

    NODE_METADATA = {
        "__start__": {"label": "START", "desc": "Workflow entry", "type": "start", "icon": "Play"},
        "receive_question": {"label": "Receive Question", "desc": "Initialize context & trace", "type": "node", "icon": "Layers"},
        "inspect_schema": {"label": "Inspect Schema", "desc": "Fetch DB structure via MCP", "type": "node", "icon": "Database"},
        "build_schema_context": {"label": "Schema Context", "desc": "Format schema & relations", "type": "node", "icon": "FileCode2"},
        "classify_intent": {"label": "Classify Intent", "desc": "READ / WRITE / DESTRUCTIVE", "type": "node", "icon": "Cpu"},
        "generate_sql": {"label": "Generate SQL", "desc": "Gemini LLM generation", "type": "node", "icon": "Code2"},
        "validate_sql": {"label": "Validate SQL", "desc": "AST & semantic check", "type": "node", "icon": "CheckCircle2"},
        "safety_check": {"label": "Guardrails Check", "desc": "Security & policy enforcement", "type": "node", "icon": "ShieldCheck"},
        "human_confirmation": {"label": "Human Confirm", "desc": "Interrupt for broad writes", "type": "node", "icon": "AlertTriangle"},
        "execute_query": {"label": "MCP Execute", "desc": "Controlled DB execution", "type": "node", "icon": "Server"},
        "check_result": {"label": "Check Result", "desc": "Validate DB return", "type": "node", "icon": "Activity"},
        "final_answer": {"label": "Final Answer", "desc": "Synthesize natural response", "type": "node", "icon": "Zap"},
        "increment_retry": {"label": "Increment Retry", "desc": "Update retry count & history", "type": "retry", "icon": "RefreshCw"},
        "error_terminal": {"label": "Error Terminal", "desc": "Error handling & safe exit", "type": "error", "icon": "XCircle"},
        "__end__": {"label": "END", "desc": "Workflow completion", "type": "end", "icon": "Award"},
    }

    EDGE_METADATA = {
        ("__start__", "receive_question"): {"label": "", "type": "default"},
        ("receive_question", "inspect_schema"): {"label": "", "type": "default"},
        ("inspect_schema", "build_schema_context"): {"label": "", "type": "default"},
        ("build_schema_context", "classify_intent"): {"label": "", "type": "default"},
        ("classify_intent", "generate_sql"): {"label": "READ / DML", "type": "conditional"},
        ("classify_intent", "error_terminal"): {"label": "DESTRUCTIVE / UNKNOWN", "type": "error"},
        ("generate_sql", "validate_sql"): {"label": "", "type": "default"},
        ("validate_sql", "safety_check"): {"label": "valid", "type": "conditional"},
        ("validate_sql", "increment_retry"): {"label": "invalid (retry)", "type": "retry"},
        ("validate_sql", "error_terminal"): {"label": "exhausted", "type": "error"},
        ("safety_check", "execute_query"): {"label": "safe", "type": "conditional"},
        ("safety_check", "human_confirmation"): {"label": "needs confirmation", "type": "conditional"},
        ("safety_check", "error_terminal"): {"label": "unsafe", "type": "error"},
        ("human_confirmation", "execute_query"): {"label": "approved", "type": "conditional"},
        ("human_confirmation", "error_terminal"): {"label": "rejected", "type": "error"},
        ("execute_query", "check_result"): {"label": "succeeded", "type": "conditional"},
        ("execute_query", "increment_retry"): {"label": "error (retry)", "type": "retry"},
        ("execute_query", "error_terminal"): {"label": "exhausted", "type": "error"},
        ("check_result", "final_answer"): {"label": "ok", "type": "conditional"},
        ("check_result", "increment_retry"): {"label": "suspicious (retry)", "type": "retry"},
        ("check_result", "error_terminal"): {"label": "exhausted", "type": "error"},
        ("increment_retry", "generate_sql"): {"label": "retry loop", "type": "retry_loop"},
        ("final_answer", "__end__"): {"label": "", "type": "default"},
        ("error_terminal", "__end__"): {"label": "", "type": "default"},
    }

    lg_graph = compiled_graph.get_graph()

    nodes = []
    for node_id in lg_graph.nodes.keys():
        meta = NODE_METADATA.get(node_id, {"label": node_id, "desc": "", "type": "node", "icon": "Layers"})
        nodes.append({
            "id": node_id,
            "label": meta["label"],
            "desc": meta["desc"],
            "type": meta["type"],
            "icon": meta["icon"],
        })

    edges = []
    for edge in lg_graph.edges:
        src = edge.source
        tgt = edge.target
        key = (src, tgt)
        meta = EDGE_METADATA.get(key, {
            "label": getattr(edge, "data", "") or "",
            "type": "conditional" if getattr(edge, "conditional", False) else "default",
        })
        edges.append({
            "id": f"{src}->{tgt}",
            "source": src,
            "target": tgt,
            "label": meta["label"],
            "edge_type": meta["type"],
            "is_conditional": getattr(edge, "conditional", False),
        })

    return {"nodes": nodes, "edges": edges}


@obs_router.post("/init-db")
async def trigger_init_db() -> dict:
    """Ensures database tables for observability are initialized."""
    init_observability_db()
    return {"status": "ok", "message": "Observability tables checked and initialized."}

