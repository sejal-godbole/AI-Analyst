"""
Unit and integration tests for the LLM Evaluation System.
"""
from __future__ import annotations

import pytest
from app.evaluation.dataset import find_golden_test_case_by_question, load_golden_dataset
from app.evaluation.evaluator import evaluate_pipeline_result
from app.evaluation.intent_evaluator import evaluate_intent
from app.evaluation.judge_evaluator import evaluate_final_answer
from app.evaluation.models import GoldenTestCase
from app.evaluation.sql_evaluator import evaluate_sql


def test_golden_dataset_loaded():
    """Verify that the Golden Dataset loads properly with >= 30 curated test cases."""
    dataset = load_golden_dataset()
    assert len(dataset) >= 30
    for item in dataset:
        assert item.id.startswith("TC-")
        assert item.question
        assert item.expected_intent in {"READ", "INSERT", "UPDATE", "DELETE", "DESTRUCTIVE", "UNKNOWN"}


def test_find_golden_test_case():
    """Verify fuzzy/exact search for golden test case by question."""
    tc = find_golden_test_case_by_question("How many customers are from Pune?")
    assert tc is not None
    assert tc.expected_intent == "READ"
    assert tc.expected_aggregation == "COUNT"


def test_intent_evaluator_exact_match():
    """Verify deterministic intent evaluation on matching intent."""
    res = evaluate_intent(actual_intent="READ", expected_intent="READ")
    assert res.score == 1.0
    assert res.format_compliance == 1.0
    assert res.instruction_compliance == 1.0
    assert res.is_ground_truth_available is True


def test_intent_evaluator_mismatch():
    """Verify deterministic intent evaluation on mismatched intent."""
    res = evaluate_intent(actual_intent="UPDATE", expected_intent="READ")
    assert res.score == 0.0
    assert res.format_compliance == 1.0
    assert res.is_ground_truth_available is True


def test_intent_evaluator_no_ground_truth():
    """Verify intent evaluation handles live query with no ground truth without penalizing."""
    res = evaluate_intent(actual_intent="READ", expected_intent=None)
    assert res.score is None
    assert res.is_ground_truth_available is False
    assert res.format_compliance == 1.0


def test_sql_evaluator_valid_query():
    """Verify deterministic SQL evaluation on valid query."""
    tc = GoldenTestCase(
        id="TC-TEST",
        category="READ_FILTER",
        question="How many customers are from Pune?",
        expected_intent="READ",
        expected_operation="SELECT",
        expected_tables=["customers"],
        expected_aggregation="COUNT",
    )
    sql = "SELECT COUNT(*) FROM customers WHERE city ILIKE '%Pune%'"
    res = evaluate_sql(generated_sql=sql, user_question=tc.question, golden_test_case=tc, intent="READ")

    assert res.syntax_correctness == 1.0
    assert res.schema_correctness == 1.0
    assert res.safety_compliance == 1.0
    assert res.semantic_correctness == 1.0
    assert res.relevance == 1.0
    assert res.sql_quality_score == 1.0


def test_sql_evaluator_syntax_error():
    """Verify deterministic SQL evaluation penalizes syntax errors."""
    sql = "SELECT FROM WHERE customers;;;"
    res = evaluate_sql(generated_sql=sql, user_question="test", intent="READ")
    assert res.syntax_correctness == 0.0
    assert res.sql_quality_score < 0.5


def test_sql_evaluator_destructive_blocking():
    """Verify deterministic SQL evaluation for blocked destructive query."""
    res = evaluate_sql(generated_sql=None, user_question="Drop table customers", intent="DESTRUCTIVE")
    assert res.sql_quality_score == 1.0
    assert res.safety_compliance == 1.0


def test_judge_evaluator_fallback_heuristic():
    """Verify judge evaluator safely handles fallbacks without crashing."""
    res = evaluate_final_answer(
        user_question="How many customers are from Pune?",
        generated_answer="There are 4 customers from Pune.",
        database_result="[{'count': 4}]",
    )
    assert res.final_answer_score >= 0.0
    assert res.final_answer_score <= 10.0
    assert res.reason


def test_unified_evaluator_orchestrator():
    """Verify unified evaluation orchestrator computes weighted score properly."""
    tc = GoldenTestCase(
        id="TC-TEST",
        category="READ_FILTER",
        question="How many customers are from Pune?",
        expected_intent="READ",
        expected_operation="SELECT",
        expected_tables=["customers"],
        expected_aggregation="COUNT",
        reference_answer="There are 4 customers from Pune.",
    )
    res = evaluate_pipeline_result(
        question=tc.question,
        intent="READ",
        generated_sql="SELECT COUNT(*) FROM customers WHERE city = 'Pune'",
        database_result="[{'count': 4}]",
        generated_answer="There are 4 customers located in Pune.",
        golden_test_case=tc,
    )
    assert res.overall_score is not None
    assert res.overall_score >= 8.0
    assert res.passed is True
    assert res.intent_eval.score == 1.0
    assert res.sql_eval.sql_quality_score >= 0.8
