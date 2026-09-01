"""
Centralized configuration.

All secrets (DATABASE_URL, LLM_API_KEY) are loaded here from environment
variables only. They are never placed into LangGraph state, LLM prompts,
or logs. Only the MCP/database layer ever reads DATABASE_URL.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated, Any

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode

load_dotenv()


class Settings(BaseSettings):
    # Database — read only by app/database/* and app/mcp/server.py
    database_url: str = os.getenv("DATABASE_URL", "")

    # LLM — defaults target Gemini's OpenAI-compatibility endpoint, so the
    # same `openai` SDK client works unchanged against Google's API.
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv(
        "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    llm_model: str = os.getenv("LLM_MODEL", "gemini-2.5-flash")

    # Agent behavior
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    max_rows: int = int(os.getenv("MAX_ROWS", "100"))

    # Guardrails
    require_write_confirmation: bool = os.getenv(
        "REQUIRE_WRITE_CONFIRMATION", "true"
    ).lower() == "true"
    confirmation_row_threshold: int = int(os.getenv("CONFIRMATION_ROW_THRESHOLD", "1"))
    sensitive_columns: Annotated[list[str], NoDecode] = [
        c.strip().lower()
        for c in os.getenv(
            "SENSITIVE_COLUMNS", "email,phone,password,ssn,aadhaar,credit_card,salary"
        ).split(",")
        if c.strip()
    ]

    @field_validator("sensitive_columns", mode="before")
    @classmethod
    def parse_sensitive_columns(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [c.strip().lower() for c in v.split(",") if c.strip()]
        return v

    # MCP server transport (spawned as a subprocess over stdio)
    mcp_server_command: str = os.getenv("MCP_SERVER_COMMAND", "python")
    mcp_server_args: str = os.getenv("MCP_SERVER_ARGS", "-m app.mcp.server")

    audit_log_table: str = os.getenv("AUDIT_LOG_TABLE", "agent_audit_log")

    class Config:
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
