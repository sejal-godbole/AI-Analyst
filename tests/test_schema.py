import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="Requires a live DATABASE_URL (see sample_db/init.sql)."
)


def test_schema_discovery():
    from app.database.schema_inspector import inspect_schema

    schema = inspect_schema()
    assert "customers" in schema["tables"]
    assert "orders" in schema["tables"]


def test_primary_keys_discovered():
    from app.database.schema_inspector import inspect_schema

    schema = inspect_schema()
    assert "customer_id" in schema["tables"]["customers"]["primary_keys"]


def test_foreign_keys_discovered():
    from app.database.schema_inspector import inspect_schema

    schema = inspect_schema()
    fks = schema["tables"]["orders"]["foreign_keys"]
    assert any(
        fk["column"] == "customer_id" and fk["references_table"] == "customers" for fk in fks
    )
