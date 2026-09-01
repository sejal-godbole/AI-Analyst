# AI Analyst Agent

A natural-language database analyst built with **raw LangGraph** and the **raw MCP Python SDK** —
no LangChain, no high-level agent framework. You ask a question or give a database instruction in
plain English; the system generates SQL, validates it against the real schema, checks it for safety,
executes it through a controlled MCP tool, and answers you in plain English.

```
"Which city has the most customers?"  ->  "Pune has the highest number of customers, with 1,250 customers."
```

## 1. What this project does

- Understands an arbitrary PostgreSQL schema (tables, columns, types, primary keys, foreign keys).
- Turns a natural-language request into SQL using an LLM.
- Parses and validates that SQL deterministically with `sqlglot` — no trusting the LLM's word.
- Blocks destructive administrative statements (DROP/TRUNCATE/ALTER/GRANT/REVOKE) unconditionally.
- Requires human confirmation for broad or ambiguous writes (UPDATE/DELETE affecting many rows).
- Executes only through a **separate MCP server process** that owns the database connection.
- Retries automatically (bounded) when SQL is invalid or execution fails, feeding the error back
  to the LLM so it can self-correct.
- Validates results before answering ("did this actually answer the question?").
- Writes an audit log row for every request.
- Never lets the LLM see database credentials, unnecessary raw rows, or configured sensitive columns.

## 2. Architecture

```mermaid
flowchart TD
    U[User] --> API[FastAPI /analyze]
    API --> G[LangGraph Agent]

    subgraph LG[LangGraph Workflow]
        RQ[receive_question] --> IS[inspect_schema]
        IS --> BSC[build_schema_context]
        BSC --> CI[classify_intent]
        CI --> GS[generate_sql]
        GS --> VS[validate_sql]
        VS -- invalid, retries left --> RETRY[increment_retry] --> GS
        VS -- invalid, exhausted --> ERR[error_terminal]
        VS -- valid --> SC[safety_check]
        SC -- unsafe --> ERR
        SC -- needs confirmation --> HC[human_confirmation interrupt]
        HC -- approved --> EQ[execute_query]
        HC -- rejected --> ERR
        SC -- safe --> EQ
        EQ -- failed, retries left --> RETRY
        EQ -- failed, exhausted --> ERR
        EQ -- success --> CR[check_result]
        CR -- ok --> FA[final_answer]
        CR -- suspicious, retries left --> RETRY
        CR -- suspicious, exhausted --> ERR
    end

    G --> LG
    IS -.MCP call.-> MCP[MCP Server]
    EQ -.MCP call.-> MCP
    MCP --> DB[(PostgreSQL)]
    GS -.reasoning only.-> LLM[LLM]
    CI -.reasoning only.-> LLM
    FA -.phrasing only.-> LLM
```

The system enforces this separation everywhere:

```
LLM       = reasoning / SQL text generation / natural-language phrasing
LangGraph = workflow orchestration, state, retries, guardrail decisions, human-in-the-loop
MCP       = controlled tool boundary — the only thing that can reach the database
Database  = actual data, actual credentials
```

`DATABASE_URL` is read in exactly two files: `app/database/connection.py` and (indirectly)
`app/mcp/tools.py`. It is never placed in `AgentState`, never sent to the LLM, and never returned
in an API response.

## 3. Why LangGraph

LangGraph gives this project three things a plain function-calling loop doesn't give for free:

- **Explicit state** (`app/agent/state.py`) — every field the workflow depends on is named and typed,
  so it's obvious what data flows between steps.
- **Conditional branching as a graph** (`app/agent/routing.py` + `app/agent/graph.py`) — the
  retry loop, the safety branch, and the confirmation branch are edges, not nested `if/else` — so the
  control flow is inspectable and testable independently of the LLM.
- **`interrupt()` for human-in-the-loop** — `human_confirmation` pauses the graph mid-execution and
  resumes exactly where it left off once the user approves or rejects, using a checkpointer
  (`MemorySaver`) keyed by `thread_id`.

