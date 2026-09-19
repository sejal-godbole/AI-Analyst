"""Initializes sample database tables and seed data if not present."""
from __future__ import annotations

import logging
from pathlib import Path

from app.database.connection import get_connection

logger = logging.getLogger("ai_analyst.database.init_db")


def init_sample_db() -> None:
    """Initialize sample business tables and agent audit log."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Check if customers table already exists
                cur.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = 'customers';"
                )
                if cur.fetchone():
                    logger.info("Sample database tables already exist.")
                    return

                # Read sample_db/init.sql
                sql_file = Path(__file__).resolve().parent.parent.parent / "sample_db" / "init.sql"
                if sql_file.exists():
                    sql_script = sql_file.read_text(encoding="utf-8")
                    cur.execute(sql_script)
                    conn.commit()
                    logger.info("Successfully executed sample_db/init.sql and seeded tables.")
                else:
                    logger.warning("sample_db/init.sql file not found at %s", sql_file)
    except Exception as e:
        logger.warning("Could not auto-initialize sample database: %s", e)
