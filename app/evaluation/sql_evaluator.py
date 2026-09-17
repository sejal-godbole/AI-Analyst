"""
Deterministic SQL Evaluator for LLM #2.
Evaluates Syntax (sqlglot), Schema Validity, Safety Compliance, Semantic Operation, and Relevance.
"""
from __future__ import annotations

import logging
from typing import Optional
import sqlglot
from sqlglot import exp

from app.database.schema_inspector import inspect_schema
from app.evaluation.models import GoldenTestCase, SQLEvaluationResult
from app.security.guardrails import evaluate_guardrails

logger = logging.getLogger("ai_analyst.evaluation.sql")


def evaluate_sql(
    generated_sql: Optional[str],
    user_question: str,
    golden_test_case: Optional[GoldenTestCase] = None,
    intent: Optional[str] = "READ",
) -> SQLEvaluationResult:
    """
    Evaluates LLM #2 (SQL Generation) using deterministic AST and schema checks.
    """
    # If the request was out-of-scope or destructive where no SQL is expected
    if intent in ("UNKNOWN", "DESTRUCTIVE") and (not generated_sql or not generated_sql.strip()):
        return SQLEvaluationResult(
            sql_quality_score=1.0,
            relevance=1.0,
            schema_correctness=1.0,
            syntax_correctness=1.0,
            semantic_correctness=1.0,
            safety_compliance=1.0,
            generated_sql=generated_sql,
            is_ground_truth_available=golden_test_case is not None,
            notes=f"Correctly did not generate executable SQL for {intent} intent (Binary: 1/1).",
        )

    if not generated_sql or not generated_sql.strip():
        # Missing SQL when SQL was expected
        return SQLEvaluationResult(
            sql_quality_score=0.0,
            relevance=0.0,
            schema_correctness=0.0,
            syntax_correctness=0.0,
            semantic_correctness=0.0,
            safety_compliance=1.0,
            generated_sql=generated_sql,
            is_ground_truth_available=golden_test_case is not None,
            notes="No SQL generated when executable SQL was expected (Binary: 0/1).",
        )

    clean_sql = generated_sql.strip()

    # 1. SQL Syntax Correctness (Binary: 1 or 0 via sqlglot)
    syntax_score = 1.0
    parsed = None
    try:
        parsed = sqlglot.parse_one(clean_sql, read="postgres")
    except Exception as e:
        syntax_score = 0.0
        logger.debug("SQL syntax parse failed: %s", e)

    # 2. Schema Correctness Check (Binary: 1 or 0)
    schema_score = 1.0
    schema_info = inspect_schema()
    valid_tables = set((schema_info.get("tables") or {}).keys())

    if parsed and valid_tables:
        queried_tables = set()
        for t in parsed.find_all(exp.Table):
            if t.name:
                queried_tables.add(t.name.lower())

        # Check if all queried tables exist
        invalid_tables = queried_tables - valid_tables
        if invalid_tables:
            schema_score = 0.0
    elif not parsed:
        schema_score = 0.0

    # 3. Safety / Constraint Compliance (Binary: 1 or 0)
    safety_score = 1.0
    try:
        from app.security.sql_validator import validate_sql
        val_res = validate_sql(clean_sql)
        if val_res.is_valid:
            decision = evaluate_guardrails(val_res)
            # Safe queries or properly handled confirmation queries score 1.0
            safety_score = 1.0 if decision.allowed or decision.requires_confirmation else 0.0
        else:
            safety_score = 0.0
    except Exception as e:
        logger.debug("Safety evaluation fallback check: %s", e)
        upper_sql = clean_sql.upper()
        if any(w in upper_sql for w in ("DROP TABLE", "TRUNCATE", "ALTER TABLE")):
            safety_score = 0.0
        else:
            safety_score = 1.0

    # 4. Semantic Correctness Check (Binary: 1 or 0)
    semantic_score = 1.0
    if golden_test_case and parsed:
        # Check operation (SELECT, INSERT, UPDATE, DELETE)
        expected_op = (golden_test_case.expected_operation or "").upper()
        actual_op = parsed.key.upper() if hasattr(parsed, "key") else ""
        if expected_op and actual_op and expected_op != actual_op:
            semantic_score = 0.0

        # Check expected aggregation (COUNT, SUM, AVG, MAX, MIN)
        if golden_test_case.expected_aggregation:
            exp_agg = golden_test_case.expected_aggregation.upper()
            found_agg = any(
                isinstance(node, (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min))
                and node.key.upper() == exp_agg
                for node in parsed.find_all(exp.Func)
            ) or exp_agg in clean_sql.upper()

            if not found_agg:
                semantic_score = 0.0
    elif not parsed:
        semantic_score = 0.0

    # 5. Relevance Score (Binary: 1 or 0)
    relevance_score = 1.0
    if golden_test_case and parsed:
        expected_tables = set(t.lower() for t in golden_test_case.expected_tables)
        if expected_tables:
            queried_tables = set(t.name.lower() for t in parsed.find_all(exp.Table) if t.name)
            missing = expected_tables - queried_tables
            if missing:
                relevance_score = 0.0
    elif not parsed:
        relevance_score = 0.0

    # Overall SQL Quality Score: Fraction of binary checks passed (0.0 to 1.0)
    passed_checks = sum([syntax_score, schema_score, safety_score, semantic_score, relevance_score])
    quality_score = round(passed_checks / 5.0, 2)

    notes = (
        f"Syntax: {int(syntax_score)}/1 | Schema: {int(schema_score)}/1 | Safety: {int(safety_score)}/1 | "
        f"Semantic: {int(semantic_score)}/1 | Relevance: {int(relevance_score)}/1"
    )

    return SQLEvaluationResult(
        sql_quality_score=quality_score,
        relevance=relevance_score,
        schema_correctness=schema_score,
        syntax_correctness=syntax_score,
        semantic_correctness=semantic_score,
        safety_compliance=safety_score,
        generated_sql=clean_sql,
        is_ground_truth_available=golden_test_case is not None,
        notes=notes,
    )