## 4. Why MCP

MCP is the boundary that keeps the LLM away from the database. The FastAPI process never imports
`psycopg` directly for agent logic — LangGraph nodes call `app/mcp/client.py`, which spawns
`app/mcp/server.py` as a subprocess over stdio and calls its tools (`inspect_schema`,
`preview_query`, `execute_query`). Only the MCP server process ever opens a database connection.

This also gives **defense in depth**: even if a bug in LangGraph's validation somehow let bad SQL
through, `app/mcp/tools.py` re-validates every statement with `sqlglot` and re-runs the guardrail
checks before touching the database. The MCP server does not trust its caller.

```
LLM validation (none — LLM has no execution ability)
      v
LangGraph validation (sql_validator.py + guardrails.py, before calling MCP)
      v
MCP server validation (tools.py re-validates, independent of the caller)
      v
Database (constraints, foreign keys, permissions)
```

## 5. How schema discovery works

`app/database/schema_inspector.py` queries `information_schema.columns`,
`information_schema.table_constraints`, and `key_column_usage`/`constraint_column_usage` to build:

```json
{
  "tables": {
    "customers": {
      "columns": {"customer_id": "integer", "name": "character varying", "city": "character varying"},
      "primary_keys": ["customer_id"],
      "foreign_keys": []
    },
    "orders": {
      "columns": {"order_id": "integer", "customer_id": "integer", "amount": "numeric"},
      "primary_keys": ["order_id"],
      "foreign_keys": [{"column": "customer_id", "references_table": "customers", "references_column": "customer_id"}]
    }
  }
}
```

No row data is ever included — only structure. This is exposed as the MCP tool `inspect_schema`.

## 6. How relationships are discovered and used

Foreign keys pulled from `information_schema` are rendered as explicit arrows in the schema context
that's given to the LLM (`app/agent/nodes.py::build_schema_context`):

```
customers.customer_id -> orders.customer_id
orders.order_id -> order_items.order_id
products.product_id -> order_items.product_id
```

The SQL-generation prompt (`app/agent/prompts.py`) explicitly instructs the model to use only these
listed relationships for JOINs and never invent one.

## 7. How SQL generation works

`app/agent/nodes.py::generate_sql` sends the schema context, the user's question, and (on retry)
the previous error to the LLM via `app/agent/llm.py` (a thin OpenAI-compatible chat wrapper), at
temperature 0 for determinism. The response is stripped of markdown fences and stored as
`generated_sql`.

## 8. How hallucination is prevented

`app/security/sql_validator.py` parses the SQL with `sqlglot` (not regex) and extracts every table
and column actually referenced, then diffs them against the real schema dict. Any unknown table or
column fails validation immediately — the query never reaches the database. The error is stored in
`query_history` and fed back into the next `generate_sql` prompt, so the LLM sees exactly what it
got wrong (see the worked example in section 9 below).

## 9. How SQL validation works

For every candidate statement, `validate_sql()` determines:

- syntactic validity (via `sqlglot.parse`)
- exactly one statement present (rejects `SELECT ...; DROP ...;`-style stacking)
- the operation type (SELECT/INSERT/UPDATE/DELETE — anything else is rejected)
- every referenced table exists in the schema
- every referenced column exists in one of the referenced tables
- whether UPDATE/DELETE has a WHERE clause
- whether a blocked administrative keyword (DROP/TRUNCATE/ALTER/GRANT/REVOKE) is present

Worked hallucination-correction example (see `tests/test_agent.py::test_hallucinated_table_then_correction`):

```
Attempt 1: SELECT * FROM users
Error:     Unknown table(s) referenced: users. Known tables: customers.
Attempt 2: SELECT * FROM customers
Result:    valid — proceeds to safety_check
```

## 10. How guardrails work

`app/security/guardrails.py` makes the allow/confirm/reject decision from the validator's parsed
result — never from the LLM's self-reported intent (section 24 of the original spec: "do not trust
LLM classification").

