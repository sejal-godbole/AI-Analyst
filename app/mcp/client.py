"""
Raw MCP Python SDK client with Observability instrumentation.

Spawns app/mcp/server.py as a subprocess connected over stdio, measures
startup/handshake latencies and tool execution metrics, and logs events to the tracer.
"""
from __future__ import annotations

import json
import logging
import os
import shlex
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import get_settings
from app.observability.tracer import tracer

logger = logging.getLogger("ai_analyst.mcp.client")


def _server_params() -> StdioServerParameters:
    settings = get_settings()
    args = shlex.split(settings.mcp_server_args)
    command = settings.mcp_server_command
    if command == "python":
        command = sys.executable
    return StdioServerParameters(command=command, args=args, env=os.environ.copy())


@asynccontextmanager
async def mcp_session():
    """Async context manager yielding (session, startup_latency_ms)."""
    params = _server_params()
    t0 = time.time()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            startup_latency_ms = (time.time() - t0) * 1000.0
            yield session, startup_latency_ms


async def call_inspect_schema(trace_id: Optional[str] = None) -> dict:
    start_t = time.time()
    startup_ms = None
    ok = True
    error_msg = None
    res = {}
    try:
        async with mcp_session() as (session, startup_ms):
            result = await session.call_tool("inspect_schema", {})
            res = json.loads(result.content[0].text)
            return res
    except Exception as e:
        ok = False
        error_msg = str(e)
        logger.warning("MCP inspect_schema call failed: %s", e)
        raise
    finally:
        duration_ms = (time.time() - start_t) * 1000.0
        table_count = len(res.get("tables", {})) if ok else 0
        tracer.record_mcp_call(
            tool_name="inspect_schema",
            duration_ms=duration_ms,
            ok=ok,
            rows_count=table_count,
            error=error_msg,
            subprocess_startup_ms=startup_ms,
            trace_id=trace_id,
        )


async def call_preview_query(sql: str, trace_id: Optional[str] = None) -> dict:
    start_t = time.time()
    startup_ms = None
    ok = True
    error_msg = None
    res = {}
    try:
        async with mcp_session() as (session, startup_ms):
            result = await session.call_tool("preview_query", {"sql": sql})
            res = json.loads(result.content[0].text)
            ok = res.get("ok", True)
            if not ok:
                error_msg = res.get("error")
            return res
    except Exception as e:
        ok = False
        error_msg = str(e)
        logger.warning("MCP preview_query call failed: %s", e)
        raise
    finally:
        duration_ms = (time.time() - start_t) * 1000.0
        tracer.record_mcp_call(
            tool_name="preview_query",
            duration_ms=duration_ms,
            ok=ok,
            rows_count=res.get("estimated_rows") or 0,
            error=error_msg,
            subprocess_startup_ms=startup_ms,
            trace_id=trace_id,
        )


async def call_execute_query(
    sql: str, max_rows: int | None = None, trace_id: Optional[str] = None
) -> dict:
    args = {"sql": sql}
    if max_rows is not None:
        args["max_rows"] = max_rows

    start_t = time.time()
    startup_ms = None
    ok = True
    error_msg = None
    res = {}
    try:
        async with mcp_session() as (session, startup_ms):
            result = await session.call_tool("execute_query", args)
            res = json.loads(result.content[0].text)
            ok = res.get("ok", True)
            if not ok:
                error_msg = res.get("error")
            return res
    except Exception as e:
        ok = False
        error_msg = str(e)
        logger.warning("MCP execute_query call failed: %s", e)
        raise
    finally:
        duration_ms = (time.time() - start_t) * 1000.0
        rows_count = res.get("row_count", 0) if ok else 0
        tracer.record_mcp_call(
            tool_name="execute_query",
            duration_ms=duration_ms,
            ok=ok,
            rows_count=rows_count,
            error=error_msg,
            subprocess_startup_ms=startup_ms,
            trace_id=trace_id,
        )
