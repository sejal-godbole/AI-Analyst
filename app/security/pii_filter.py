"""
Strips configured sensitive columns out of result rows before they are sent
to the LLM for final-answer generation. This is defense against a query that
was allowed (e.g. `SELECT * FROM employees WHERE city = 'Pune'`) but whose
result set contains columns the LLM doesn't need to see.
"""
from __future__ import annotations

from app.config import get_settings


def filter_sensitive_columns(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Returns (filtered_rows, redacted_column_names).
    Column names are matched case-insensitively against SENSITIVE_COLUMNS.
    """
    if not rows:
        return rows, []

    settings = get_settings()
    sensitive = set(settings.sensitive_columns)

    redacted: set[str] = set()
    filtered_rows = []
    for row in rows:
        new_row = {}
        for k, v in row.items():
            if k.lower() in sensitive:
                redacted.add(k)
                continue
            new_row[k] = v
        filtered_rows.append(new_row)

    return filtered_rows, sorted(redacted)
