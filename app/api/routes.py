"""FastAPI routes: POST /analyze handles both fresh requests and resuming
a workflow that's paused awaiting human confirmation."""
from __future__ import annotations

import uuid

from fastapi import APIRouter
from langgraph.types import Command

from app.agent.graph import compiled_graph
from app.models.schemas import AnalyzeRequest, AnalyzeResponse

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    # --- Resuming a paused (awaiting-confirmation) workflow ---
    if request.thread_id and request.confirm is not None:
        config = {"configurable": {"thread_id": request.thread_id}}
        final_state = await compiled_graph.ainvoke(Command(resume=request.confirm), config)
        return _to_response(final_state, request.thread_id)

    # --- Fresh request ---
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {"user_question": request.question}

    final_state = await compiled_graph.ainvoke(initial_state, config)
    return _to_response(final_state, thread_id)


def _to_response(state: dict, thread_id: str) -> AnalyzeResponse:
    # If the graph is paused (interrupted), LangGraph's ainvoke return value
    # contains a special "__interrupt__" key instead of running to completion.
    interrupts = state.get("__interrupt__")
    if interrupts:
        payload = interrupts[0].value
        return AnalyzeResponse(
            status="awaiting_confirmation",
            requires_confirmation=True,
            confirmation_message=payload.get("message"),
            sql=payload.get("sql"),
            thread_id=thread_id,
        )

    status = state.get("status", "error")
    return AnalyzeResponse(
        status=status,
        answer=state.get("final_answer"),
        sql=state.get("validated_sql"),
        requires_confirmation=False,
        thread_id=thread_id,
        error=state.get("error_message") if status != "success" else None,
        rows_affected=state.get("rows_affected"),
    )


@router.get("/schema")
async def get_schema() -> dict:
    from app.database.schema_inspector import inspect_schema
    return inspect_schema()


@router.get("/audit-logs")
async def get_audit_logs() -> list[dict]:
    from app.database.connection import get_connection
    from app.config import get_settings
    settings = get_settings()
    table = settings.audit_log_table
    query = f"SELECT * FROM {table} ORDER BY audit_id DESC LIMIT 100"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                return [dict(r) for r in rows]
    except Exception as e:
        return [{"error": str(e)}]
