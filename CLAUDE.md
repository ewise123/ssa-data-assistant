# SSA Data Assistant - Project Instructions

## What This Project Is

A FastAPI app that translates natural-language questions into safe, read-only SQL against the `Project_Master_Database` PostgreSQL schema. SSA Consultants ask questions in a browser UI, the backend uses OpenAI to generate SQL, validates it, executes it, and returns tabular results.

## Architecture

```
User (browser) → Static SPA (index.html + Tailwind + Anime.js)
                    ↓ POST /ask
              FastAPI backend (app/main.py)
                    ↓
        ┌───────────┼───────────────┐
        ↓           ↓               ↓
  Schema Router   OpenAI API    SQL Validator
  (catalog.py)   (ai_sql.py)  (sql_validator.py)
        ↓           ↓               ↓
        └───────────┼───────────────┘
                    ↓
           PostgreSQL (read-only)
                    ↓
           SQLite (query_metrics.db) ← analytics logging
```

## Tech Stack

- **Python 3.11+**, FastAPI, Pydantic
- **psycopg** (v3) for PostgreSQL (read-only connections)
- **OpenAI** Chat Completions (default model: `gpt-4.1-mini`, configurable via `OPENAI_MODEL` env var)
- **OpenAI** Embeddings (`text-embedding-3-small`) for RAG retrieval
- **ChromaDB** for vector storage (schema, golden queries, documentation)
- **MCP** (Model Context Protocol) server for Claude-native SQL generation
- **SQLite** for local analytics (`data/query_metrics.db`)
- **Static frontend**: single `index.html` with Tailwind CSS + Anime.js
- No ORM — raw parameterized SQL only

## Key Files

| File | Purpose |
|------|---------|
| `mcp_server.py` | MCP server: exposes schema, golden queries, and query execution as tools for Claude |
| `app/main.py` | FastAPI app, all routes, startup logic, env loading |
| `app/ai_sql.py` | OpenAI prompt construction, SQL generation + repair |
| `app/catalog.py` | DB introspection, schema routing, synonym matching |
| `app/db.py` | PostgreSQL connection management, `run_select()` |
| `app/sql_validator.py` | SQL safety validation (5-layer AST pipeline) |
| `app/rag.py` | ChromaDB RAG: SchemaRetriever, GoldenQueryStore, DocumentationStore |
| `app/config_loader.py` | Loads CSV/JSON config files from `app/config/` |
| `app/schema_hints.py` | Static dataset-level schema hints (fallback for catalog) |
| `app/schema_enrichment.py` | LLM-generated schema descriptions (M-Schema YAML) |
| `app/query_metrics.py` | SQLite analytics: record queries, fetch top/problem queries |
| `app/static/index.html` | Single-page frontend (759 lines, self-contained) |

## Configuration Files (`app/config/`)

| File | Format | Purpose |
|------|--------|---------|
| `*_aliases.csv` | CSV (canonical, alias) | Synonym mappings for clients, titles, tools, capabilities |
| `join_map.json` | JSON | Intent-based join paths with tables, joins, filters, defaults |
| `column_semantics.csv` | CSV | Semantic type + preferred filter per table.column |
| `disambiguation.json` | JSON | Keyword-to-dataset routing rules |
| `allowed_values/*.csv` | CSV (one value per line) | Enumerated valid values for specific columns |

## Request Flow (`POST /ask`)

1. `suggest_schema_snippet()` — scores tables/columns against the question using synonyms, join map intents, and disambiguation rules
2. `propose_sql()` — builds OpenAI prompt with system instructions, schema hint, intent guidance, few-shot examples, and user question
3. `validate_sql()` — ensures SELECT-only, no dangerous keywords, enforces LIMIT 100
4. `run_select()` — executes against PostgreSQL with 10s timeout
5. If execution fails or returns 0 rows → `propose_sql_repair()` for one retry
6. `record_query()` — logs to SQLite for analytics

## Running Locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Create .env with OPENAI_API_KEY, PG_DSN_READONLY, PG_SEARCH_PATH
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Serves the SPA |
| `/ask` | POST | NL → SQL → results (core pipeline) |
| `/projects` | GET | Distinct project names from ClientEngagement |
| `/analytics/common-queries` | GET | Top queries by frequency |
| `/analytics/problem-queries` | GET | Failed/empty queries |
| `/admin/problem-queries` | GET | HTML dashboard for problem queries (requires `ADMIN_TOKEN`) |
| `/admin/golden-queries` | GET | List verified golden queries (requires `ADMIN_TOKEN`) |
| `/admin/verifiable-queries` | GET | Queries available for verification (requires `ADMIN_TOKEN`) |
| `/admin/verify-query` | POST | Promote a query to golden (requires `ADMIN_TOKEN`) |
| `/feedback` | POST | Record user feedback (does NOT auto-verify) |
| `/debug/env` | GET | Environment/config status (requires `ENABLE_DEBUG_ENDPOINTS=true`) |
| `/debug/db` | GET | DB connectivity check (requires `ENABLE_DEBUG_ENDPOINTS=true`) |
| `/debug/dns` | GET | DNS resolution check (requires `ENABLE_DEBUG_ENDPOINTS=true`) |
| `/debug/router?q=...` | GET | Schema routing debug (requires `ENABLE_DEBUG_ENDPOINTS=true`) |
| `/debug/config` | GET | Config summary counts (requires `ENABLE_DEBUG_ENDPOINTS=true`) |
| `/debug/catalog/reload` | POST | Hot-reload catalog + config (requires `ENABLE_DEBUG_ENDPOINTS=true`) |

