"""
Deterministic SQL validation using sqlglot.

This is layer 1 of defense-in-depth (LangGraph-side). It never trusts the
LLM's self-reported intent. It parses the actual SQL text and checks it
against the real schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

# Statement types we refuse outright, regardless of schema.
_BLOCKED_KEYWORDS = {
    "DROP",
    "TRUNCATE",
    "ALTER",
    "GRANT",
    "REVOKE",
    "CREATE",  # blocks CREATE DATABASE / CREATE TABLE etc. via generation
}

_ALLOWED_STATEMENT_TYPES = (exp.Select, exp.Insert, exp.Update, exp.Delete)


@dataclass
class ValidationResult:
    is_valid: bool
    operation: str | None = None
    tables: set[str] = field(default_factory=set)
    columns: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)
    is_destructive: bool = False
    has_where_clause: bool | None = None  # relevant for UPDATE/DELETE
    statement_count: int = 0


def _extract_columns(tree: exp.Expression) -> set[str]:
    cols = set()
    for col in tree.find_all(exp.Column):
        if col.name:
            cols.add(col.name.lower())
    return cols


def _extract_tables(tree: exp.Expression) -> set[str]:
    tables = set()
    for t in tree.find_all(exp.Table):
        if t.name:
            tables.add(t.name.lower())
    return tables


def validate_sql(sql: str, schema: dict) -> ValidationResult:
    """
    Parses `sql` (PostgreSQL dialect) and validates it against `schema`
    (the dict shape produced by schema_inspector.inspect_schema()).
    """
    result = ValidationResult(is_valid=True)
    sql_stripped = sql.strip().rstrip(";")

    if not sql_stripped:
        result.is_valid = False
        result.errors.append("Empty SQL statement.")
        return result

    upper = sql_stripped.upper()
    for kw in _BLOCKED_KEYWORDS:
        # Word-boundary-ish check: keyword must appear as its own token.
        if f" {kw} " in f" {upper} " or upper.startswith(kw + " "):
            result.is_valid = False
            result.is_destructive = True
            result.errors.append(
                f"Statement contains blocked administrative keyword: {kw}."
            )
            return result

    # Parse — reject multiple statements unless exactly one is present.
    try:
        statements = sqlglot.parse(sql_stripped, read="postgres")
    except Exception as e:  # sqlglot raises ParseError subtypes
        result.is_valid = False
        result.errors.append(f"SQL failed to parse: {e}")
        return result

    statements = [s for s in statements if s is not None]
    result.statement_count = len(statements)
    if len(statements) != 1:
        result.is_valid = False
        result.errors.append(
            f"Expected exactly one SQL statement, found {len(statements)}."
        )
        return result

    tree = statements[0]

    if not isinstance(tree, _ALLOWED_STATEMENT_TYPES):
        result.is_valid = False
        result.errors.append(
            f"Unsupported or disallowed statement type: {type(tree).__name__}."
        )
        return result

    result.operation = type(tree).__name__.upper()  # SELECT / INSERT / UPDATE / DELETE
    result.tables = _extract_tables(tree)
    result.columns = _extract_columns(tree)

    if isinstance(tree, (exp.Update, exp.Delete)):
        where = tree.find(exp.Where)
        result.has_where_clause = where is not None

    # --- Schema conformance ---
    schema_tables = {t.lower() for t in schema.get("tables", {}).keys()}
    unknown_tables = result.tables - schema_tables
    if unknown_tables:
        result.is_valid = False
        result.errors.append(
            f"Unknown table(s) referenced: {', '.join(sorted(unknown_tables))}. "
            f"Known tables: {', '.join(sorted(schema_tables))}."
        )

    # Build the set of valid columns across all referenced (known) tables.
    valid_columns: set[str] = set()
    for t in result.tables & schema_tables:
        valid_columns |= {c.lower() for c in schema["tables"][t]["columns"].keys()}

    # Columns like COUNT(*) produce no exp.Column with a real name; also
    # allow bare '*' (star) which sqlglot represents via exp.Star, not Column.
    unknown_columns = {
        c for c in result.columns if c not in valid_columns and c != "*"
    }
    if unknown_columns and result.tables & schema_tables:
        result.is_valid = False
        result.errors.append(
            f"Unknown column(s) referenced: {', '.join(sorted(unknown_columns))}."
        )

    return result
