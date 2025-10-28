# app/main.py
import os
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def _load_from_key_vault() -> Dict[str, str]:
    """
    Optionally pull secrets from Azure Key Vault.
    Enabled when AZURE_KEY_VAULT_URL is set. The comma-separated list of secret names is read from
    SSA_KEY_VAULT_SECRETS (defaults to OpenAI + Postgres entries).
    """
    vault_url = os.getenv("AZURE_KEY_VAULT_URL")
    if not vault_url:
        return {}

    try:
        from azure.identity import DefaultAzureCredential  # type: ignore
        from azure.keyvault.secrets import SecretClient  # type: ignore
    except ImportError:
        print("[secrets] azure-identity / keyvault packages missing; skipping Key Vault load")
        return {}

    secret_names = os.getenv(
        "SSA_KEY_VAULT_SECRETS",
        "OPENAI_API_KEY,PG_DSN_READONLY,PG_SEARCH_PATH",
    )
    credential = DefaultAzureCredential(exclude_visual_studio_code_credential=True)
    client = SecretClient(vault_url=vault_url, credential=credential)

    secrets: Dict[str, str] = {}
    for raw_name in secret_names.split(","):
        name = raw_name.strip()
        if not name:
            continue
        try:
            secrets[name] = client.get_secret(name).value
        except Exception as exc:  # pragma: no cover - network dependency
            print(f"[secrets] Failed to pull '{name}' from Key Vault: {exc}")
    return secrets


def load_environment() -> None:
    """
    Ensures all required secrets are available from environment variables.
    Preference order:
      1. Already-set environment variables (injected by platform).
      2. Azure Key Vault (optional).
      3. Local .env file (developer convenience only).
    """
    # Apply Key Vault secrets without overriding explicitly-set env values.
    for key, value in _load_from_key_vault().items():
        os.environ.setdefault(key, value)

    required = ("OPENAI_API_KEY", "PG_DSN_READONLY", "PG_SEARCH_PATH")
    missing = [key for key in required if not os.getenv(key)]
    env_path = ROOT / ".env"
    if missing and env_path.exists():
        load_dotenv(env_path)
        missing = [key for key in required if not os.getenv(key)]

    if missing:
        missing_list = ", ".join(missing)
        print(f"[secrets] Warning: missing expected environment variables: {missing_list}")


load_environment()

# --- Local imports AFTER env vars are loaded ---
from .ai_sql import propose_sql, propose_sql_repair
from .catalog import Catalog, CatalogLoadError, SchemaHint, load_catalog, suggest_schema_snippet
from .config_loader import (
    load_aliases,
    load_allowed_values,
    load_column_semantics,
    load_disambiguation_rules,
    load_join_map,
)
from .db import describe_dsn, run_select
from .sql_validator import validate_sql
from .query_metrics import record_query, fetch_top_queries

# --- App setup ---
app = FastAPI(title="SSA Data Assistant")

# Schema to introspect (default to your schema)
SCHEMA = os.getenv("PG_SEARCH_PATH", "Project_Master_Database")

# Global in-memory catalog and config
CATALOG: Optional[Catalog] = None
CATALOG_ERROR: Optional[str] = None
CONFIG: Dict[str, Any] = {
    "aliases": {},
    "join_map": {"paths": []},
    "semantics": {},
    "allowed": {},
    "disambiguation": {"rules": []},
}

# --- Startup diagnostics ---
_dsn_info = describe_dsn()
if _dsn_info:
    safe_parts = []
    for key in ("user", "host", "port", "dbname", "sslmode"):
        value = _dsn_info.get(key)
        if value:
            safe_parts.append(f"{key}={value}")
    print(f"[startup] PG_DSN_READONLY -> {', '.join(safe_parts)}")
else:
    print("[WARN] PG_DSN_READONLY not found after load_dotenv")

# Serve the single-page app from the static directory
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")

