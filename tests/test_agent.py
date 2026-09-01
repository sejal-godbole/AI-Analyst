"""
Unit tests for routing logic (pure functions, no mocking needed) plus a
mocked end-to-end run of the node functions to verify the hallucination ->
retry -> correction loop and the max-retries cutoff, without requiring a
live LLM or database.
"""
from __future__ import annotations

import pytest

from app.agent import routing


def _state(**kwargs):
    base = {"retry_count": 0, "max_retries": 3}
    base.update(kwargs)
    return base


# --- Routing ---

def test_route_after_validation_valid():
    assert routing.route_after_validation(_state(validated_sql="SELECT 1")) == "safety_check"


def test_route_after_validation_invalid_retries_left():
    assert routing.route_after_validation(_state(validated_sql=None, retry_count=1)) == "retry"


def test_route_after_validation_invalid_retries_exhausted():
    assert routing.route_after_validation(_state(validated_sql=None, retry_count=3)) == "error_terminal"


def test_route_after_safety_check_unsafe():
    assert routing.route_after_safety_check(_state(safety_status="unsafe")) == "error_terminal"


def test_route_after_safety_check_needs_confirmation():
    assert routing.route_after_safety_check(_state(safety_status="needs_confirmation")) == "human_confirmation"


def test_route_after_safety_check_safe():
    assert routing.route_after_safety_check(_state(safety_status="safe")) == "execute_query"


def test_route_after_confirmation_approved():
    assert routing.route_after_confirmation(_state(confirmation_approved=True)) == "execute_query"


def test_route_after_confirmation_rejected():
    assert routing.route_after_confirmation(_state(confirmation_approved=False)) == "error_terminal"


def test_route_after_execution_success():
    assert routing.route_after_execution(_state(execution_result={"ok": True})) == "check_result"


def test_route_after_execution_failure_retries_left():
    assert routing.route_after_execution(_state(execution_result={"ok": False}, retry_count=0)) == "retry"


def test_route_after_execution_failure_retries_exhausted():
    assert (
        routing.route_after_execution(_state(execution_result={"ok": False}, retry_count=3))
        == "error_terminal"
    )


def test_route_after_result_check_ok():
    assert routing.route_after_result_check(_state(result_validation={"ok": True})) == "final_answer"


def test_route_after_result_check_suspicious_retries_left():
    assert (
        routing.route_after_result_check(_state(result_validation={"ok": False}, retry_count=0)) == "retry"
    )


def test_route_after_intent_destructive():
    assert routing.route_after_intent(_state(intent="DESTRUCTIVE")) == "error_terminal"


def test_route_after_intent_unknown():
    assert routing.route_after_intent(_state(intent="UNKNOWN")) == "error_terminal"


def test_route_after_intent_non_destructive():
    assert routing.route_after_intent(_state(intent="READ")) == "generate_sql"


# --- Mocked end-to-end: hallucinated table triggers exactly one retry, then succeeds ---

@pytest.mark.asyncio
async def test_hallucinated_table_then_correction(monkeypatch):
    from app.agent import nodes

    schema = {
        "tables": {
            "customers": {
                "columns": {"customer_id": "integer", "name": "character varying"},
                "primary_keys": ["customer_id"],
                "foreign_keys": [],
            }
        }
    }

    calls = {"n": 0}

    def fake_chat(system, user, temperature=0.0):
        calls["n"] += 1
        if calls["n"] == 1:
            return "SELECT * FROM users"  # hallucinated table
        return "SELECT * FROM customers"  # corrected

    monkeypatch.setattr(nodes, "chat", fake_chat)

    state = {"user_question": "list customers", "schema": schema, "schema_context": "..."}

    gen1 = await nodes.generate_sql(state)
    state.update(gen1)
    val1 = await nodes.validate_sql_node(state)
    state.update(val1)
    assert state["validated_sql"] is None
    assert routing.route_after_validation({**state, "retry_count": 0, "max_retries": 3}) == "retry"

    retry = await nodes.increment_retry({**state, "retry_count": 0})
    state.update(retry)

    gen2 = await nodes.generate_sql(state)
    state.update(gen2)
    val2 = await nodes.validate_sql_node(state)
    state.update(val2)

    assert state["validated_sql"] == "SELECT * FROM customers"
    assert routing.route_after_validation({**state, "max_retries": 3}) == "safety_check"


@pytest.mark.asyncio
async def test_max_retries_exhausted_goes_to_error(monkeypatch):
    from app.agent import nodes

    schema = {"tables": {"customers": {"columns": {"customer_id": "integer"}, "primary_keys": [], "foreign_keys": []}}}
    monkeypatch.setattr(nodes, "chat", lambda *a, **k: "SELECT * FROM users")

    state = {"user_question": "x", "schema": schema, "schema_context": "...", "retry_count": 3, "max_retries": 3}
    gen = await nodes.generate_sql(state)
    state.update(gen)
    val = await nodes.validate_sql_node(state)
    state.update(val)

    assert routing.route_after_validation(state) == "error_terminal"


@pytest.mark.asyncio
async def test_chat_history_appended_and_capped():
    from app.agent import nodes
    import unittest.mock as mock

    state = {
        "user_question": "Who are you?",
        "execution_result": {"ok": True, "operation": "SELECT", "row_count": 1, "rows": []},
        "chat_history": [{"question": "Q1", "answer": "A1"}]
    }

    with mock.patch("app.agent.nodes.chat", return_value="I am the assistant"):
        res = await nodes.final_answer_node(state)
        assert len(res["chat_history"]) == 2
        assert res["chat_history"][0] == {"question": "Q1", "answer": "A1"}
        assert res["chat_history"][1] == {"question": "Who are you?", "answer": "I am the assistant"}

    state_large = {
        "user_question": "Q6",
        "execution_result": {"ok": True, "operation": "SELECT", "row_count": 1, "rows": []},
        "chat_history": [
            {"question": "Q1", "answer": "A1"},
            {"question": "Q2", "answer": "A2"},
            {"question": "Q3", "answer": "A3"},
            {"question": "Q4", "answer": "A4"},
            {"question": "Q5", "answer": "A5"},
        ]
    }
    with mock.patch("app.agent.nodes.chat", return_value="A6"):
        res_large = await nodes.final_answer_node(state_large)
        assert len(res_large["chat_history"]) == 5
        assert res_large["chat_history"][0] == {"question": "Q2", "answer": "A2"}
        assert res_large["chat_history"][4] == {"question": "Q6", "answer": "A6"}
