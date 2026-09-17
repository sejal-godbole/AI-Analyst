"""
Unified Evaluation Orchestrator.
Coordinates Intent, SQL, and LLM-as-a-Judge evaluators, calculating weighted quality scores.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings
from app.evaluation.dataset import find_golden_test_case_by_question
from app.evaluation.intent_evaluator import evaluate_intent
from app.evaluation.judge_evaluator import evaluate_final_answer
from app.evaluation.models import GoldenTestCase, SingleEvaluationResult
from app.evaluation.sql_evaluator import evaluate_sql

logger = logging.getLogger("ai_analyst.evaluation.orchestrator")


def evaluate_pipeline_result(
    question: str,
    intent: str,
    generated_sql: Optional[str] = None,
    database_result: Optional[str] = None,
    generated_answer: str = "",
    golden_test_case: Optional[GoldenTestCase] = None,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    error: Optional[str] = None,
) -> SingleEvaluationResult:
    """
    Evaluates the complete output of the 3-stage LLM pipeline.
    Shared across both Golden Dataset batch evaluation and live query observability.
    """
    settings = get_settings()

    # Look up golden test case if not explicitly provided
    if not golden_test_case:
        golden_test_case = find_golden_test_case_by_question(question)

    expected_intent = golden_test_case.expected_intent if golden_test_case else None

    # 1. Evaluate LLM #1 — Intent Classification (Deterministic)
    intent_eval = evaluate_intent(actual_intent=intent, expected_intent=expected_intent)

    # 2. Evaluate LLM #2 — SQL Generation (Deterministic)
    sql_eval = evaluate_sql(
        generated_sql=generated_sql,
        user_question=question,
        golden_test_case=golden_test_case,
        intent=intent,
    )

    # 3. Evaluate LLM #3 — Final Answer (LLM-as-a-Judge)
    final_answer_eval = evaluate_final_answer(
        user_question=question,
        generated_answer=generated_answer,
        database_result=database_result,
        golden_test_case=golden_test_case,
        error=error,
    )

    # 4. Calculate Overall Quality Score with Configurable Weights
    # LLM #1 (Intent) and LLM #2 (SQL) are binary (0 or 1), scaled x10 for the composite 10-point scale.
    # LLM #3 (Final Answer) is evaluated on a continuous 0-10 scale by the LLM Judge.
    w_intent = getattr(settings, "eval_weight_intent", 0.20)
    w_sql = getattr(settings, "eval_weight_sql", 0.40)
    w_final = getattr(settings, "eval_weight_final_answer", 0.40)

    if intent_eval.score is not None:
        overall_score = round(
            ((intent_eval.score * 10.0) * w_intent)
            + ((sql_eval.sql_quality_score * 10.0) * w_sql)
            + (final_answer_eval.final_answer_score * w_final),
            2,
        )
    else:
        # Ground truth unavailable: rebalance remaining weights between SQL and Final Answer
        overall_score = round(
            ((sql_eval.sql_quality_score * 10.0) * 0.50) + (final_answer_eval.final_answer_score * 0.50),
            2,
        )

    pass_threshold = getattr(settings, "eval_pass_threshold", 8.0)
    passed = bool(overall_score >= pass_threshold)

    result_id = f"eval_{trace_id or run_id or str(uuid.uuid4())[:8]}_{int(datetime.now(timezone.utc).timestamp() * 1000)}"

    return SingleEvaluationResult(
        result_id=result_id,
        run_id=run_id,
        trace_id=trace_id,
        test_case_id=golden_test_case.id if golden_test_case else None,
        question=question,
        intent_eval=intent_eval,
        sql_eval=sql_eval,
        final_answer_eval=final_answer_eval,
        overall_score=overall_score,
        passed=passed,
        weights_used={"intent": w_intent, "sql": w_sql, "final_answer": w_final},
        database_result=database_result,
        status="completed" if not error else "error",
        error=error,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
