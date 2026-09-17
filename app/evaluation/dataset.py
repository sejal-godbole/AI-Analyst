"""
Golden Dataset loader and search utilities.
Loads pre-defined ground-truth evaluation test cases from golden_dataset.json.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.evaluation.models import GoldenTestCase

DATASET_PATH = Path(__file__).parent / "golden_dataset.json"


@lru_cache
def load_golden_dataset() -> list[GoldenTestCase]:
    """Loads all test cases from golden_dataset.json."""
    if not DATASET_PATH.exists():
        return []

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [GoldenTestCase(**item) for item in data]


def find_golden_test_case_by_question(question: str) -> Optional[GoldenTestCase]:
    """Finds a matching golden test case by normalized question text."""
    if not question:
        return None

    normalized_q = question.strip().lower()
    dataset = load_golden_dataset()

    for item in dataset:
        if item.question.strip().lower() == normalized_q:
            return item

    # Check for strong substring match if question is closely phrased
    for item in dataset:
        item_q = item.question.strip().lower()
        if item_q in normalized_q or normalized_q in item_q:
            if len(item_q) > 10 and len(normalized_q) > 10:
                return item

    return None


def get_test_case_by_id(test_id: str) -> Optional[GoldenTestCase]:
    """Finds a golden test case by its ID (e.g. TC-001)."""
    dataset = load_golden_dataset()
    for item in dataset:
        if item.id == test_id:
            return item
    return None
