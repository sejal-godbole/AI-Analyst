"""
Pydantic schemas for the LLM Evaluation System.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class GoldenTestCase(BaseModel):
    id: str
    category: str
    question: str
    expected_intent: str
    expected_operation: Optional[str] = None
    expected_tables: list[str] = Field(default_factory=list)
    expected_conditions: Optional[str] = None
    expected_aggregation: Optional[str] = None
    expected_behavior: Optional[str] = None
    reference_answer: Optional[str] = None


class IntentEvaluationResult(BaseModel):
    expected_intent: Optional[str] = None
    actual_intent: str
    score: Optional[float] = None  # 10.0 or 0.0 (None if ground truth unavailable)
    format_compliance: float = 10.0  # 0 to 10
    instruction_compliance: float = 10.0  # 0 to 10
    is_ground_truth_available: bool = True
    notes: Optional[str] = None


class SQLEvaluationResult(BaseModel):
    sql_quality_score: float = 10.0  # 0 to 10
    relevance: float = 10.0
    schema_correctness: float = 10.0
    syntax_correctness: float = 10.0
    semantic_correctness: float = 10.0
    safety_compliance: float = 10.0
    generated_sql: Optional[str] = None
    is_ground_truth_available: bool = True
    notes: Optional[str] = None


class FinalAnswerEvaluationResult(BaseModel):
    final_answer_score: float = 10.0  # 0 to 10
    relevance: float = 10.0
    correctness: float = 10.0
    groundedness: float = 10.0
    completeness: float = 10.0
    clarity: float = 10.0
    reason: str = "Evaluation completed."
    judge_model: Optional[str] = None
    generated_answer: Optional[str] = None


class SingleEvaluationResult(BaseModel):
    result_id: str
    run_id: Optional[str] = None
    trace_id: Optional[str] = None
    test_case_id: Optional[str] = None
    question: str
    intent_eval: IntentEvaluationResult
    sql_eval: SQLEvaluationResult
    final_answer_eval: FinalAnswerEvaluationResult
    overall_score: Optional[float] = None  # 0 to 10
    passed: bool = True
    weights_used: dict[str, float] = Field(
        default_factory=lambda: {"intent": 0.20, "sql": 0.40, "final_answer": 0.40}
    )
    database_result: Optional[str] = None
    status: str = "completed"  # 'completed', 'error', 'skipped'
    error: Optional[str] = None
    timestamp: Optional[str] = None


class EvaluationRunSummary(BaseModel):
    run_id: str
    name: str = "Golden Dataset Run"
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    avg_intent_score: float = 0.0
    avg_sql_score: float = 0.0
    avg_final_score: float = 0.0
    overall_score: float = 0.0
    status: str = "completed"  # 'running', 'completed', 'failed'
    duration_ms: float = 0.0
    created_at: Optional[str] = None


class EvaluationRunDetail(BaseModel):
    summary: EvaluationRunSummary
    results: list[SingleEvaluationResult] = Field(default_factory=list)


class EvaluationRunRequest(BaseModel):
    test_ids: Optional[list[str]] = None  # Optional subset of test case IDs to run
    name: Optional[str] = "Batch Evaluation Run"
    concurrency: int = 1
