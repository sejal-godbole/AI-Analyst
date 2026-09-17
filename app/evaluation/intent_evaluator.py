"""
Deterministic Intent Classification Evaluator for LLM #1.
Evaluates accuracy, format compliance, and instruction compliance against ground truth.
"""
from __future__ import annotations

from typing import Optional
from app.evaluation.models import IntentEvaluationResult

_ALLOWED_INTENTS = {"READ", "INSERT", "UPDATE", "DELETE", "DESTRUCTIVE", "UNKNOWN"}


def evaluate_intent(
    actual_intent: str,
    expected_intent: Optional[str] = None,
) -> IntentEvaluationResult:
    """
    Evaluates LLM #1 (Intent Classification).
    Deterministic check:
    - Expected vs Actual: 10/10 if match, 0/10 if mismatch
    - Format Compliance: 10/10 if in standard intent enum
    - Instruction Compliance: 10/10 if single uppercase token
    """
    raw_actual = (actual_intent or "").strip()
    normalized_actual = raw_actual.upper()

    # 1. Format Compliance Check (Binary: 1 or 0)
    if normalized_actual in _ALLOWED_INTENTS:
        format_score = 1.0
    else:
        format_score = 0.0

    # 2. Instruction Compliance Check (Binary: 1 or 0)
    # Must be single uppercase token matching allowed format
    if raw_actual == normalized_actual and raw_actual in _ALLOWED_INTENTS:
        instruction_score = 1.0
    else:
        instruction_score = 0.0

    # 3. Accuracy vs Ground Truth (Binary: 1 or 0)
    if expected_intent is not None and expected_intent.strip():
        norm_expected = expected_intent.strip().upper()
        if normalized_actual == norm_expected:
            score = 1.0
            notes = f"Intent matches ground truth: {norm_expected} (Binary 1)."
        else:
            score = 0.0
            notes = f"Intent mismatch. Expected {norm_expected}, got {normalized_actual} (Binary 0)."
        is_gt_available = True
    else:
        score = None
        is_gt_available = False
        notes = "Ground truth unavailable for this query."

    return IntentEvaluationResult(
        expected_intent=expected_intent,
        actual_intent=normalized_actual,
        score=score,
        format_compliance=format_score,
        instruction_compliance=instruction_score,
        is_ground_truth_available=is_gt_available,
        notes=notes,
    )
