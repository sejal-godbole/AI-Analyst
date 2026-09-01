"""Conditional-edge routing functions. Pure, deterministic, no side effects."""
from __future__ import annotations

from app.agent.state import AgentState


def route_after_validation(state: AgentState) -> str:
    if state.get("validated_sql"):
        return "safety_check"
    if state.get("retry_count", 0) < state.get("max_retries", 3):
        return "retry"
    return "error_terminal"


def route_after_safety_check(state: AgentState) -> str:
    status = state.get("safety_status")
    if status == "unsafe":
        return "error_terminal"
    if status == "needs_confirmation":
        return "human_confirmation"
    return "execute_query"


def route_after_confirmation(state: AgentState) -> str:
    if state.get("confirmation_approved"):
        return "execute_query"
    return "error_terminal"


def route_after_execution(state: AgentState) -> str:
    result = state.get("execution_result") or {}
    if result.get("ok"):
        return "check_result"
    if state.get("retry_count", 0) < state.get("max_retries", 3):
        return "retry"
    return "error_terminal"


def route_after_result_check(state: AgentState) -> str:
    validation = state.get("result_validation") or {}
    if validation.get("ok"):
        return "final_answer"
    if state.get("retry_count", 0) < state.get("max_retries", 3):
        return "retry"
    return "error_terminal"


def route_after_intent(state: AgentState) -> str:
    if state.get("intent") in ("DESTRUCTIVE", "UNKNOWN"):
        return "error_terminal"
    return "generate_sql"
