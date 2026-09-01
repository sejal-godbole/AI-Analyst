"""
Raw MCP Python SDK server.

Exposes three tools over stdio:
  - inspect_schema
  - preview_query
  - execute_query

This process is the ONLY thing that talks to PostgreSQL. It owns the
DATABASE_URL (via app.database.connection) and re-validates every SQL
statement it is asked to run, regardless of what LangGraph already checked.

Run standalone:
    python -m app.mcp.server
"""
from __future__ import annotations

import asyncio
import json
import logging

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from app.mcp.tools import tool_execute_query, tool_inspect_schema, tool_preview_query

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_analyst.mcp_server")

server = Server("ai-analyst-db-server")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="inspect_schema",
            description=(
                "Inspect the database and return table names, columns, data types, "
                "primary keys, foreign keys, and relationships. Returns metadata "
                "only — no row data."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="preview_query",
            description=(
                "Estimate how many rows a SQL statement would affect, without "
                "executing it. Used before risky UPDATE/DELETE statements."
            ),
            inputSchema={
                "type": "object",
                "properties": {"sql": {"type": "string", "description": "SQL statement to preview."}},
                "required": ["sql"],
            },
        ),
        types.Tool(
            name="execute_query",
            description=(
                "Execute a validated SQL statement (SELECT/INSERT/UPDATE/DELETE) "
                "against the database. Destructive administrative statements are "
                "rejected server-side regardless of caller intent."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL statement to execute."},
                    "max_rows": {
                        "type": "integer",
                        "description": "Optional row cap override for SELECT statements.",
                    },
                },
                "required": ["sql"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    logger.info("MCP tool call: %s(%s)", name, {k: v for k, v in arguments.items() if k != "sql"})

    if name == "inspect_schema":
        result = tool_inspect_schema()
    elif name == "preview_query":
        result = tool_preview_query(arguments["sql"])
    elif name == "execute_query":
        result = tool_execute_query(arguments["sql"], arguments.get("max_rows"))
    else:
        result = {"ok": False, "error": f"Unknown tool: {name}"}

    return [types.TextContent(type="text", text=json.dumps(result, default=str))]


async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="ai-analyst-db-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
