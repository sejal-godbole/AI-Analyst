"""
PostgreSQL Storage for Evaluation Runs, Test Case Results, and Live Trace Evaluations.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.database.connection import get_connection
from app.evaluation.models import (
    EvaluationRunDetail,
    EvaluationRunSummary,
    FinalAnswerEvaluationResult,
    IntentEvaluationResult,
    SingleEvaluationResult,
    SQLEvaluationResult,
)

logger = logging.getLogger("ai_analyst.evaluation.store")

# In-memory fallback cache
_EVAL_RUNS_CACHE: dict[str, EvaluationRunSummary] = {}
_EVAL_RESULTS_CACHE: dict[str, list[SingleEvaluationResult]] = {}
_LIVE_EVAL_CACHE: dict[str, SingleEvaluationResult] = {}


def init_evaluation_db() -> None:
    """Initializes evaluation database tables if they do not exist."""
    queries = [
        """
        CREATE TABLE IF NOT EXISTS evaluation_runs (
            run_id VARCHAR(128) PRIMARY KEY,
            name VARCHAR(256) NOT NULL,
            total_cases INTEGER DEFAULT 0,
            passed_cases INTEGER DEFAULT 0,
            failed_cases INTEGER DEFAULT 0,
            avg_intent_score DOUBLE PRECISION DEFAULT 0.0,
            avg_sql_score DOUBLE PRECISION DEFAULT 0.0,
            avg_final_score DOUBLE PRECISION DEFAULT 0.0,
            overall_score DOUBLE PRECISION DEFAULT 0.0,
            status VARCHAR(64) DEFAULT 'completed',
            duration_ms DOUBLE PRECISION DEFAULT 0.0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS evaluation_results (
            result_id VARCHAR(128) PRIMARY KEY,
            run_id VARCHAR(128),
            trace_id VARCHAR(128),
            test_case_id VARCHAR(64),
            question TEXT NOT NULL,
            expected_intent VARCHAR(64),
            actual_intent VARCHAR(64),
            intent_score DOUBLE PRECISION,
            intent_metrics JSONB,
            generated_sql TEXT,
            sql_score DOUBLE PRECISION,
            sql_metrics JSONB,
            database_result TEXT,
            generated_answer TEXT,
            final_answer_score DOUBLE PRECISION,
            judge_metrics JSONB,
            judge_reason TEXT,
            overall_score DOUBLE PRECISION,
            passed BOOLEAN DEFAULT TRUE,
            weights_used JSONB,
            status VARCHAR(64) DEFAULT 'completed',
            error TEXT,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_eval_results_run_id ON evaluation_results(run_id);
        CREATE INDEX IF NOT EXISTS idx_eval_results_trace_id ON evaluation_results(trace_id);
        """
    ]

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                for q in queries:
                    cur.execute(q)
            conn.commit()
            logger.info("Evaluation database tables successfully initialized.")
    except Exception as e:
        logger.warning("Failed to initialize evaluation PostgreSQL tables: %s", e)


def save_evaluation_run(summary: EvaluationRunSummary, results: list[SingleEvaluationResult]) -> None:
    """Saves a complete batch evaluation run with its test case results."""
    _EVAL_RUNS_CACHE[summary.run_id] = summary
    _EVAL_RESULTS_CACHE[summary.run_id] = results

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO evaluation_runs (
                        run_id, name, total_cases, passed_cases, failed_cases,
                        avg_intent_score, avg_sql_score, avg_final_score, overall_score,
                        status, duration_ms, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id) DO UPDATE SET
                        passed_cases = EXCLUDED.passed_cases,
                        failed_cases = EXCLUDED.failed_cases,
                        avg_intent_score = EXCLUDED.avg_intent_score,
                        avg_sql_score = EXCLUDED.avg_sql_score,
                        avg_final_score = EXCLUDED.avg_final_score,
                        overall_score = EXCLUDED.overall_score,
                        status = EXCLUDED.status,
                        duration_ms = EXCLUDED.duration_ms;
                    """,
                    (
                        summary.run_id,
                        summary.name,
                        summary.total_cases,
                        summary.passed_cases,
                        summary.failed_cases,
                        summary.avg_intent_score,
                        summary.avg_sql_score,
                        summary.avg_final_score,
                        summary.overall_score,
                        summary.status,
                        summary.duration_ms,
                        summary.created_at or datetime.now(timezone.utc).isoformat(),
                    ),
                )

                for r in results:
                    cur.execute(
                        """
                        INSERT INTO evaluation_results (
                            result_id, run_id, trace_id, test_case_id, question,
                            expected_intent, actual_intent, intent_score, intent_metrics,
                            generated_sql, sql_score, sql_metrics, database_result,
                            generated_answer, final_answer_score, judge_metrics, judge_reason,
                            overall_score, passed, weights_used, status, error, timestamp
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (result_id) DO NOTHING;
                        """,
                        (
                            r.result_id,
                            r.run_id,
                            r.trace_id,
                            r.test_case_id,
                            r.question,
                            r.intent_eval.expected_intent,
                            r.intent_eval.actual_intent,
                            r.intent_eval.score,
                            json.dumps(r.intent_eval.model_dump()),
                            r.sql_eval.generated_sql,
                            r.sql_eval.sql_quality_score,
                            json.dumps(r.sql_eval.model_dump()),
                            r.database_result,
                            r.final_answer_eval.generated_answer,
                            r.final_answer_eval.final_answer_score,
                            json.dumps(r.final_answer_eval.model_dump()),
                            r.final_answer_eval.reason,
                            r.overall_score,
                            r.passed,
                            json.dumps(r.weights_used),
                            r.status,
                            r.error,
                            r.timestamp or datetime.now(timezone.utc).isoformat(),
                        ),
                    )
            conn.commit()
    except Exception as e:
        logger.warning("Failed to persist evaluation run to database: %s", e)


def save_live_evaluation(result: SingleEvaluationResult) -> None:
    """Saves a live evaluation associated with a specific query trace."""
    if result.trace_id:
        _LIVE_EVAL_CACHE[result.trace_id] = result

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO evaluation_results (
                        result_id, run_id, trace_id, test_case_id, question,
                        expected_intent, actual_intent, intent_score, intent_metrics,
                        generated_sql, sql_score, sql_metrics, database_result,
                        generated_answer, final_answer_score, judge_metrics, judge_reason,
                        overall_score, passed, weights_used, status, error, timestamp
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (result_id) DO UPDATE SET
                        intent_score = EXCLUDED.intent_score,
                        sql_score = EXCLUDED.sql_score,
                        final_answer_score = EXCLUDED.final_answer_score,
                        overall_score = EXCLUDED.overall_score,
                        judge_reason = EXCLUDED.judge_reason;
                    """,
                    (
                        result.result_id,
                        result.run_id or "live",
                        result.trace_id,
                        result.test_case_id,
                        result.question,
                        result.intent_eval.expected_intent,
                        result.intent_eval.actual_intent,
                        result.intent_eval.score,
                        json.dumps(result.intent_eval.model_dump()),
                        result.sql_eval.generated_sql,
                        result.sql_eval.sql_quality_score,
                        json.dumps(result.sql_eval.model_dump()),
                        result.database_result,
                        result.final_answer_eval.generated_answer,
                        result.final_answer_eval.final_answer_score,
                        json.dumps(result.final_answer_eval.model_dump()),
                        result.final_answer_eval.reason,
                        result.overall_score,
                        result.passed,
                        json.dumps(result.weights_used),
                        result.status,
                        result.error,
                        result.timestamp or datetime.now(timezone.utc).isoformat(),
                    ),
                )
            conn.commit()
    except Exception as e:
        logger.warning("Failed to persist live evaluation result: %s", e)


def get_live_evaluation(trace_id: str) -> Optional[SingleEvaluationResult]:
    """Retrieves live evaluation result for a trace ID."""
    if trace_id in _LIVE_EVAL_CACHE:
        return _LIVE_EVAL_CACHE[trace_id]

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM evaluation_results WHERE trace_id = %s ORDER BY timestamp DESC LIMIT 1",
                    (trace_id,),
                )
                row = cur.fetchone()
                if row:
                    row_dict = dict(row)
                    intent_data = row_dict.get("intent_metrics")
                    if isinstance(intent_data, str):
                        intent_data = json.loads(intent_data)
                    sql_data = row_dict.get("sql_metrics")
                    if isinstance(sql_data, str):
                        sql_data = json.loads(sql_data)
                    judge_data = row_dict.get("judge_metrics")
                    if isinstance(judge_data, str):
                        judge_data = json.loads(judge_data)

                    weights_data = row_dict.get("weights_used")
                    if isinstance(weights_data, str):
                        weights_data = json.loads(weights_data)

                    res = SingleEvaluationResult(
                        result_id=row_dict["result_id"],
                        run_id=row_dict.get("run_id"),
                        trace_id=row_dict.get("trace_id"),
                        test_case_id=row_dict.get("test_case_id"),
                        question=row_dict["question"],
                        intent_eval=IntentEvaluationResult(**(intent_data or {"actual_intent": row_dict.get("actual_intent", "READ")})),
                        sql_eval=SQLEvaluationResult(**(sql_data or {"sql_quality_score": row_dict.get("sql_score", 10.0)})),
                        final_answer_eval=FinalAnswerEvaluationResult(**(judge_data or {"final_answer_score": row_dict.get("final_answer_score", 10.0), "reason": row_dict.get("judge_reason", "")})),
                        overall_score=row_dict.get("overall_score"),
                        passed=row_dict.get("passed", True),
                        weights_used=weights_data or {"intent": 0.20, "sql": 0.40, "final_answer": 0.40},
                        database_result=row_dict.get("database_result"),
                        status=row_dict.get("status", "completed"),
                        error=row_dict.get("error"),
                        timestamp=row_dict["timestamp"].isoformat() if hasattr(row_dict.get("timestamp"), "isoformat") else str(row_dict.get("timestamp")),
                    )
                    _LIVE_EVAL_CACHE[trace_id] = res
                    return res
    except Exception as e:
        logger.debug("Failed to retrieve live evaluation from DB: %s", e)

    return None


def list_evaluation_runs() -> list[EvaluationRunSummary]:
    """Lists all historical evaluation runs."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM evaluation_runs ORDER BY created_at DESC LIMIT 50")
                rows = cur.fetchall()
                if rows:
                    return [
                        EvaluationRunSummary(
                            run_id=r["run_id"],
                            name=r["name"],
                            total_cases=r["total_cases"],
                            passed_cases=r["passed_cases"],
                            failed_cases=r["failed_cases"],
                            avg_intent_score=r["avg_intent_score"],
                            avg_sql_score=r["avg_sql_score"],
                            avg_final_score=r["avg_final_score"],
                            overall_score=r["overall_score"],
                            status=r["status"],
                            duration_ms=r["duration_ms"],
                            created_at=r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
                        )
                        for r in rows
                    ]
    except Exception as e:
        logger.debug("Listing runs from DB failed: %s", e)

    return list(_EVAL_RUNS_CACHE.values())


def get_evaluation_run_detail(run_id: str) -> Optional[EvaluationRunDetail]:
    """Retrieves full details of a specific evaluation run."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM evaluation_runs WHERE run_id = %s", (run_id,))
                run_row = cur.fetchone()
                if not run_row:
                    if run_id in _EVAL_RUNS_CACHE:
                        return EvaluationRunDetail(
                            summary=_EVAL_RUNS_CACHE[run_id],
                            results=_EVAL_RESULTS_CACHE.get(run_id, []),
                        )
                    return None

                summary = EvaluationRunSummary(
                    run_id=run_row["run_id"],
                    name=run_row["name"],
                    total_cases=run_row["total_cases"],
                    passed_cases=run_row["passed_cases"],
                    failed_cases=run_row["failed_cases"],
                    avg_intent_score=run_row["avg_intent_score"],
                    avg_sql_score=run_row["avg_sql_score"],
                    avg_final_score=run_row["avg_final_score"],
                    overall_score=run_row["overall_score"],
                    status=run_row["status"],
                    duration_ms=run_row["duration_ms"],
                    created_at=run_row["created_at"].isoformat() if hasattr(run_row["created_at"], "isoformat") else str(run_row["created_at"]),
                )

                cur.execute("SELECT * FROM evaluation_results WHERE run_id = %s ORDER BY test_case_id ASC, timestamp ASC", (run_id,))
                result_rows = cur.fetchall()

                results = []
                for r in result_rows:
                    intent_data = r.get("intent_metrics") or {}
                    if isinstance(intent_data, str):
                        intent_data = json.loads(intent_data)
                    sql_data = r.get("sql_metrics") or {}
                    if isinstance(sql_data, str):
                        sql_data = json.loads(sql_data)
                    judge_data = r.get("judge_metrics") or {}
                    if isinstance(judge_data, str):
                        judge_data = json.loads(judge_data)
                    weights_data = r.get("weights_used") or {}
                    if isinstance(weights_data, str):
                        weights_data = json.loads(weights_data)

                    results.append(
                        SingleEvaluationResult(
                            result_id=r["result_id"],
                            run_id=r.get("run_id"),
                            trace_id=r.get("trace_id"),
                            test_case_id=r.get("test_case_id"),
                            question=r["question"],
                            intent_eval=IntentEvaluationResult(**intent_data),
                            sql_eval=SQLEvaluationResult(**sql_data),
                            final_answer_eval=FinalAnswerEvaluationResult(**judge_data),
                            overall_score=r.get("overall_score"),
                            passed=r.get("passed", True),
                            weights_used=weights_data or {"intent": 0.20, "sql": 0.40, "final_answer": 0.40},
                            database_result=r.get("database_result"),
                            status=r.get("status", "completed"),
                            error=r.get("error"),
                            timestamp=r["timestamp"].isoformat() if hasattr(r["timestamp"], "isoformat") else str(r["timestamp"]),
                        )
                    )

                return EvaluationRunDetail(summary=summary, results=results)
    except Exception as e:
        logger.warning("Failed to fetch evaluation run detail: %s", e)
        if run_id in _EVAL_RUNS_CACHE:
            return EvaluationRunDetail(
                summary=_EVAL_RUNS_CACHE[run_id],
                results=_EVAL_RESULTS_CACHE.get(run_id, []),
            )

    return None
