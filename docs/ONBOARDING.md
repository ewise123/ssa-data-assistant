# Onboarding — SSA Data Assistant

Welcome. This doc is written for a human joining the project (not an AI agent). Read it top-to-bottom; it should take ~30 minutes, and by the end you'll know what the project is, how to run it, where the moving parts live, and what the next phase of work looks like.

---

## 1. What this project is, in one paragraph

SSA Consultants need to answer questions about our project portfolio ("which engagements used tool X?", "who has capability Y?", "what deliverables are due this quarter?"). The SSA Data Assistant lets them type those questions in plain English and get a table back. Under the hood, the app takes the question, figures out which tables are relevant, sends everything to an LLM to generate SQL, validates the SQL is safe and read-only, runs it against Postgres, and returns the result. There's also an MCP server variant so Claude (Desktop or Code) can do the same thing without going through OpenAI.

Today it runs against one manually curated schema (`Project_Master_Database`). **The next phase of work — and likely your focus — is connecting real source systems to populate that schema.**

## 2. Read these, in this order

1. `README.md` — setup, endpoints, env vars
2. `CLAUDE.md` — project conventions (same content applies to humans)
3. `docs/ARCHITECTURE.md` — the diagram and the data flow
4. `docs/USING_SSA_DATA_ASSISTANT.md` — what end users see
5. `docs/ADD_NEW_DATA_WORKFLOW.md` — how config changes propagate

## 3. Get it running locally

Follow **Local Development** in `README.md`. You'll need:
- Python 3.11+
- The `.env` values (ask the project lead — `PG_DSN_READONLY`, `OPENAI_API_KEY`, `ADMIN_TOKEN`)
- VPN access to the Azure Postgres instance

Once `uvicorn` is up at `http://localhost:8000`, ask a few questions from `docs/test_questions.md` and watch the server logs to see the pipeline in action.

## 4. The five files you'll touch most

| File | Why you'll open it |
|------|--------------------|
| `app/main.py` | Every HTTP route. Start-of-request logic, startup wiring. |
| `app/ai_sql.py` | The OpenAI prompt — system message, few-shot examples, repair loop. |
| `app/catalog.py` | Schema routing — how the app picks which tables to show the LLM. |
| `app/config/*.csv` + `join_map.json` | Most "it picked the wrong table" bugs are fixed here, not in code. |
| `app/sql_validator.py` | The safety net. Read it once so you trust it, then mostly leave it alone. |

## 5. Your debugging toolkit

- `GET /debug/router?q=<question>` — see which tables the router scored highest and why. Your single most useful endpoint.
- `POST /debug/catalog/reload` — after editing anything in `app/config/`, hit this instead of restarting.
- `GET /analytics/problem-queries` — questions users asked that failed or returned empty. Gold mine for finding gaps.
- `GET /admin/verifiable-queries` (needs `ADMIN_TOKEN`) — candidates to promote to golden examples.

## 6. The big next-phase effort: data feeds

The assistant is only as good as the data behind it. Today `Project_Master_Database` is populated manually. We need to connect it to the systems where the data actually lives:

| Feed | What lives there | Status |
|------|------------------|--------|
| Salesforce | Opportunities, clients, engagement status | Not connected |
| SharePoint | Deliverables, project folders, artifacts | Not connected |
| Skills Matrix | Consultant capabilities, levels | Not connected |
| Engagement closeout | Post-engagement data, outcomes | Not connected |
| Project review forms | Mid/end-of-project assessments | Not connected |
| PMO toolkit | Staffing, utilization, pipeline | Not connected |

**Open questions you'll help answer:**
- Which of these do we have sanctioned access to *today* (creds, API permissions, data-sharing sign-off)?
- What's the right ingestion mechanism per feed — API pull, scheduled export, manual upload?
- When feeds overlap (same project, different systems), which is source of truth?
- What refresh cadence does each feed need?

**Likely architecture** (not yet built): a `raw_*` schema per source (immutable, loaded verbatim), then curated views in `Project_Master_Database` that unify them with consistent keys. The assistant only ever queries the curated layer, so ingestion changes don't break prompts.

## 7. Conventions worth knowing up front

- **No ORM.** All SQL is raw, parameterized via `psycopg`. Always schema-qualify: `"Project_Master_Database"."TableName"`.
- **Small files.** 200–400 lines typical, 800 max.
- **Immutable.** Don't mutate objects or arrays.
- **Conventional commits.** `feat:`, `fix:`, `refactor:`, `docs:`, `test:`.
- **Never commit to `main`.** Always branch, always PR.
- **No `console.log` / stray `print` in production code.** Use the logger.
- **Secrets.** `.env` is local only; prod uses Azure Key Vault. Never commit `clients_aliases.csv` or `schema_descriptions.yaml` — they're gitignored for a reason.

## 8. Who to ask

- **Project lead / product questions:** Ethan Wise (`ewise@ssaandco.com`)
- **Data access / feed owners:** TBD — you'll likely be the one to figure out who owns each of the six feeds
- **Infra / Azure:** Solutions CoE

## 9. First-week suggested path

1. Day 1 — Run it locally. Ask 20 questions. Read logs.
2. Day 2 — Read `app/main.py` end to end. Trace one request from `/ask` through to the response.
3. Day 3 — Pick one failed query from `/analytics/problem-queries`, figure out *why* it failed, propose a fix (config, not code).
4. Day 4–5 — Pick one feed from section 6 and write a one-page discovery doc: access method, auth, refresh, owner, rough volume, entities. Drop it in `docs/feeds/<feed>.md`.

Welcome aboard.