# --- Load catalog + config on startup ---
@app.on_event("startup")
def _load_catalog_on_start() -> None:
    global CATALOG, CATALOG_ERROR, CONFIG
    # Load catalog
    try:
        CATALOG = load_catalog(SCHEMA)
        CATALOG_ERROR = None
        print(f"[catalog] Loaded {len(CATALOG.tables)} tables, {len(CATALOG.fks)} FKs from schema {SCHEMA}")
    except CatalogLoadError as exc:
        CATALOG = None
        CATALOG_ERROR = str(exc)
        print(f"[catalog] FAILED to load: {CATALOG_ERROR}")
    except Exception as exc:
        CATALOG = None
        CATALOG_ERROR = str(exc)
        print(f"[catalog] FAILED to load: {CATALOG_ERROR}")

    # Load configuration layers
    try:
        aliases = load_aliases()
        join_map = load_join_map()
        semantics = load_column_semantics()
        allowed = load_allowed_values()
        disambig = load_disambiguation_rules()
        CONFIG = {
            "aliases": aliases,
            "join_map": join_map,
            "semantics": semantics,
            "allowed": allowed,
            "disambiguation": disambig,
        }
        print(
            "[config] Loaded aliases=%d join_paths=%d semantics=%d allowed=%d disambiguation_rules=%d"
            % (
                sum(len(v) for v in aliases.values()),
                len(join_map.get("paths", [])),
                sum(len(v) for v in semantics.values()),
                sum(len(v) for v in allowed.values()),
                len(disambig.get("rules", [])),
            )
        )
    except Exception as exc:
        print(f"[config] Failed to load extended config: {exc}")

# --- optional debug endpoint to confirm env is loaded ---
@app.get("/debug/env", include_in_schema=False)
def debug_env():
    info = describe_dsn()
    return {
        "has_PG_DSN_READONLY": bool(info),
        "has_OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
        "schema": SCHEMA,
        "catalog_loaded": bool(CATALOG),
        "catalog_error": CATALOG_ERROR,
        "config_loaded": bool(CONFIG.get("join_map", {}).get("paths")),
        "dsn": {
            key: info[key]
            for key in ("host", "port", "user", "dbname", "sslmode")
            if info and info.get(key)
        },
    }


@app.get("/debug/dns", include_in_schema=False)
def debug_dns():
    info = describe_dsn()
    if not info:
        return {"ok": False, "error": "PG_DSN_READONLY not configured"}

    host = info.get("host") or info.get("hostaddr")
    response: Dict[str, Any] = {
        "ok": False,
        "dsn_host": host,
        "dsn_port": info.get("port"),
        "dsn_user": info.get("user"),
        "dsn_db": info.get("dbname"),
    }

    if not host:
        response["error"] = "Host not present in DSN"
        return response

    try:
        resolved_ip = socket.gethostbyname(host)
        response["ok"] = True
        response["resolved_ip"] = resolved_ip
    except Exception as exc:
        response["error"] = str(exc)

    return response


# --- optional debug endpoint to see the router's schema snippet for a question ---
@app.get("/debug/router", include_in_schema=False)
def debug_router(q: str):
    if not CATALOG:
        return {"error": "catalog not loaded"}
    hint = suggest_schema_snippet(
        q,
        CATALOG,
        config=CONFIG,
        disambiguation_rules=CONFIG.get("disambiguation"),
    )
    return {
        "snippet": hint.snippet,
        "tables": hint.tables,
        "intents": hint.intents,
        "datasets": hint.disambiguation_datasets,
    }


@app.get("/debug/config", include_in_schema=False)
def debug_config():
    aliases = CONFIG.get("aliases", {})
    semantics = CONFIG.get("semantics", {})
    allowed = CONFIG.get("allowed", {})
    join_map = CONFIG.get("join_map", {})
    disambig = CONFIG.get("disambiguation", {})
    return {
        "aliases": {name: len(entries) for name, entries in aliases.items()},
        "join_paths": len(join_map.get("paths", [])),
        "semantics_tables": len(semantics),
        "allowed_columns": len(allowed),
        "disambiguation_rules": len(disambig.get("rules", [])),
    }


# --- API models ---
class AskRequest(BaseModel):
    question: str
    dataset: Optional[str] = None


