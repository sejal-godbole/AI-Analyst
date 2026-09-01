"""
Owns the database connection.

CRITICAL: this module (and schema_inspector.py) are the ONLY places in the
codebase that ever see DATABASE_URL. The LLM, LangGraph state, and API
responses never receive it.
"""
from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings


def get_connection() -> psycopg.Connection:
    """
    Open a new synchronous psycopg connection using DATABASE_URL.

    A fresh connection per call keeps this simple and safe for a learning
    project. For production, replace with a psycopg_pool.ConnectionPool.
    """
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured.")
    return psycopg.connect(settings.database_url, row_factory=dict_row)
