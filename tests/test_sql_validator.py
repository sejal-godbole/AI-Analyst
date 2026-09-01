from app.security.sql_validator import validate_sql

SCHEMA = {
    "tables": {
        "customers": {
            "columns": {"customer_id": "integer", "name": "character varying", "city": "character varying"},
            "primary_keys": ["customer_id"],
            "foreign_keys": [],
        },
        "orders": {
            "columns": {"order_id": "integer", "customer_id": "integer", "amount": "numeric"},
            "primary_keys": ["order_id"],
            "foreign_keys": [
                {"column": "customer_id", "references_table": "customers", "references_column": "customer_id"}
            ],
        },
    }
}


def test_valid_select():
    r = validate_sql("SELECT name, city FROM customers", SCHEMA)
    assert r.is_valid
    assert r.operation == "SELECT"


def test_valid_join():
    r = validate_sql(
        "SELECT c.name, o.amount FROM customers c JOIN orders o ON c.customer_id = o.customer_id", SCHEMA
    )
    assert r.is_valid


def test_valid_insert():
    r = validate_sql("INSERT INTO customers (name, city) VALUES ('Test', 'Pune')", SCHEMA)
    assert r.is_valid
    assert r.operation == "INSERT"


def test_valid_update_with_where():
    r = validate_sql("UPDATE customers SET city = 'Pune' WHERE customer_id = 1", SCHEMA)
    assert r.is_valid
    assert r.has_where_clause is True


def test_valid_delete_with_where():
    r = validate_sql("DELETE FROM customers WHERE customer_id = 1", SCHEMA)
    assert r.is_valid
    assert r.has_where_clause is True


def test_invalid_table():
    r = validate_sql("SELECT * FROM nonexistent_table", SCHEMA)
    assert not r.is_valid
    assert any("Unknown table" in e for e in r.errors)


def test_invalid_column():
    r = validate_sql("SELECT customer_name FROM customers", SCHEMA)
    assert not r.is_valid
    assert any("Unknown column" in e for e in r.errors)


def test_malformed_sql():
    r = validate_sql("SELEC * FROM customers", SCHEMA)
    assert not r.is_valid


def test_multiple_statements_rejected():
    r = validate_sql("SELECT * FROM customers; SELECT * FROM orders;", SCHEMA)
    assert not r.is_valid


def test_drop_blocked():
    r = validate_sql("DROP TABLE customers", SCHEMA)
    assert not r.is_valid
    assert r.is_destructive


def test_truncate_blocked():
    r = validate_sql("TRUNCATE customers", SCHEMA)
    assert not r.is_valid
    assert r.is_destructive


def test_delete_without_where_flagged_no_where():
    r = validate_sql("DELETE FROM customers", SCHEMA)
    assert r.is_valid  # syntactically/schema valid — guardrails.py rejects it
    assert r.has_where_clause is False


def test_update_without_where_flagged():
    r = validate_sql("UPDATE customers SET city = 'Pune'", SCHEMA)
    assert r.is_valid
    assert r.has_where_clause is False