class AskResponse(BaseModel):
    sql: str
    columns: List[str]
    rows: List[Dict[str, Any]]


# --- Main endpoint ---
@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    active_catalog = CATALOG
    disambiguation = CONFIG.get("disambiguation")
    schema_hint: Optional[SchemaHint] = None
    status: str = "ok"
    row_count: Optional[int] = None
    error_message: Optional[str] = None
    safe_sql: Optional[str] = None
    columns: List[str] = []
    rows: List[Dict[str, Any]] = []

    if active_catalog:
        schema_hint = suggest_schema_snippet(
            req.question,
            active_catalog,
            config=CONFIG,
            disambiguation_rules=disambiguation,
        )

    def _repair(reason: str, last_sql: str) -> Tuple[str, List[str], List[Dict[str, Any]]]:
        nonlocal schema_hint
        repaired_sql, new_hint = propose_sql_repair(
            req.question,
            last_sql,
            reason,
            req.dataset,
            active_catalog,
            CONFIG,
            schema_hint,
            disambiguation,
        )
        if new_hint:
            schema_hint = new_hint
        validated_sql = validate_sql(repaired_sql)
        cols, rows = run_select(validated_sql)
        return validated_sql, cols, rows

    try:
        try:
            # 1. Generate SQL
            raw_sql, schema_hint = propose_sql(
                req.question,
                dataset=req.dataset,
                catalog=active_catalog,
                config=CONFIG,
                schema_hint=schema_hint,
                disambiguation=disambiguation,
            )
            safe_sql = validate_sql(raw_sql)
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            raise HTTPException(status_code=400, detail=f"Could not generate safe SQL: {exc}") from exc

        try:
            # 2. Execute first attempt
            columns, rows = run_select(safe_sql)
        except Exception as exc:
            err_text = str(exc)
            print(f"[ask] execution error -> attempting repair ({err_text})")
            try:
                safe_sql, columns, rows = _repair(err_text, safe_sql)
                print("[ask] repair succeeded after execution error")
            except Exception as repair_exc:
                status = "error"
                error_message = f"{err_text}; repair failed: {repair_exc}"
                raise HTTPException(
                    status_code=400,
                    detail=f"Database error: {err_text}; repair failed: {repair_exc}",
                ) from repair_exc

        # 3. If the query ran but returned no rows, try one guided repair
        if active_catalog and schema_hint and len(rows) == 0:
            print(f"[ask] no rows returned; attempting repair via intent '{schema_hint.primary_intent}'")
            try:
                candidate_sql, new_cols, new_rows = _repair("no rows returned", safe_sql)
                if new_rows:
                    print("[ask] repair produced rows; returning repaired result")
                    safe_sql = candidate_sql
                    columns = new_cols
                    rows = new_rows
                else:
                    print("[ask] repair still returned zero rows; returning original result")
                    status = "empty"
            except Exception as repair_exc:
                print(f"[ask] repair attempt failed: {repair_exc}")
                status = "empty"

        row_count = len(rows)
        return AskResponse(sql=safe_sql, columns=columns, rows=rows)
    except HTTPException:
        raise
    except Exception as exc:
        status = "error"
        if error_message is None:
            error_message = str(exc)
        raise
    finally:
        effective_row_count = row_count if row_count is not None else len(rows)
        final_status = status
        if final_status == "ok" and effective_row_count == 0:
            final_status = "empty"
        record_query(
            question=req.question,
            dataset=req.dataset,
            status=final_status,
            row_count=effective_row_count,
            error_message=error_message,
        )


@app.get("/debug/db", include_in_schema=False)
def debug_db():
    try:
        cols, rows = run_select('SELECT current_database() AS db, current_schema() AS sch')
        return {"ok": True, "rows": rows}
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "dsn_set": bool(os.getenv("PG_DSN_READONLY")),
        }


@app.get("/analytics/common-queries")
def analytics_common_queries(limit: int = 10):
    limit = max(1, min(limit, 50))
    rows = fetch_top_queries(limit=limit)
    return {"items": rows}
