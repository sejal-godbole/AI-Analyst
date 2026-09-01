import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="Requires a live DATABASE_URL (see sample_db/init.sql)."
)


def test_execute_query_select():
    from app.mcp.tools import tool_execute_query

    result = tool_execute_query("SELECT * FROM customers WHERE city = 'Pune'")
    assert result["ok"]
    assert result["operation"] == "SELECT"


def test_execute_query_blocks_drop():
    from app.mcp.tools import tool_execute_query

    result = tool_execute_query("DROP TABLE customers")
    assert not result["ok"]


def test_execute_query_blocks_delete_without_where():
    from app.mcp.tools import tool_execute_query

    result = tool_execute_query("DELETE FROM customers")
    assert not result["ok"]


def test_execute_query_hallucinated_table():
    from app.mcp.tools import tool_execute_query

    result = tool_execute_query("SELECT * FROM users")
    assert not result["ok"]
