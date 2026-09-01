from app.security.guardrails import evaluate_guardrails
from app.security.sql_validator import validate_sql

SCHEMA = {
    "tables": {
        "customers": {
            "columns": {"customer_id": "integer", "name": "character varying", "city": "character varying"},
            "primary_keys": ["customer_id"],
            "foreign_keys": [],
        }
    }
}


def test_select_always_allowed_no_confirmation():
    v = validate_sql("SELECT * FROM customers", SCHEMA)
    d = evaluate_guardrails(v)
    assert d.allowed
    assert not d.requires_confirmation


def test_delete_without_where_blocked():
    v = validate_sql("DELETE FROM customers", SCHEMA)
    d = evaluate_guardrails(v)
    assert not d.allowed


def test_update_without_where_requires_confirmation_not_rejected():
    v = validate_sql("UPDATE customers SET city = 'Pune'", SCHEMA)
    d = evaluate_guardrails(v)
    assert d.allowed
    assert d.requires_confirmation


def test_delete_with_where_allowed():
    v = validate_sql("DELETE FROM customers WHERE customer_id = 1", SCHEMA)
    d = evaluate_guardrails(v)
    assert d.allowed


def test_destructive_statement_rejected():
    v = validate_sql("DROP TABLE customers", SCHEMA)
    d = evaluate_guardrails(v)
    assert not d.allowed
    assert not d.requires_confirmation


def test_invalid_sql_rejected():
    v = validate_sql("SELECT * FROM nonexistent", SCHEMA)
    d = evaluate_guardrails(v)
    assert not d.allowed
