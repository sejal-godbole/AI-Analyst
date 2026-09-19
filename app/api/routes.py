"""FastAPI routes: POST /analyze handles both fresh requests and resuming
a workflow that's paused awaiting human confirmation."""
from __future__ import annotations

import uuid

from fastapi import APIRouter
from langgraph.types import Command

from app.agent.graph import compiled_graph
from app.models.schemas import AnalyzeRequest, AnalyzeResponse
from app.observability.tracer import set_current_trace_id, tracer

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    # --- Resuming a paused (awaiting-confirmation) workflow ---
    if request.thread_id and request.confirm is not None:
        trace_id = request.trace_id or str(uuid.uuid4())
        set_current_trace_id(trace_id)
        config = {"configurable": {"thread_id": request.thread_id}}
        final_state = await compiled_graph.ainvoke(Command(resume=request.confirm), config)
        return _to_response(final_state, request.thread_id, trace_id)

    # --- Fresh request ---
    thread_id = request.thread_id or str(uuid.uuid4())
    trace_id = request.trace_id or str(uuid.uuid4())
    set_current_trace_id(trace_id)

    # Start root trace
    tracer.start_trace(trace_id=trace_id, user_question=request.question, thread_id=thread_id)

    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "user_question": request.question,
        "trace_id": trace_id,
        "thread_id": thread_id,
    }

    final_state = await compiled_graph.ainvoke(initial_state, config)
    return _to_response(final_state, thread_id, trace_id)


def _to_response(state: dict, thread_id: str, trace_id: str) -> AnalyzeResponse:
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
            trace_id=trace_id,
        )

    status = state.get("status", "error")

    # Safe live query evaluation (never breaks main pipeline)
    try:
        from app.evaluation.evaluator import evaluate_pipeline_result
        from app.evaluation.store import save_live_evaluation
        user_question = state.get("user_question") or ""
        intent = state.get("intent") or "READ"
        generated_sql = state.get("validated_sql") or state.get("generated_sql") or state.get("raw_sql")
        db_result = str(state.get("execution_result") or state.get("result_validation") or "")
        final_answer = state.get("final_answer") or state.get("error_message") or ""
        eval_res = evaluate_pipeline_result(
            question=user_question,
            intent=intent,
            generated_sql=generated_sql,
            database_result=db_result,
            generated_answer=final_answer,
            trace_id=trace_id,
            error=state.get("error_message") if status != "success" else None,
        )
        save_live_evaluation(eval_res)
    except Exception as e:
        import logging
        logging.getLogger("ai_analyst.routes").warning("Live evaluation skipped on error: %s", e)

    return AnalyzeResponse(
        status=status,
        answer=state.get("final_answer"),
        sql=state.get("validated_sql"),
        requires_confirmation=False,
        thread_id=thread_id,
        trace_id=trace_id,
        error=state.get("error_message") if status != "success" else None,
        rows_affected=state.get("rows_affected"),
    )


@router.get("/schema")
async def get_schema() -> dict:
    from app.database.init_db import init_sample_db
    from app.database.schema_inspector import inspect_schema
    init_sample_db()
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
