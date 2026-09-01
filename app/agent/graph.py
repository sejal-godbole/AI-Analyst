"""
Wires the AgentState + nodes + routing functions into a compiled LangGraph
graph, with an in-memory checkpointer so `interrupt()` (human confirmation)
can pause and later resume execution for a given thread_id.

Graph shape:

    receive_question -> inspect_schema -> build_schema_context -> classify_intent
        -> generate_sql -> validate_sql
            --(invalid, retries left)--> increment_retry -> generate_sql
            --(invalid, retries exhausted)--> error_terminal
            --(valid)--> safety_check
                --(unsafe)--> error_terminal
                --(needs confirmation)--> human_confirmation
                    --(approved)--> execute_query
                    --(rejected)--> error_terminal
                --(safe)--> execute_query
    execute_query
        --(failed, retries left)--> increment_retry -> generate_sql
        --(failed, retries exhausted)--> error_terminal
        --(succeeded)--> check_result
            --(ok)--> final_answer -> END
            --(suspicious, retries left)--> increment_retry -> generate_sql
            --(suspicious, retries exhausted)--> error_terminal
    error_terminal -> END
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agent import nodes, routing
from app.agent.state import AgentState


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("receive_question", nodes.receive_question)
    graph.add_node("inspect_schema", nodes.inspect_schema_node)
    graph.add_node("build_schema_context", nodes.build_schema_context)
    graph.add_node("classify_intent", nodes.classify_intent)
    graph.add_node("generate_sql", nodes.generate_sql)
    graph.add_node("validate_sql", nodes.validate_sql_node)
    graph.add_node("safety_check", nodes.safety_check)
    graph.add_node("human_confirmation", nodes.human_confirmation)
    graph.add_node("execute_query", nodes.execute_query_node)
    graph.add_node("check_result", nodes.check_result)
    graph.add_node("final_answer", nodes.final_answer_node)
    graph.add_node("error_terminal", nodes.error_terminal)
    graph.add_node("increment_retry", nodes.increment_retry)

    graph.set_entry_point("receive_question")
    graph.add_edge("receive_question", "inspect_schema")
    graph.add_edge("inspect_schema", "build_schema_context")
    graph.add_edge("build_schema_context", "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        routing.route_after_intent,
        {
            "generate_sql": "generate_sql",
            "error_terminal": "error_terminal",
        },
    )
    graph.add_edge("generate_sql", "validate_sql")

    graph.add_conditional_edges(
        "validate_sql",
        routing.route_after_validation,
        {
            "safety_check": "safety_check",
            "retry": "increment_retry",
            "error_terminal": "error_terminal",
        },
    )

    graph.add_conditional_edges(
        "safety_check",
        routing.route_after_safety_check,
        {
            "execute_query": "execute_query",
            "human_confirmation": "human_confirmation",
            "error_terminal": "error_terminal",
        },
    )

    graph.add_conditional_edges(
        "human_confirmation",
        routing.route_after_confirmation,
        {
            "execute_query": "execute_query",
            "error_terminal": "error_terminal",
        },
    )

    graph.add_conditional_edges(
        "execute_query",
        routing.route_after_execution,
        {
            "check_result": "check_result",
            "retry": "increment_retry",
            "error_terminal": "error_terminal",
        },
    )

    graph.add_conditional_edges(
        "check_result",
        routing.route_after_result_check,
        {
            "final_answer": "final_answer",
            "retry": "increment_retry",
            "error_terminal": "error_terminal",
        },
    )

    graph.add_edge("increment_retry", "generate_sql")
    graph.add_edge("final_answer", END)
    graph.add_edge("error_terminal", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


# Module-level singleton compiled graph, reused across requests.
compiled_graph = build_graph()
