# SSA Data Assistant

FastAPI-powered, AI-assisted SQL exploration for the **Project_Master_Database** schema. The SSA Data Assistant lets business and analytics users ask natural-language questions that are translated into safe, read-only SQL and executed against a PostgreSQL instance.

## Table of Contents
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [Environment Variables & Secrets](#environment-variables--secrets)
- [Running the App](#running-the-app)
- [Refreshing Catalog / Config](#refreshing-catalog--config)
- [User Documentation](#user-documentation)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

---

## Architecture

| Layer              | Technology / Notes                                                                 |
|--------------------|-------------------------------------------------------------------------------------|
| Backend API        | FastAPI (`/ask`, `/debug/*`)                                                        |
| SQL generation     | OpenAI Chat Completions (server-side only)                                         |
| Database           | Azure PostgreSQL (read-only DSN, schema `Project_Master_Database`)                 |
| ORM/DB access      | `psycopg` (raw queries, read-only)                                                  |
| Frontend           | Static HTML + Tailwind styles + Anime.js micro-animations                           |
| Configuration      | CSV/JSON files under `app/config/` for aliases, join map, column semantics, etc.   |

---

## Prerequisites

- Python 3.11+
- Node/npm **not required** (frontend is static)
- Access to Azure PostgreSQL read-only DSN
- OpenAI API key (with access to the configured model)

---

## Local Development

1. **Clone & create virtual environment**
   ```bash
   git clone <repo-url>
   cd ssa-data-assistant
   python -m venv .venv
   .\.venv\Scripts\activate  # Windows
   # source .venv/bin/activate  # macOS/Linux
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create `.env` (local only)**  
   ```
   OPENAI_API_KEY=sk-...
   PG_DSN_READONLY=postgresql://user:pass@host:port/postgres?sslmode=require
   PG_SEARCH_PATH=Project_Master_Database
   ```

4. **Run server**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

5. **Open UI**  
   Visit `http://localhost:8000/` to test the assistant.

---

## Environment Variables & Secrets

| Variable            | Description                                              |
|---------------------|----------------------------------------------------------|
| `OPENAI_API_KEY`    | Server-side key used to call the OpenAI API              |
| `PG_DSN_READONLY`   | PostgreSQL read-only DSN (Azure PG)                      |
| `PG_SEARCH_PATH`    | Schema to introspect (default `Project_Master_Database`) |
| `AZURE_KEY_VAULT_URL` / `SSA_KEY_VAULT_SECRETS` | _(Optional)_ for Azure deployments leveraging Key Vault |

> The app prefers environment-injected secrets. `.env` is only a developer convenience. For production, store secrets in Azure App Settings or Azure Key Vault. Secrets are never exposed to the browser.

---

## Running the App

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Useful endpoints (all require authentication in production):

| Endpoint                 | Purpose                                  |
|--------------------------|------------------------------------------|
| `GET /`                  | Serves the SPA-like static UI            |
| `POST /ask`              | Core NL → SQL → results pipeline         |
| `GET /debug/env`         | Inspect environment/load status          |
| `GET /debug/db`          | Sanity check DB connectivity             |
| `POST /debug/catalog/reload` | (Optional) Trigger catalog/config reload |

---

## Refreshing Catalog / Config

When new tables/columns are added:
1. Apply DB migrations (ensure naming conventions and foreign keys).
2. Update relevant config files under `app/config/` if needed.
3. Reload catalog via `/debug/catalog/reload` or CLI helper.
4. Validate with sample `/ask` queries.

See **[docs/ADD_NEW_DATA_WORKFLOW.md](docs/ADD_NEW_DATA_WORKFLOW.md)** for step-by-step instructions.

---

## User Documentation

- **How to use the assistant**: [docs/USING_SSA_DATA_ASSISTANT.md](docs/USING_SSA_DATA_ASSISTANT.md)
- Covers launching, dataset selection, example questions, and limitations.

---

## Security Considerations

- Secrets (OpenAI key, DB DSN) are loaded server-side only. The frontend never contains or transmits them.
- The database user configured by `PG_DSN_READONLY` must be read-only.
- `.env` is ignored by Git; ensure deployment platforms inject secrets via environment variables / Key Vault.
- Consider adding reverse-proxy rules to block access to hidden files (`.env`, `.git`, etc.).
- All SQL generated is validated to ensure it is a single `SELECT` statement before execution.

---

## Troubleshooting

| Issue                                | Suggested Action                                                  |
|--------------------------------------|-------------------------------------------------------------------|
| `OPENAI_API_KEY not configured`      | Ensure the env var is set (or `.env` exists locally).             |
| Database connection errors           | Check VPN, firewall, and that `PG_DSN_READONLY` is correct.       |
| Catalog not loading / stale schema   | Re-run catalog reload endpoint/CLI and confirm config updates.    |
| UI loads but queries fail            | Inspect browser console & server logs; verify `/ask` response.    |

---

## Contributing
1. Fork & create feature branch.
2. Add tests or docs for new behavior.
3. Update config docs if schema/config files change.
4. Submit PR with summary + screenshots/logs if relevant.

For questions, reach out to the Analytics Engineering team or open an internal ticket.
