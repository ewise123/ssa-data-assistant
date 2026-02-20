# App Architecture Report: SSA Data Assistant

## 1. Overview

| Field | Value |
|-------|-------|
| **App Name** | SSA Data Assistant |
| **Purpose** | A natural-language-to-SQL query tool. SSA & Co employees type plain-English questions in a browser UI; the backend uses OpenAI to generate safe, read-only SQL against the `Project_Master_Database` PostgreSQL schema, validates it, executes it, and returns tabular results. |
| **Primary Users** | SSA & Co Employees |
| **Access Scope** | Internal only |
| **Built By / Maintained By** | Emory Wise |
| **First Deployed** | October 23, 2025 |
| **Current Status** | Active — in development, not yet hosted in production |

---

## 2. Tech Stack

### Frontend

- **Framework / Library**: No framework — plain vanilla JavaScript in a single self-contained HTML file (`app/static/index.html`, 759 lines)
- **Language**: JavaScript (ES6+), no TypeScript, no build step
- **Styling**: Tailwind CSS v3+ (loaded from CDN with `forms` and `container-queries` plugins). Custom theme extends colors (`primary` #DE4702, `header-bg` #003399, `cool-gray`, `sky-blue`, `navy-slate`), fonts (`Inter` display, `Fira Code` mono), and border-radius defaults. Dark mode enabled via `darkMode: "class"`.
- **Build Tool**: None — no bundler, no transpiler, everything served as-is
- **Key Dependencies** (all via CDN):

  | Package | Version | Purpose |
  |---------|---------|---------|
  | Anime.js | 3.2.1 | Micro-animations (button bounces, progress bar, toast notifications, panel expand/collapse, row stagger, error shake). Graceful fallback if CDN fails. Respects `prefers-reduced-motion`. |
  | Google Fonts | — | Inter (400/500/600/700), Fira Code |
  | Google Material Symbols | — | Icon library (Outlined variant) |

- **Notable Frontend Features**: Dark mode toggle with `localStorage` persistence + system preference detection; collapsible "Projects" accordion (lazy-loaded); common queries dropdown; copy-SQL-to-clipboard with toast; responsive table with sticky header; ARIA labels and semantic HTML for accessibility.

### Backend

- **Framework**: FastAPI 0.115.0
- **Language / Runtime**: Python 3.11+
- **ASGI Server**: Uvicorn 0.30.6 (with `standard` extras)
- **Key Dependencies** (`requirements.txt`):

  | Package | Version | Purpose |
  |---------|---------|---------|
  | `fastapi` | 0.115.0 | Web framework, route definitions, Pydantic integration |
  | `uvicorn[standard]` | 0.30.6 | ASGI server |
  | `psycopg[binary]` | 3.2.11 | PostgreSQL v3 driver (primary DB driver) |
  | `pydantic` | 2.9.2 | Request/response validation |
  | `python-dotenv` | 1.0.1 | `.env` file loading for local dev |
  | `httpx` | 0.27.2 | Async HTTP client (available but not heavily used in app code) |
  | `openai` | 1.51.2 | OpenAI Chat Completions API client |
  | `SQLAlchemy` | 2.0.34 | **Installed but NOT imported or used** — legacy/unused |
  | `psycopg2-binary` | 2.9.9 | **Installed but NOT used** — redundant with psycopg v3 |

### Databases

**PostgreSQL (primary — read-only)**

- **Type & Engine**: PostgreSQL (version not pinned in code)
- **Hosting**: Not confirmed — Azure Key Vault integration suggests Azure
- **ORM / Query Layer**: No ORM — raw parameterized SQL via `psycopg` v3. Schema-qualified identifiers: `"Project_Master_Database"."TableName"` with double quotes.
- **Migration Tool**: None — schema is externally managed; app has read-only access
- **Connection Pattern**: Direct connections (no pooling). New `psycopg.connect(dsn)` per request via context manager `get_conn()`. Sets `search_path`, `statement_timeout = '10s'`, `application_name = 'ssa-data-assistant'`, `row_factory = dict_row`.
- **Schema Notes**: Single schema `Project_Master_Database`. Tables include ClientList, ClientEngagement, ConsultantRoster, TitleMaster, FirmTool, ResourceTool, FirmCapability, ResourceCapability, ICRoster, ICSSAContact, Course, CourseCapability, CourseTool, ProjectTeam. UUID-based IDs on IC tables. DB user is `chat_reader` with SELECT-only permissions.

**SQLite (analytics — local)**

- **Type & Engine**: SQLite 3
- **Hosting**: Local file at `data/query_metrics.db` (gitignored, created at runtime)
- **ORM / Query Layer**: Raw SQL via Python's built-in `sqlite3` module
- **Migration Tool**: None — table auto-created by `_ensure_database()` on first use
- **Connection Pattern**: Context manager `_conn()` per operation
- **Schema Notes**: Single `query_log` table tracking: id, question, dataset, status (ok/empty/error), row_count, error_message, canonical_question, created_at. Indexes on question, status, canonical_question.

---

## 3. Authentication & Authorization

### Authentication

- **Method**: **None in application code**. No login routes, no OAuth, no session handling, no API key validation for client-facing endpoints.
- **Flow**: Users access the app directly. No redirect, no token exchange. The app is presumed to sit behind a reverse proxy or Azure App Service authentication in production, but this is configured externally — no auth code exists in the repo.
- **Session Management**: None — stateless API. No cookies, no JWTs, no localStorage tokens (beyond theme preference).
- **Domain/Tenant Restriction**: None enforced in code.

### Authorization

- **Model**: No authorization model. All users have the same access.
- **Roles Defined**: None
- **How Enforced**: Not enforced in code. One exception: `POST /debug/catalog/reload` accepts an optional bearer token via the `CATALOG_RELOAD_TOKEN` env var. If set, requests must include `Authorization: Bearer <token>`. Returns 401 (missing) or 403 (invalid). If the env var is not set, the endpoint is unprotected.

---

## 4. External Services & Integrations

| Service | Purpose | Direction | How Connected | Auth Method |
|---------|---------|-----------|---------------|-------------|
| **OpenAI API** | NL-to-SQL generation via Chat Completions (`propose_sql()`, `propose_sql_repair()`) | Outbound (app to OpenAI) | REST API via `openai` Python SDK. Model: `gpt-4o-mini` (default, configurable via `OPENAI_MODEL`). Temperature: 0. | API key via `OPENAI_API_KEY` env var |
| **Azure Key Vault** (optional) | Secret retrieval for production (`OPENAI_API_KEY`, `PG_DSN_READONLY`, `PG_SEARCH_PATH`) | Outbound (app to Azure) | Azure SDK via `azure.identity.DefaultAzureCredential` + `azure.keyvault.secrets.SecretClient`. Gracefully skipped if packages not installed. | `DefaultAzureCredential` (managed identity / CLI / env-based) |
| **Azure PostgreSQL** | Read-only query execution against `Project_Master_Database` | Outbound (app to PostgreSQL) | Direct TCP via `psycopg` v3 using `PG_DSN_READONLY` connection string | PostgreSQL user credentials in DSN |

No inbound webhooks, no third-party analytics, no email services, no file storage services.

---

## 5. Additional Infrastructure Patterns

| Pattern | Status |
|---------|--------|
| Background Jobs / Cron | None |
| File Storage | None — no uploads, no cloud storage. Only static assets served from `app/static/`. |
| WebSocket / Real-Time | None — purely request/response HTTP |
| Caching | None — no Redis, no in-memory cache. Global `CATALOG` and `CONFIG` dicts are loaded at startup and held in memory but are not a cache layer. |
| Message Queues / Event Buses | None |
| Static Assets / CDN | Frontend loads Tailwind CSS, Anime.js, Google Fonts, and Material Symbols from public CDNs. No self-hosted CDN. |

---

## 6. Environment Variables & Secrets

| Variable Name | Category | Description | Where Used | Required |
|---------------|----------|-------------|------------|----------|
| `OPENAI_API_KEY` | External Service | OpenAI API authentication key | `app/ai_sql.py`, validated in `app/main.py` | Yes |
| `PG_DSN_READONLY` | Database | PostgreSQL read-only connection string | `app/db.py`, validated in `app/main.py` | Yes |
| `PG_SEARCH_PATH` | Database | Schema name for queries (default: `"Project_Master_Database"`) | `app/db.py` | Yes (has default) |
| `OPENAI_MODEL` | External Service | OpenAI model override (default: `"gpt-4o-mini"`) | `app/ai_sql.py` | No |
| `AZURE_KEY_VAULT_URL` | Auth / Infra | Azure Key Vault URL for production secrets | `app/main.py` | No |
| `SSA_KEY_VAULT_SECRETS` | Auth / Infra | Comma-separated secret names to pull from Key Vault (default: `"OPENAI_API_KEY,PG_DSN_READONLY,PG_SEARCH_PATH"`) | `app/main.py` | No |
| `CATALOG_RELOAD_TOKEN` | App Config | Bearer token to protect `/debug/catalog/reload` | `app/main.py` | No |

**Secret Loading Order** (in `app/main.py`, `load_environment()`):
1. Azure Key Vault (if `AZURE_KEY_VAULT_URL` is set and Azure SDK is installed)
2. Already-set environment variables (platform injection)
3. `.env` file (local development, via `python-dotenv`)

Startup validates that `OPENAI_API_KEY`, `PG_DSN_READONLY`, and `PG_SEARCH_PATH` are available after loading. Warns on missing but does not crash.

---

## 7. Deployment & Infrastructure

- **Hosting Platform**: Not yet hosted. Code includes Azure Key Vault integration for future production deployment. No `Dockerfile`, `Procfile`, or CI/CD config files exist in the repo.
- **Deployment Method**: Not yet deployed. No deployment configuration checked into the repo.
- **Build & Start Commands**:
  - **Production**: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
  - **Development**: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
  - **Setup**: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- **Environment(s)**: Local development only (via `.env` file). Azure Key Vault integration prepared for future production.
- **Domain / URL**: None — not yet hosted
- **SSL/TLS**: N/A — not yet hosted

### Architecture Pattern

- **Monolith or Separate Services**: Monolithic single deploy — FastAPI serves both the API and the static frontend.
- **How Frontend is Served**: Static `index.html` served by FastAPI's built-in `StaticFiles` middleware at `/static` and a `FileResponse` at `/`. No separate frontend host. No SSR. No build step.

---

## 8. Deployment Readiness Assessment

| Check | Status | Notes |
|-------|--------|-------|
| Health Check Endpoint | Missing | No dedicated `/health` endpoint. `/debug/db` and `/debug/env` are proxies but not optimized for load balancer health checks. |
| Error Handling | Pass | Global try/except in `/ask` route with structured error responses. Custom `CatalogLoadError`. `HTTPException` for 400/401/403/500. No global exception handler middleware. |
| Logging | Missing | Uses `print()` with prefix tags (`[startup]`, `[catalog]`, `[ask]`, etc.) to stdout. No structured logging, no Python `logging` module, no JSON logs, no log levels. |
| Monitoring / Alerting | Missing | No APM configured. No Sentry, Datadog, Azure Monitor, or equivalent. |
| Secrets Management | Pass | Properly externalized — env vars + Azure Key Vault integration. No hardcoded secrets. `.env` is gitignored. |
| Input Validation | Pass | Pydantic models for API requests. SQL validation via `validate_sql()` (keyword blocklist, LIMIT enforcement). Column semantics and allowed values for query generation. |
| Rate Limiting | Missing | No rate limiting on any endpoint. |
| CORS Configuration | Missing | No CORS middleware configured. FastAPI defaults apply. |
| Database Backups | Unknown | Cannot determine from code — externally managed. |
| Dependency Security | Missing | SQLAlchemy and psycopg2-binary are installed but unused — unnecessary attack surface. No `pip audit` or security scanning configured. |
| Documentation | Pass | Comprehensive README.md, user guide, schema change runbook, schema SQL export and ERD in `docs/schema/`. |
| Environment Separation | Missing | No distinct configs for dev/staging/production. Single `requirements.txt` and env var loading logic covers all environments. |
| Automated Tests | Missing | No tests exist. No `tests/` directory. No test framework configured. |

### Additional Notes

- Debug endpoints (`/debug/env`, `/debug/dns`, `/debug/db`, `/debug/router`, `/debug/config`) are exposed without authentication — should be protected or removed in production.
- No connection pooling for PostgreSQL — new connection per request may be a bottleneck under load.
- SQLAlchemy and psycopg2-binary in `requirements.txt` are unused and could be removed.
- All database operations are synchronous despite FastAPI being async — potential throughput concern.
- Admin dashboard at `/admin/problem-queries` uses `html.escape()` for XSS prevention (good).

---

## 9. All API Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/` | GET | None | Serves the SPA (`index.html`) |
| `/ask` | POST | None | Core NL-to-SQL-to-results pipeline |
| `/projects` | GET | None | Distinct project names from ClientEngagement |
| `/analytics/common-queries` | GET | None | Top queries by frequency |
| `/analytics/problem-queries` | GET | None | Failed/empty queries |
| `/admin/problem-queries` | GET | None | HTML dashboard for problem queries |
| `/debug/env` | GET | None | Environment/config status |
| `/debug/dns` | GET | None | DNS resolution check for PG host |
| `/debug/db` | GET | None | PostgreSQL connectivity check |
| `/debug/router` | GET | None | Schema routing debug (`?q=...`) |
| `/debug/config` | GET | None | Config file summary counts |
| `/debug/catalog/reload` | POST | Optional bearer token | Hot-reload catalog + config files |

---

## 10. Configuration Files (`app/config/`)

| File | Format | Purpose |
|------|--------|---------|
| `join_map.json` | JSON | 10+ intent-based join paths mapping question intents to table join graphs |
| `disambiguation.json` | JSON | 7 keyword-to-dataset routing rules (IC, tools, capabilities, MDs, clients, engagements, training) |
| `column_semantics.csv` | CSV (110 rows) | Per-column metadata: semantic type, preferred filter, pattern, notes |
| `clients_aliases.csv` | CSV | 4 canonical client names with synonym variants |
| `titles_aliases.csv` | CSV | 14 job title synonym mappings |
| `tools_aliases.csv` | CSV | 25 tool synonym mappings |
| `capabilities_aliases.csv` | CSV | 40 capability synonym mappings |
| `allowed_values/engagement_status.csv` | CSV | 6 engagement statuses |
| `allowed_values/industries.csv` | CSV | 15 industry values |
| `allowed_values/role_rank.csv` | CSV | 7 role ranks |
| `allowed_values/geographic_presence.csv` | CSV | 8 geographic regions |

---

## 11. Project File Structure

```
ssa-data-assistant/
├── .gitignore
├── .env                               # Local secrets (gitignored)
├── README.md                          # Project documentation (159 lines)
├── CLAUDE.md                          # AI assistant instructions
├── requirements.txt                   # 9 Python packages
├── app/
│   ├── __init__.py
│   ├── main.py                        # FastAPI app, all routes, startup (759 lines)
│   ├── ai_sql.py                      # OpenAI prompt construction, SQL generation + repair
│   ├── catalog.py                     # DB introspection, schema routing, synonym matching
│   ├── db.py                          # PostgreSQL connection management
│   ├── sql_validator.py               # SQL safety validation (SELECT-only, keyword blocklist)
│   ├── config_loader.py               # CSV/JSON config file loading
│   ├── schema_hints.py                # Static dataset-level schema hints (fallback)
│   ├── query_metrics.py               # SQLite analytics logging
│   ├── config/                        # Configuration files
│   │   ├── join_map.json
│   │   ├── disambiguation.json
│   │   ├── column_semantics.csv
│   │   ├── clients_aliases.csv
│   │   ├── titles_aliases.csv
│   │   ├── tools_aliases.csv
│   │   ├── capabilities_aliases.csv
│   │   └── allowed_values/
│   │       ├── engagement_status.csv
│   │       ├── industries.csv
│   │       ├── role_rank.csv
│   │       └── geographic_presence.csv
│   └── static/
│       ├── index.html                 # Single-page SPA (759 lines)
│       └── assets/
│           └── logo.svg
├── docs/
│   ├── ARCHITECTURE.md                # This file
│   ├── USING_SSA_DATA_ASSISTANT.md    # User guide
│   ├── ADD_NEW_DATA_WORKFLOW.md       # Schema change runbook
│   └── schema/
│       ├── Project_Master_Database_ERD_2025-11-06.pgerd
│       └── Project_Master_Database_schema_v3_2025-11-06.sql
└── data/
    └── query_metrics.db               # SQLite analytics (runtime, gitignored)
```
