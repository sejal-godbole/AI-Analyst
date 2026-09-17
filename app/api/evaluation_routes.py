"""
FastAPI Routes for the LLM Evaluation System.
Provides endpoints for executing batch evaluations against the Golden Dataset,
inspecting evaluation runs, and retrieving live query evaluation telemetry.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.agent.graph import compiled_graph
from app.evaluation.dataset import get_test_case_by_id, load_golden_dataset
from app.evaluation.evaluator import evaluate_pipeline_result
from app.evaluation.models import (
    EvaluationRunDetail,
    EvaluationRunRequest,
    EvaluationRunSummary,
    GoldenTestCase,
    SingleEvaluationResult,
)
from app.evaluation.store import (
    get_evaluation_run_detail,
    get_live_evaluation,
    list_evaluation_runs,
    save_evaluation_run,
)
from app.observability.tracer import set_current_trace_id, tracer

logger = logging.getLogger("ai_analyst.api.evaluation")

eval_router = APIRouter(prefix="/api/evaluation", tags=["Evaluation"])


@eval_router.get("/dataset", response_model=list[GoldenTestCase])
async def get_dataset() -> list[GoldenTestCase]:
    """Returns the full Golden Dataset of curated ground-truth test cases."""
    return load_golden_dataset()


@eval_router.get("/runs", response_model=list[EvaluationRunSummary])
async def get_runs() -> list[EvaluationRunSummary]:
    """Lists historical evaluation runs."""
    return list_evaluation_runs()


@eval_router.get("/runs/{run_id}", response_model=EvaluationRunDetail)
async def get_run_detail(run_id: str) -> EvaluationRunDetail:
    """Retrieves full details of an evaluation run including all test case results."""
    detail = get_evaluation_run_detail(run_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Evaluation run '{run_id}' not found.")
    return detail


@eval_router.get("/trace/{trace_id}", response_model=Optional[SingleEvaluationResult])
async def get_trace_evaluation(trace_id: str) -> Optional[SingleEvaluationResult]:
    """Retrieves evaluation result for a live trace ID."""
    eval_record = get_live_evaluation(trace_id)
    return eval_record


@eval_router.post("/run", response_model=EvaluationRunDetail)
async def run_evaluation(request: Optional[EvaluationRunRequest] = None) -> EvaluationRunDetail:
    """
    Executes an evaluation run across the Golden Dataset test cases through the AI Analyst pipeline.
    Captures outputs from all 3 LLM stages, performs deterministic & judge scoring, and persists results.
    """
    start_t = time.time()
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:6]}"
    run_name = (request.name if request and request.name else "Golden Dataset Batch Run")

    dataset = load_golden_dataset()
    if request and request.test_ids:
        test_ids_set = set(request.test_ids)
        test_cases = [tc for tc in dataset if tc.id in test_ids_set]
    else:
        test_cases = dataset

    if not test_cases:
        raise HTTPException(status_code=400, detail="No test cases found to evaluate.")

    results: list[SingleEvaluationResult] = []
    passed_count = 0
    failed_count = 0

    total_intent_score = 0.0
    intent_count = 0
    total_sql_score = 0.0
    total_final_score = 0.0
    total_overall_score = 0.0

    for tc in test_cases:
        trace_id = f"eval_{uuid.uuid4()}"
        thread_id = f"eval_thread_{str(uuid.uuid4())[:8]}"
        set_current_trace_id(trace_id)

        # Initialize trace
        tracer.start_trace(trace_id=trace_id, user_question=tc.question, thread_id=thread_id)

        initial_state = {
            "user_question": tc.question,
            "trace_id": trace_id,
            "thread_id": thread_id,
        }
        config = {"configurable": {"thread_id": thread_id}}

        final_state = {}
        error_msg = None
        try:
            final_state = await compiled_graph.ainvoke(initial_state, config)
            # Handle potential interrupt response for HITL confirmation
            if "__interrupt__" in final_state:
                interrupt_val = final_state["__interrupt__"][0].value
                final_state["status"] = "awaiting_confirmation"
                final_state["confirmation_message"] = interrupt_val.get("message")
                final_state["validated_sql"] = interrupt_val.get("sql")
                final_state["final_answer"] = interrupt_val.get("message")
        except Exception as e:
            error_msg = str(e)
            logger.warning("Pipeline execution exception for test %s: %s", tc.id, e)

        # Extract agent output fields
        intent = final_state.get("intent") or ("DESTRUCTIVE" if "drop" in tc.question.lower() else "READ")
        generated_sql = final_state.get("validated_sql") or final_state.get("generated_sql") or final_state.get("raw_sql")
        db_result = str(final_state.get("execution_result") or final_state.get("result_validation") or "")
        final_answer = final_state.get("final_answer") or final_state.get("error_message") or ""

        # Run unified evaluation
        eval_result = evaluate_pipeline_result(
            question=tc.question,
            intent=intent,
            generated_sql=generated_sql,
            database_result=db_result,
            generated_answer=final_answer,
            golden_test_case=tc,
            trace_id=trace_id,
            run_id=run_id,
            error=error_msg or (final_state.get("error_message") if final_state.get("status") == "error" else None),
        )

        results.append(eval_result)

        if eval_result.passed:
            passed_count += 1
        else:
            failed_count += 1

        if eval_result.intent_eval.score is not None:
            total_intent_score += eval_result.intent_eval.score
            intent_count += 1

        total_sql_score += eval_result.sql_eval.sql_quality_score
        total_final_score += eval_result.final_answer_eval.final_answer_score
        total_overall_score += (eval_result.overall_score or 0.0)

    duration_ms = (time.time() - start_t) * 1000.0
    total_count = len(results)

    avg_intent = round(total_intent_score / max(1, intent_count), 2)
    avg_sql = round(total_sql_score / max(1, total_count), 2)
    avg_final = round(total_final_score / max(1, total_count), 2)
    overall_avg = round(total_overall_score / max(1, total_count), 2)

    summary = EvaluationRunSummary(
        run_id=run_id,
        name=run_name,
        total_cases=total_count,
        passed_cases=passed_count,
        failed_cases=failed_count,
        avg_intent_score=avg_intent,
        avg_sql_score=avg_sql,
        avg_final_score=avg_final,
        overall_score=overall_avg,
        status="completed",
        duration_ms=round(duration_ms, 2),
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    save_evaluation_run(summary, results)

    return EvaluationRunDetail(summary=summary, results=results)
