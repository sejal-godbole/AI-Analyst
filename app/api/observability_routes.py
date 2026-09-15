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


@obs_router.post("/init-db")
async def trigger_init_db() -> dict:
    """Ensures database tables for observability are initialized."""
    init_observability_db()
    return {"status": "ok", "message": "Observability tables checked and initialized."}
