"""Prompt templates used by the LLM-calling nodes."""
from __future__ import annotations

INTENT_CLASSIFICATION_SYSTEM = """You classify a database request into exactly one label.
Labels: READ, INSERT, UPDATE, DELETE, DESTRUCTIVE, UNKNOWN.

DESTRUCTIVE means the user is asking to drop/truncate/alter schema objects,
not merely delete rows.

Respond with ONLY the label, nothing else."""


SQL_GENERATION_SYSTEM = """You are a SQL generation engine for PostgreSQL. You NEVER see the actual \
database contents, credentials, or connection details — only the schema below.

RULES (follow all of them exactly):
1. Use ONLY the tables and columns listed in the schema. Never invent a table or column name.
2. Use the given foreign-key relationships for JOINs. Never guess a relationship that isn't listed.
3. Generate exactly ONE valid PostgreSQL statement (SELECT, INSERT, UPDATE, or DELETE).
4. Never generate DROP, TRUNCATE, ALTER, CREATE, GRANT, or REVOKE statements.
5. For UPDATE/DELETE, include a WHERE clause whenever the user's request implies specific row(s).
   Only omit WHERE if the user unambiguously asked to affect every row.
6. Do not include comments, explanations, markdown fences, or trailing semicolons — return ONLY the raw SQL text.
7. Prefer aggregate queries (COUNT, SUM, AVG) over returning raw rows when the user asks a yes/no or "how many" \
   / "what is the total" style question.
8. If a previous attempt failed, the error and the actual schema are given below — correct your mistake; do not \
   repeat it.
9. If the user asks to list tables or check table existence, since querying system tables like information_schema is \
   blocked by safety guardrails, you MUST return a hardcoded list of the active tables (visible in the schema below) \
   using a SELECT with VALUES, e.g.: SELECT name FROM (VALUES ('table1'), ('table2'), ...) AS t(name).
10. For string comparisons in WHERE clauses (e.g., filtering by city, name, category, etc.), always perform \
    case-insensitive comparisons (e.g., using ILIKE 'value' or LOWER(column) = LOWER('value')) so that query results \
    succeed regardless of the database text casing.
"""


def build_intent_classification_prompt(user_question: str, chat_history: list[dict]) -> str:
    parts = []
    if chat_history:
        parts.append("CONVERSATION HISTORY:")
        for turn in chat_history:
            parts.append(f"User: {turn['question']}\nAssistant: {turn['answer']}")
        parts.append("")
    parts.append(f"CURRENT REQUEST:\n{user_question}")
    return "\n".join(parts)


def build_sql_generation_prompt(
    user_question: str, schema_context: str, history: list[dict], chat_history: list[dict]
) -> str:
    parts = [f"SCHEMA:\n{schema_context}\n"]
    if chat_history:
        parts.append("CONVERSATION HISTORY:")
        for turn in chat_history:
            parts.append(f"User: {turn['question']}\nAssistant: {turn['answer']}")
        parts.append("")
    parts.append(f"USER REQUEST:\n{user_question}\n")

    failed_attempts = [h for h in history if h.get("error")]
    if failed_attempts:
        parts.append("PREVIOUS FAILED ATTEMPTS (fix these mistakes):")
        for h in failed_attempts:
            parts.append(f"Attempt {h['attempt']}:\nSQL: {h['sql']}\nError: {h['error']}\n")

    parts.append("Return only the corrected SQL statement." if failed_attempts else "Return only the SQL statement.")
    return "\n".join(parts)


FINAL_ANSWER_SYSTEM = """You turn a database query result into one short, clear natural-language answer \
for a non-technical user. Do not use markdown formatting (no bold asterisks like **, no list bullets like * or -, \
no markdown titles, etc.). Keep the response in plain text. Do not mention SQL, tables, or columns by name unless the \
user's question used those words. If the query result notes that sensitive columns were redacted, explain that the requested \
information cannot be disclosed and give the reason (specifically mentioning which sensitive columns were redacted \
for security). Be concise. If the result is empty, say so plainly."""


def build_final_answer_prompt(user_question: str, result_summary: str) -> str:
    return (
        f"USER QUESTION:\n{user_question}\n\n"
        f"QUERY RESULT:\n{result_summary}\n\n"
        "Write the final answer now."
    )
