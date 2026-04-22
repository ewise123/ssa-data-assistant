# SSA Data Assistant

A FastAPI app that lets SSA Consultants ask natural-language questions and get tabular answers from the `Project_Master_Database` PostgreSQL schema. Questions are translated into safe, read-only SQL — either via OpenAI (web UI) or via the built-in MCP server (Claude Desktop / Claude Code).

## Table of Contents
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [Environment Variables & Secrets](#environment-variables--secrets)
- [Running the App](#running-the-app)
- [MCP Server](#mcp-server)
- [RAG / Vector Store](#rag--vector-store)
- [Refreshing Catalog / Config](#refreshing-catalog--config)
- [API Endpoints](#api-endpoints)
- [User Documentation](#user-documentation)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

---

## Architecture

| Layer              | Technology / Notes                                                                 |
|--------------------|-------------------------------------------------------------------------------------|
| Backend API        | FastAPI (`/ask`, `/admin/*`, `/analytics/*`, `/debug/*`)                            |
| SQL generation     | OpenAI Chat Completions, model configurable via `OPENAI_MODEL` (default `gpt-4.1-mini`) |
| Retrieval          | ChromaDB vector store for schema context, golden queries, and documentation        |
| MCP server         | `mcp_server.py` — exposes schema, golden examples, and query execution as MCP tools |
| Database           | Azure PostgreSQL (read-only DSN, schema `Project_Master_Database`)                 |
| DB access          | `psycopg` v3, raw parameterized SQL, 10s statement timeout                         |
| SQL safety         | 5-layer AST validator in `app/sql_validator.py`                                    |
| Frontend           | Static `app/static/index.html` — Tailwind + Anime.js, single-page                  |
| Configuration      | CSV/JSON under `app/config/` (aliases, join map, column semantics, disambiguation) |
| Analytics          | SQLite (`data/query_metrics.db`) — common queries, problem queries, golden set     |

See `docs/ARCHITECTURE.md` and `docs/ssa-data-assistant-architecture.svg` for the full diagram.

---

## Prerequisites

- Python 3.11+
- Access to Azure PostgreSQL read-only DSN
- OpenAI API key (web UI only — the MCP server runs fully local embeddings)

---

## Local Development

1. **Clone & create virtual environment**
   ```bash
   git clone <repo-url>
   cd ssa-data-assistant
   python -m venv .venv
   source .venv/bin/activate   # macOS/Linux/WSL
   # .\.venv\Scripts\activate  # Windows PowerShell
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create `.env`**
   ```
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-4.1-mini
   PG_DSN_READONLY=postgresql://user:pass@host:port/postgres?sslmode=require
   PG_SEARCH_PATH=Project_Master_Database
   ADMIN_TOKEN=<any-long-random-string>
   ENABLE_DEBUG_ENDPOINTS=true
   ```

4. **Run server**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

5. **Open UI**
   Visit `http://localhost:8000/`.

---

## Environment Variables & Secrets

| Variable                  | Required | Description                                                          |
|---------------------------|----------|----------------------------------------------------------------------|
| `OPENAI_API_KEY`          | Yes (web UI) | Server-side OpenAI key                                            |
| `OPENAI_MODEL`            | No       | Chat model for SQL generation (default `gpt-4.1-mini`)               |
| `PG_DSN_READONLY`         | Yes      | PostgreSQL read-only DSN                                             |
| `PG_SEARCH_PATH`          | Yes      | Schema to introspect (default `Project_Master_Database`)             |
| `ADMIN_TOKEN`             | Prod     | Bearer token required for all `/admin/*` endpoints                   |
| `ENABLE_DEBUG_ENDPOINTS`  | No       | Set `true` to expose `/debug/*` (default off; 404 otherwise)         |
| `CATALOG_RELOAD_TOKEN`    | No       | Optional extra token for `/debug/catalog/reload`                     |
| `AZURE_KEY_VAULT_URL`     | No       | Azure Key Vault URL for production secret loading                    |
| `SSA_KEY_VAULT_SECRETS`   | No       | Comma-separated secret names to pull from Key Vault                  |

Secrets are never exposed to the browser. `.env` is gitignored; production uses Azure App Settings / Key Vault.

---

## Running the App

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## MCP Server

`mcp_server.py` lets Claude (Desktop, Code, or any MCP client) query the database directly — no OpenAI involved. It exposes four tools:

| Tool                              | Purpose                                                               |
|-----------------------------------|-----------------------------------------------------------------------|
| `get_schema(question)`            | Hybrid vector + keyword schema retrieval with M-Schema descriptions   |
| `get_golden_examples(question, k)`| Retrieve similar verified (question, SQL) pairs                       |
| `execute_query(sql)`              | Run SQL through the 5-layer validator and execute read-only           |
| `list_tables()`                   | List all tables with descriptions and column counts                   |

**Run locally:**
```bash
# stdio (for Claude Desktop / Claude Code)
python mcp_server.py

# HTTP (for remote access)
python mcp_server.py --transport streamable-http --port 8001
```

**Claude Code config** (`~/.claude/settings.json`):
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

The MCP server uses local embeddings (ChromaDB's `all-MiniLM-L6-v2` via onnxruntime) — **no OpenAI key required**. Its vector store lives in `data/chromadb_mcp/`, separate from the web-app store.

---

## RAG / Vector Store

`app/rag.py` defines three ChromaDB-backed stores:

- **`SchemaRetriever`** — embeds table/column descriptions for hybrid semantic + keyword schema selection
- **`GoldenQueryStore`** — stores verified (question, SQL) pairs promoted via `/admin/verify-query`
- **`DocumentationStore`** — arbitrary markdown docs for in-context reference

Web app uses OpenAI embeddings (`text-embedding-3-small`); MCP server uses local embeddings. Stores are persisted under `data/chromadb*/`.

Schema descriptions in M-Schema YAML format are generated by `python -m app.schema_enrichment` into `app/config/schema_descriptions.yaml` (gitignored).

---

## Refreshing Catalog / Config

When tables/columns change, or you edit anything under `app/config/`:

1. (If schema changed) apply DB migrations.
2. (If you want fresh descriptions) regenerate `schema_descriptions.yaml`.
3. Hot-reload without restart: `POST /debug/catalog/reload`.
4. Validate with `/debug/router?q=<test question>` and `POST /ask`.

See **[docs/ADD_NEW_DATA_WORKFLOW.md](docs/ADD_NEW_DATA_WORKFLOW.md)** for the full checklist.

---

## API Endpoints

### Public
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Serves the SPA |
| `/ask` | POST | NL → SQL → results (core pipeline) |
| `/projects` | GET | Distinct project names from `ClientEngagement` |
| `/feedback` | POST | Record user feedback on a query (does not auto-verify) |
| `/analytics/common-queries` | GET | Top queries by frequency |
| `/analytics/problem-queries` | GET | Failed / empty queries |

### Admin (require `Authorization: Bearer <ADMIN_TOKEN>`)
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/problem-queries` | GET | HTML dashboard for problem queries |
| `/admin/golden-queries` | GET | List verified golden queries |
| `/admin/verifiable-queries` | GET | Candidates available for promotion |
| `/admin/verify-query` | POST | Promote a query to golden |

### Debug (require `ENABLE_DEBUG_ENDPOINTS=true`; return 404 otherwise)
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/debug/env` | GET | Environment/config status |
| `/debug/db` | GET | DB connectivity check |
| `/debug/dns` | GET | DNS resolution check |
| `/debug/router?q=...` | GET | Schema routing debug |
| `/debug/config` | GET | Config summary counts |
| `/debug/catalog/reload` | POST | Hot-reload catalog + config |

---

## User Documentation

- **How to use the assistant**: [docs/USING_SSA_DATA_ASSISTANT.md](docs/USING_SSA_DATA_ASSISTANT.md)
- **Architecture**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Adding new data**: [docs/ADD_NEW_DATA_WORKFLOW.md](docs/ADD_NEW_DATA_WORKFLOW.md)
- **Onboarding (new contributors)**: [docs/ONBOARDING.md](docs/ONBOARDING.md)
- **Test questions**: [docs/test_questions.md](docs/test_questions.md)

---

## Security Considerations

- **Read-only DB user** — `PG_DSN_READONLY` must have SELECT-only permissions.
- **SQL validator** — blocks INSERT/UPDATE/DELETE/ALTER/DROP/CREATE/GRANT/REVOKE/TRUNCATE/COPY, `pg_*` / `information_schema`, and SQL comments. Enforces a single `SELECT` with `LIMIT 100`.
- **10-second statement timeout** on all DB connections.
- **Secrets are server-side only** — the frontend never contains or transmits the OpenAI key or DSN.
- **`.env` is gitignored** — production secrets come from Azure App Settings / Key Vault.
- **Debug endpoints are off by default** — return 404 unless `ENABLE_DEBUG_ENDPOINTS=true`.
- **Admin endpoints require a bearer token** — unavailable until `ADMIN_TOKEN` is set.
- **Feedback does not auto-promote** — positive feedback is recorded but must be explicitly verified via `/admin/verify-query` to become a golden example.
- **Sensitive configs gitignored** — `clients_aliases.csv` and `schema_descriptions.yaml` contain business data; see `.example` files for format.
- Admin HTML is escaped via `html.escape()` for XSS prevention.

---

## Troubleshooting

| Issue                                | Suggested Action                                                  |
|--------------------------------------|-------------------------------------------------------------------|
| `OPENAI_API_KEY not configured`      | Set the env var or add to `.env`.                                 |
| DB connection errors                 | Check VPN, firewall, and `PG_DSN_READONLY`.                       |
| Catalog stale after config edit      | Hit `POST /debug/catalog/reload`.                                 |
| Wrong table picked for a question    | `GET /debug/router?q=...` to see routing scores; add aliases.     |
| MCP server can't find embeddings     | Delete `data/chromadb_mcp/` and re-run; it rebuilds on startup.   |
| `schema_descriptions.yaml` missing   | Run `python -m app.schema_enrichment`.                            |

---

## Contributing

1. Branch from `main` (never commit directly to `main`).
2. Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`.
3. Update config docs if `app/config/` changes.
4. Don't commit `data/` (gitignored; generated at runtime).
5. Open a PR; for feature branches, run `/autofix-pr` to monitor CI.

For questions, reach out to the Solutions CoE.