## MCP Server

The MCP server (`mcp_server.py`) exposes the same schema context, golden queries, and query execution as MCP tools — letting Claude generate SQL directly instead of routing through OpenAI.

### MCP Tools

| Tool | Purpose |
|------|---------|
| `get_schema(question)` | Hybrid vector + keyword schema retrieval with M-Schema descriptions |
| `get_golden_examples(question, k=3)` | Retrieve similar verified (question, SQL) pairs from ChromaDB |
| `execute_query(sql)` | Validate through 5-layer pipeline and execute read-only against PostgreSQL |
| `list_tables()` | List all tables with descriptions and column counts |

### Running the MCP Server

```bash
# stdio transport (for Claude Desktop / Claude Code)
python mcp_server.py

# HTTP transport (for remote access)
python mcp_server.py --transport streamable-http --port 8001
```

### Claude Code Configuration

Add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "ssa-data-assistant": {
      "command": "python",
      "args": ["/absolute/path/to/mcp_server.py"],
      "env": {
        "PG_DSN_READONLY": "...",
        "PG_SEARCH_PATH": "Project_Master_Database"
      }
    }
  }
}
```

The MCP server uses local embeddings (ChromaDB's built-in `all-MiniLM-L6-v2` via onnxruntime) — no OpenAI key or external API calls required. Vector data is stored separately in `data/chromadb_mcp/`.

## Coding Conventions

- **No ORM** — all SQL is raw, parameterized via `psycopg`
- **Schema-qualified identifiers** — always `"Project_Master_Database"."TableName"` with double quotes
- **Global mutable state** — `CATALOG`, `CATALOG_ERROR`, `CONFIG` in `main.py` (loaded at startup, reloadable via endpoint)
- **Dataclasses** for domain models (`Column`, `Table`, `ForeignKey`, `Catalog`, `SchemaHint`)
- **Pydantic** for API request/response models
- **TypedDict** for typed dict returns (`TopQueryRow`, `ProblemQueryRow`)
- **Context managers** for DB connections (`get_conn()`, `_conn()`)
- Environment loaded at module level in `main.py` before local imports

## Security Rules

- **Read-only DB access** — `PG_DSN_READONLY` user has SELECT-only permissions
- **SQL validation** — `validate_sql()` blocks INSERT/UPDATE/DELETE/ALTER/DROP/CREATE/GRANT/REVOKE/TRUNCATE/COPY, system catalogs (`pg_*`, `information_schema`), and comments
- **LIMIT 100** enforced on all queries
- **10-second statement timeout** on all DB connections
- **Secrets never sent to browser** — OpenAI key and DSN are server-side only
- `.env` is gitignored; production uses Azure App Settings / Key Vault
- HTML in admin dashboard uses `html.escape()` for XSS prevention
- **Debug endpoints gated** — all `/debug/*` return 404 unless `ENABLE_DEBUG_ENDPOINTS=true`
- **Admin endpoints require auth** — all `/admin/*` require `Authorization: Bearer <ADMIN_TOKEN>`
- **Feedback does not auto-verify** — positive feedback is recorded but does not promote queries to golden; admin must explicitly verify via `/admin/verify-query`
- **Sensitive configs gitignored** — `clients_aliases.csv` and `schema_descriptions.yaml` contain business data and are not committed; see `.example` files for format

## When Modifying Config

After changing files in `app/config/`:
1. No app restart needed — hit `POST /debug/catalog/reload`
2. Validate with `GET /debug/router?q=<test question>` and `POST /ask`
3. See `docs/ADD_NEW_DATA_WORKFLOW.md` for the full checklist

## Testing

There are currently **no automated tests** in this project. The `tests/` directory does not exist. When adding tests:
- Use `pytest` with `httpx.AsyncClient` for FastAPI endpoint testing
- Mock `OpenAI` calls and `run_select()` for unit tests
- The SQLite analytics DB is in `data/` (gitignored, created at runtime)

## Git Conventions

- Branch: `main` is the main branch
- `.gitignore`: `.venv/`, `__pycache__/`, `*.pyc`, `.env`, `data/`
- `data/query_metrics.db` is generated at runtime, never committed
