"""
Raw MCP Python SDK client.

Spawns app/mcp/server.py as a subprocess connected over stdio, and exposes
simple async functions LangGraph nodes call to reach the MCP tools. This is
the ONLY module LangGraph nodes should import to reach the database — nodes
never import app.database.* directly.
"""
from __future__ import annotations

import json
import os
import shlex
from contextlib import asynccontextmanager

import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import get_settings


def _server_params() -> StdioServerParameters:
    settings = get_settings()
    args = shlex.split(settings.mcp_server_args)
    command = settings.mcp_server_command
    if command == "python":
        command = sys.executable
    return StdioServerParameters(command=command, args=args, env=os.environ.copy())


@asynccontextmanager
async def mcp_session():
    """Async context manager yielding a live ClientSession to the DB MCP server."""
    params = _server_params()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def call_inspect_schema() -> dict:
    async with mcp_session() as session:
        result = await session.call_tool("inspect_schema", {})
        return json.loads(result.content[0].text)


async def call_preview_query(sql: str) -> dict:
    async with mcp_session() as session:
        result = await session.call_tool("preview_query", {"sql": sql})
        return json.loads(result.content[0].text)


async def call_execute_query(sql: str, max_rows: int | None = None) -> dict:
    args = {"sql": sql}
    if max_rows is not None:
        args["max_rows"] = max_rows
    async with mcp_session() as session:
        result = await session.call_tool("execute_query", args)
        return json.loads(result.content[0].text)
