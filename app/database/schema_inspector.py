"""
Discovers table/column/PK/FK metadata from PostgreSQL's information_schema
and pg_catalog. Returns ONLY structural metadata — never row data — so the
LLM never sees actual database contents at this stage.
"""
from __future__ import annotations

from app.database.connection import get_connection

_COLUMNS_QUERY = """
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;
"""

_PRIMARY_KEYS_QUERY = """
SELECT tc.table_name, kcu.column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
WHERE tc.constraint_type = 'PRIMARY KEY'
  AND tc.table_schema = 'public';
"""

_FOREIGN_KEYS_QUERY = """
SELECT
    tc.table_name        AS table_name,
    kcu.column_name       AS column_name,
    ccu.table_name        AS references_table,
    ccu.column_name       AS references_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_name = ccu.constraint_name
 AND tc.table_schema = ccu.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'public';
"""


def inspect_schema() -> dict:
    """
    Returns a structured schema dict:

    {
      "tables": {
        "<table>": {
          "columns": {"<col>": "<type>", ...},
          "nullable": {"<col>": bool, ...},
          "primary_keys": [...],
          "foreign_keys": [{"column", "references_table", "references_column"}, ...]
        }
      }
    }
    """
    tables: dict[str, dict] = {}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_COLUMNS_QUERY)
            for row in cur.fetchall():
                t = tables.setdefault(
                    row["table_name"],
                    {"columns": {}, "nullable": {}, "primary_keys": [], "foreign_keys": []},
                )
                t["columns"][row["column_name"]] = row["data_type"]
                t["nullable"][row["column_name"]] = row["is_nullable"] == "YES"

            cur.execute(_PRIMARY_KEYS_QUERY)
            for row in cur.fetchall():
                if row["table_name"] in tables:
                    tables[row["table_name"]]["primary_keys"].append(row["column_name"])

            cur.execute(_FOREIGN_KEYS_QUERY)
            for row in cur.fetchall():
                if row["table_name"] in tables:
                    tables[row["table_name"]]["foreign_keys"].append(
                        {
                            "column": row["column_name"],
                            "references_table": row["references_table"],
                            "references_column": row["references_column"],
                        }
                    )

    return {"tables": tables}