| Statement | Decision |
|---|---|
| Any DROP/TRUNCATE/ALTER/GRANT/REVOKE | **Rejected**, always |
| `DELETE` with no `WHERE` | **Rejected**, always |
| `DELETE ... WHERE ...` | Allowed; confirmation per `REQUIRE_WRITE_CONFIRMATION` / row-threshold policy |
| `UPDATE` with no `WHERE` | Allowed **only** with explicit human confirmation (never silently run) |
| `UPDATE ... WHERE ...` | Allowed; confirmation per policy |
| `INSERT` | Allowed; confirmation per policy |
| `SELECT` | Always allowed, no confirmation |

## 11. How INSERT/UPDATE/DELETE are handled

All three are generated, validated, and guardrail-checked the same way as SELECT — this system is
not read-only. The differences are: they go through the row-impact preview (`preview_query`, an
`EXPLAIN`-based estimate) so guardrails can decide whether confirmation is warranted, and their
success is measured by `rowcount` rather than returned rows.

## 12. How destructive commands are blocked

Two independent checks catch them: `sql_validator.py` scans for the blocked-keyword list before
even attempting schema-conformance checks, and `guardrails.py` treats `is_destructive=True` as an
unconditional rejection with no confirmation path — there is no way to "approve" a DROP.

## 13. How human confirmation works

For a broad write, `safety_check` returns `safety_status = "needs_confirmation"` and a rendered
message including the SQL and the estimated row impact. The graph routes to `human_confirmation`,
which calls LangGraph's `interrupt()`, pausing execution. `app/api/routes.py` detects the
`__interrupt__` key on the returned state and responds with `status: "awaiting_confirmation"` plus
a `thread_id`. The client calls `/analyze` again with the same `thread_id` and `confirm: true/false`;
this resumes the exact same graph run via `Command(resume=...)` against the `MemorySaver`
checkpoint.

## 14. How retries work

`increment_retry` bumps `retry_count`, then loops back to `generate_sql`. This happens from three
places: invalid SQL, failed execution, and suspicious results — each capped by `MAX_RETRIES`
(default 3). `query_history` accumulates every failed attempt's SQL and error so each retry's prompt
includes the full correction context, not just the latest failure.

## 15. How result validation works

