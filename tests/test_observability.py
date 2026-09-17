"""
Unit tests for the Observability, Tracing, Metrics calculation, and Schema Tracker.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.observability.models import TraceDetail
from app.observability.pricing import estimate_llm_cost
from app.observability.schema_tracker import SchemaTracker
from app.observability.store import calculate_metrics, get_trace_by_id, list_traces, save_trace_detail
from app.observability.tracer import Tracer


def test_pricing_estimation():
    # Gemini 2.5 Flash: $0.075/1M input, $0.30/1M output
    cost = estimate_llm_cost("gemini-2.5-flash", 1000, 500)
    expected = (1000 * (0.075 / 1_000_000)) + (500 * (0.30 / 1_000_000))
    assert cost == pytest.approx(expected, rel=1e-5)

    # GPT-4o: $2.50/1M input, $10.00/1M output
    cost_gpt = estimate_llm_cost("gpt-4o", 2000, 1000)
    expected_gpt = (2000 * (2.50 / 1_000_000)) + (1000 * (10.00 / 1_000_000))
    assert cost_gpt == pytest.approx(expected_gpt, rel=1e-5)


def test_schema_tracker_diff():
    tracker = SchemaTracker()
    schema_v1 = {
        "tables": {
            "customers": {
                "columns": {"id": "int", "name": "varchar"},
                "primary_keys": ["id"],
            }
        }
    }
    is_changed1, record1 = tracker.record_and_diff(schema_v1)
    assert not is_changed1
    assert record1 is not None
    assert record1.table_count == 1

    # Same schema again -> no change
    is_changed2, record2 = tracker.record_and_diff(schema_v1)
    assert not is_changed2
    assert record2 is None

    # Modified schema with a new table and column
    schema_v2 = {
        "tables": {
            "customers": {
                "columns": {"id": "int", "name": "varchar", "email": "varchar"},
                "primary_keys": ["id"],
            },
            "orders": {
                "columns": {"order_id": "int", "amount": "decimal"},
                "primary_keys": ["order_id"],
            },
        }
    }
    is_changed3, record3 = tracker.record_and_diff(schema_v2)
    assert is_changed3
    assert record3 is not None
    assert record3.table_count == 2
    assert "orders" in record3.diff_summary


def test_tracer_lifecycle():
    tracer = Tracer()
    trace_id = "test-trace-12345"
    trace = tracer.start_trace(trace_id, "How many customers in Pune?", thread_id="thread-99")
    assert trace.trace_id == trace_id
    assert trace.status == "running"

    # Start and end span
    span = tracer.start_span("classify_intent", "node", {"q": "How many customers in Pune?"}, trace_id=trace_id)
    tracer.end_span(span.span_id, {"intent": "READ"}, status="completed")

    # Record LLM call
    tracer.record_llm_call(
        node_name="generate_sql",
        model="gemini-2.5-flash",
        system_prompt="SQL System Prompt",
        user_prompt="How many customers in Pune?",
        response_text="SELECT COUNT(*) FROM customers WHERE city = 'Pune';",
        duration_ms=450.0,
        prompt_tokens=150,
        completion_tokens=25,
        trace_id=trace_id,
    )

    # Record Guardrail decision
    tracer.record_guardrail_decision(
        decision="ALLOWED",
        rule_name="Safety Checks Passed",
        reason="Query is a safe SELECT statement",
        sql="SELECT COUNT(*) FROM customers WHERE city = 'Pune';",
        trace_id=trace_id,
    )

    # Record MCP call
    tracer.record_mcp_call(
        tool_name="execute_query",
        duration_ms=12.5,
        ok=True,
        rows_count=1,
        langgraph_mcp_agreement=True,
        trace_id=trace_id,
    )

    # End trace
    ended_trace = tracer.end_trace(
        trace_id=trace_id,
        final_answer="There are 4 customers in Pune.",
        status="success",
        validated_sql="SELECT COUNT(*) FROM customers WHERE city = 'Pune';",
        raw_sql="```sql\nSELECT COUNT(*) FROM customers WHERE city = 'Pune';\n```",
        rows_affected=1,
        intent="READ",
        sql_operation="SELECT",
    )

    assert ended_trace.status == "success"
    assert ended_trace.intent_aligned is True
    assert ended_trace.first_attempt_success is True
    assert ended_trace.total_tokens == 175
    assert len(ended_trace.spans) >= 1
    assert len(ended_trace.llm_calls) >= 1
    assert len(ended_trace.guardrail_records) >= 1
    assert len(ended_trace.mcp_calls) >= 1


@pytest.mark.asyncio
async def test_observability_endpoints():
    # Insert a sample trace to verify endpoints
    import uuid
    from app.observability.tracer import tracer
    from app.observability.store import save_trace_detail
    sample_id = f"test-endpoint-trace-{uuid.uuid4()}"
    tracer.start_trace(sample_id, "Sample test question")
    ended = tracer.end_trace(
        trace_id=sample_id,
        final_answer="Sample test answer",
        status="success",
        validated_sql="SELECT 1;",
        intent="READ",
        sql_operation="SELECT",
    )
    if ended:
        save_trace_detail(ended)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Metrics endpoint
        metrics_res = await client.get("/api/observability/metrics")
        assert metrics_res.status_code == 200
        metrics = metrics_res.json()
        assert "total_requests" in metrics
        assert "first_attempt_sql_success_rate" in metrics

        # 2. Traces list endpoint
        traces_res = await client.get("/api/observability/traces")
        assert traces_res.status_code == 200
        traces = traces_res.json()
        assert isinstance(traces, list)
        assert any(t["trace_id"] == sample_id for t in traces)

        # 3. Trace detail endpoint
        detail_res = await client.get(f"/api/observability/traces/{sample_id}")
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["trace_id"] == sample_id
        assert detail["status"] == "success"

        # 4. Live traces endpoint
        live_res = await client.get("/api/observability/live")
        assert live_res.status_code == 200
        assert isinstance(live_res.json(), list)

        # 5. Schema history endpoint
        schema_res = await client.get("/api/observability/schema-history")
        assert schema_res.status_code == 200
        assert isinstance(schema_res.json(), list)