`check_result` (`app/agent/nodes.py`) treats an empty SELECT result as valid-but-notable (it may be
the correct answer — "no matching rows"), but treats a 0-row UPDATE/DELETE as suspicious (the WHERE
clause likely didn't match what the user intended), routing it back into the retry loop.

## 16. How audit logging works

`app/logging/audit.py` writes one row per terminal state (success or failure) to the
`agent_audit_log` table (created in `sample_db/init.sql`): the question, intent, final SQL,
validation/execution status, error, retry count, rows affected, a short result summary (not raw
rows), and confirmation status. Audit failures are logged but never crash the request.

## 17. How sensitive data is protected

`app/security/pii_filter.py` strips any column named in `SENSITIVE_COLUMNS` (configurable, e.g.
`email,phone,password,ssn,aadhaar,credit_card,salary`) out of result rows before they're sent to the
LLM for final-answer phrasing — even if the underlying SQL was a legitimate `SELECT *`. The
SQL-generation prompt also nudges the LLM toward aggregate queries (`COUNT`, `SUM`) for
yes/no or "how many" questions, so unnecessary raw rows are avoided in the first place. Row volume
is separately capped by `MAX_ROWS` (enforced server-side in `app/mcp/tools.py`, not just requested
of the LLM).

## 18. Project structure

```
ai-analyst/
├── app/
│   ├── main.py                  FastAPI entrypoint
│   ├── config.py                Settings (env vars only)
│   ├── api/routes.py            POST /analyze
│   ├── agent/
│   │   ├── state.py             AgentState TypedDict
│   │   ├── graph.py             StateGraph wiring + compilation
│   │   ├── nodes.py             Node implementations
│   │   ├── routing.py           Conditional-edge functions
│   │   ├── prompts.py           LLM prompt templates
│   │   └── llm.py               OpenAI-compatible chat wrapper
│   ├── mcp/
│   │   ├── server.py            Raw MCP SDK server (stdio) — owns the DB connection
│   │   ├── client.py            Raw MCP SDK client — spawns the server, calls tools
│   │   └── tools.py             Tool implementations (inspect_schema/preview_query/execute_query)
│   ├── database/
│   │   ├── connection.py        psycopg connection (DATABASE_URL lives here)
│   │   └── schema_inspector.py  information_schema-based metadata discovery
│   ├── security/
│   │   ├── sql_validator.py     sqlglot-based parsing/validation
│   │   ├── guardrails.py        Allow/confirm/reject policy
│   │   └── pii_filter.py        Sensitive-column stripping
│   ├── models/schemas.py        Pydantic request/response models
│   └── logging/audit.py         Audit log writer
├── tests/
├── sample_db/init.sql           Sample schema + seed data + audit table
├── requirements.txt
├── .env.example
├── Dockerfile
└── docker-compose.yml
```

## 19. Running it

### Option A — Docker Compose (Postgres + app)

```bash
cp .env.example .env
# edit .env and set LLM_API_KEY to a Gemini key from https://aistudio.google.com/apikey

docker compose up --build
```

The API is then at `http://localhost:8000`.

### Option B — Manual / local Python

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# edit .env: set LLM_API_KEY to a Gemini key (https://aistudio.google.com/apikey),
# and DATABASE_URL if not using the default

# 4. Start PostgreSQL (Docker, just the database)
docker run -d --name ai_analyst_pg \
  -e POSTGRES_USER=analyst_user -e POSTGRES_PASSWORD=analyst_pass -e POSTGRES_DB=ai_analyst \
  -p 5432:5432 postgres:16

# 5. Initialize the sample database
psql postgresql://analyst_user:analyst_pass@localhost:5432/ai_analyst -f sample_db/init.sql

# 6. (Optional) Start the MCP server standalone, to test it in isolation
python -m app.mcp.server

# 7. Start the FastAPI application (this spawns its own MCP client/server per request)
uvicorn app.main:app --reload

# 8. Test the API
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"question": "Which city has the most customers?"}'

# Example write requiring confirmation:
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"question": "Update the monthly charge of all customers to 999"}'
# -> {"status": "awaiting_confirmation", "thread_id": "...", "confirmation_message": "...", ...}

curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "<the thread_id from above>", "confirm": true, "question": ""}'

# 9. Run the automated tests
# (sql_validator / guardrails / routing / mocked-agent tests need no live DB or LLM key)
pytest tests/test_sql_validator.py tests/test_guardrails.py tests/test_agent.py -v

# schema/mcp integration tests require a live DATABASE_URL:
DATABASE_URL=postgresql://analyst_user:analyst_pass@localhost:5432/ai_analyst pytest tests/ -v
```

## 20. Example requests

**Read:**
```json
{"question": "How many customers are from Pune?"}
```

**Insert:**
```json
{"question": "Add a new customer named Rahul from Mumbai"}
```

**Blocked (destructive):**
```json
{"question": "Drop the customers table"}
```
Response: `{"status": "rejected", "error": "Statement contains blocked administrative keyword: DROP."}`

**Blocked (unfiltered delete):**
```json
{"question": "Delete all customers"}
```
Response: `{"status": "rejected", "error": "DELETE without a WHERE clause would remove all rows and is blocked..."}`

## 21. Known simplifications (this is a learning project, not production)

- `app/mcp/client.py` spawns a fresh MCP server subprocess per call for simplicity; a production
  system would keep one long-lived session.
- `app/database/connection.py` opens a new connection per call rather than pooling
  (`psycopg_pool.ConnectionPool` is the natural upgrade).
- The confirmation checkpointer (`MemorySaver`) is in-memory and will lose paused workflows on
  restart — swap for `langgraph.checkpoint.postgres.PostgresSaver` for durability.
- `preview_query`'s row-count estimate comes from PostgreSQL's query planner (`EXPLAIN`), which is
  an estimate, not an exact count.
