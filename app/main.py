# app/main.py
import os
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from html import escape

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
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
from .sql_validator import validate_sql, build_sqlglot_schema
from .query_metrics import (
    record_query, fetch_top_queries, fetch_problem_queries,
    fetch_verifiable_queries, verify_query, fetch_verified_queries,
)
from .rag import SchemaRetriever, GoldenQueryStore, DocumentationStore, index_config_as_documentation

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
SCHEMA_RETRIEVER: Optional[SchemaRetriever] = None
SQLGLOT_SCHEMA: Optional[Dict[str, Dict[str, Dict[str, str]]]] = None
GOLDEN_STORE: Optional[GoldenQueryStore] = None
DOC_STORE: Optional[DocumentationStore] = None

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

# --- Load catalog + config helpers ---
def _load_catalog_and_config() -> Dict[str, Any]:
    global CATALOG, CATALOG_ERROR, CONFIG, SCHEMA_RETRIEVER, SQLGLOT_SCHEMA, GOLDEN_STORE, DOC_STORE
    result: Dict[str, Any] = {"catalog": {}, "config": {}}

    try:
        CATALOG = load_catalog(SCHEMA)
        CATALOG_ERROR = None
        catalog_tables = len(CATALOG.tables)
        catalog_fks = len(CATALOG.fks)
        SQLGLOT_SCHEMA = build_sqlglot_schema(CATALOG)
        print(f"[catalog] Loaded {catalog_tables} tables, {catalog_fks} FKs from schema {SCHEMA}")
        result["catalog"] = {
            "schema": SCHEMA,
            "tables": catalog_tables,
            "foreign_keys": catalog_fks,
            "error": None,
        }
    except CatalogLoadError as exc:
        CATALOG = None
        CATALOG_ERROR = str(exc)
        print(f"[catalog] FAILED to load: {CATALOG_ERROR}")
        result["catalog"] = {"schema": SCHEMA, "tables": 0, "foreign_keys": 0, "error": CATALOG_ERROR}
        return result
    except Exception as exc:
        CATALOG = None
        CATALOG_ERROR = str(exc)
        print(f"[catalog] FAILED to load: {CATALOG_ERROR}")
        result["catalog"] = {"schema": SCHEMA, "tables": 0, "foreign_keys": 0, "error": CATALOG_ERROR}
        return result

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
        result["config"] = {"aliases": 0, "join_paths": 0, "semantics_tables": 0, "allowed_columns": 0, "disambiguation_rules": 0, "error": str(exc)}
    else:
        result["config"] = {
            "aliases": sum(len(v) for v in aliases.values()),
            "join_paths": len(join_map.get("paths", [])),
            "semantics_tables": sum(len(v) for v in semantics.values()),
            "allowed_columns": sum(len(v) for v in allowed.values()),
            "disambiguation_rules": len(disambig.get("rules", [])),
            "error": None,
        }

    # Initialize embedding-based schema retriever (if schema descriptions exist)
    try:
        retriever = SchemaRetriever()
        if retriever.count == 0:
            from pathlib import Path as _P
            desc_path = _P("app/config/schema_descriptions.yaml")
            if desc_path.exists():
                n = retriever.index_from_yaml(desc_path)
                print(f"[rag] Indexed {n} schema documents into ChromaDB")
            else:
                print("[rag] No schema_descriptions.yaml found; schema RAG disabled")
        else:
            print(f"[rag] Schema retriever loaded ({retriever.count} documents)")
        SCHEMA_RETRIEVER = retriever
    except Exception as exc:
        print(f"[rag] Failed to initialize schema retriever: {exc}")
        SCHEMA_RETRIEVER = None

    # Initialize golden query store
    try:
        GOLDEN_STORE = GoldenQueryStore()
        # Sync any verified queries from SQLite into ChromaDB
        verified = fetch_verified_queries()
        synced = 0
        for vq in verified:
            if vq["generated_sql"]:
                GOLDEN_STORE.add(vq["question"], vq["generated_sql"])
                synced += 1
        if synced:
            print(f"[rag] Synced {synced} verified golden queries to ChromaDB")
        print(f"[rag] Golden query store loaded ({GOLDEN_STORE.count} examples)")
    except Exception as exc:
        print(f"[rag] Failed to initialize golden query store: {exc}")
        GOLDEN_STORE = None

    # Initialize documentation store from config files
    try:
        doc_store = DocumentationStore()
        if doc_store.count == 0:
            n = index_config_as_documentation(doc_store, CONFIG)
            print(f"[rag] Indexed {n} documentation chunks into ChromaDB")
        else:
            print(f"[rag] Documentation store loaded ({doc_store.count} chunks)")
        DOC_STORE = doc_store
    except Exception as exc:
        print(f"[rag] Failed to initialize documentation store: {exc}")
        DOC_STORE = None

    return result


@app.on_event("startup")
def _load_catalog_on_start() -> None:
    _load_catalog_and_config()

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


@app.post("/debug/catalog/reload", include_in_schema=False)
def debug_catalog_reload(request: Request):
    expected_token = os.getenv("CATALOG_RELOAD_TOKEN")
    if expected_token:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        token = auth_header.split(" ", 1)[1].strip()
        if token != expected_token:
            raise HTTPException(status_code=403, detail="Invalid token")

    result = _load_catalog_and_config()
    ok = not result["catalog"].get("error") and not result["config"].get("error")
    return {
        "ok": bool(ok),
        "catalog": result["catalog"],
        "config": result["config"],
    }


# --- optional debug endpoint to see the router's schema snippet for a question ---
@app.get("/debug/router", include_in_schema=False)
def debug_router(q: str):
    if not CATALOG:
        return {"error": "catalog not loaded"}

    vector_scores: Optional[Dict[str, float]] = None
    if SCHEMA_RETRIEVER and SCHEMA_RETRIEVER.count > 0:
        try:
            rag_result = SCHEMA_RETRIEVER.retrieve_tables(q)
            vector_scores = {t.name: t.vector_score for t in rag_result.tables}
        except Exception:
            pass

    hint = suggest_schema_snippet(
        q,
        CATALOG,
        config=CONFIG,
        disambiguation_rules=CONFIG.get("disambiguation"),
        vector_scores=vector_scores,
    )
    return {
        "snippet": hint.snippet,
        "tables": hint.tables,
        "intents": hint.intents,
        "datasets": hint.disambiguation_datasets,
        "vector_scores": vector_scores,
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


class AskMetadata(BaseModel):
    question: str
    dataset: Optional[str]
    status: str
    row_count: int
    error: Optional[str] = None
    timestamp: datetime


class AskResponse(BaseModel):
    sql: str
    columns: List[str]
    rows: List[Dict[str, Any]]
    metadata: AskMetadata


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
    final_status_for_log: Optional[str] = None

    if active_catalog:
        # Get vector similarity scores from RAG if available
        vector_scores: Optional[Dict[str, float]] = None
        if SCHEMA_RETRIEVER and SCHEMA_RETRIEVER.count > 0:
            try:
                rag_result = SCHEMA_RETRIEVER.retrieve_tables(req.question)
                vector_scores = {t.name: t.vector_score for t in rag_result.tables}
            except Exception as rag_exc:
                print(f"[rag] Schema retrieval failed, falling back to keywords: {rag_exc}")

        schema_hint = suggest_schema_snippet(
            req.question,
            active_catalog,
            config=CONFIG,
            disambiguation_rules=disambiguation,
            vector_scores=vector_scores,
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

    # Retrieve relevant documentation context
    doc_context: Optional[List[str]] = None
    if DOC_STORE and DOC_STORE.count > 0:
        try:
            doc_hits = DOC_STORE.retrieve(req.question, k=3)
            if doc_hits:
                doc_context = [d.text for d in doc_hits]
        except Exception as doc_exc:
            print(f"[rag] Documentation retrieval failed: {doc_exc}")

    # Retrieve golden examples for dynamic few-shot
    golden_examples: Optional[List[Dict[str, Any]]] = None
    if GOLDEN_STORE and GOLDEN_STORE.count > 0:
        try:
            golden_hits = GOLDEN_STORE.retrieve(req.question, k=3)
            if golden_hits:
                golden_examples = [
                    {"user": g.question, "assistant": g.sql}
                    for g in golden_hits
                ]
                print(f"[rag] Retrieved {len(golden_examples)} golden examples (best similarity: {golden_hits[0].similarity:.3f})")
        except Exception as golden_exc:
            print(f"[rag] Golden query retrieval failed: {golden_exc}")

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
                golden_examples=golden_examples,
                doc_context=doc_context,
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
        response_status = status
        if response_status == "ok" and row_count == 0:
            response_status = "empty"
        final_status_for_log = response_status
        metadata = AskMetadata(
            question=req.question,
            dataset=req.dataset,
            status=response_status,
            row_count=row_count,
            error=error_message if response_status == "error" else None,
            timestamp=datetime.now(timezone.utc),
        )
        return AskResponse(sql=safe_sql, columns=columns, rows=rows, metadata=metadata)
    except HTTPException:
        raise
    except Exception as exc:
        status = "error"
        if error_message is None:
            error_message = str(exc)
        raise
    finally:
        effective_row_count = row_count if row_count is not None else len(rows)
        final_status = final_status_for_log or status
        if final_status == "ok" and effective_row_count == 0:
            final_status = "empty"
        record_query(
            question=req.question,
            dataset=req.dataset,
            status=final_status,
            row_count=effective_row_count,
            error_message=error_message,
            generated_sql=safe_sql,
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


@app.get("/projects")
def list_projects():
    projects_sql = f'''
        SELECT DISTINCT
            ce.project_name,
            cl.client_firm_name,
            cl.industry
        FROM "{SCHEMA}"."ClientEngagement" AS ce
        JOIN "{SCHEMA}"."ClientList" AS cl
          ON ce.client_id = cl.client_id
        WHERE ce.project_name IS NOT NULL AND ce.project_name <> ''
        ORDER BY ce.project_name ASC, cl.client_firm_name ASC
    '''
    try:
        _, rows = run_select(projects_sql)
    except Exception as exc:
        print(f"[projects] failed to load projects: {exc}")
        raise HTTPException(status_code=500, detail="Could not load projects.") from exc
    return {"items": rows}


@app.get("/analytics/common-queries")
def analytics_common_queries(limit: int = 10):
    limit = max(1, min(limit, 50))
    rows = fetch_top_queries(limit=limit)
    return {"items": rows}


@app.get("/analytics/problem-queries")
def analytics_problem_queries(limit: int = 20):
    limit = max(1, min(limit, 50))
    rows = fetch_problem_queries(limit=limit)
    return {"items": rows}


@app.get("/admin/problem-queries", include_in_schema=False)
def admin_problem_queries(limit: int = 50):
    limit = max(1, min(limit, 200))
    rows = fetch_problem_queries(limit=limit)
    table_rows = "\n".join(
        f"<tr>"
        f"<td>{escape(row['question'])}</td>"
        f"<td>{escape(row['status'])}</td>"
        f"<td class='numeric'>{row['count']}</td>"
        f"<td>{escape(row['last_asked'])}</td>"
        f"<td>{escape(row['last_error'] or '')}</td>"
        f"</tr>"
        for row in rows
    ) or "<tr><td colspan='5'>No problematic queries logged yet.</td></tr>"

    html_doc = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8"/>
      <title>Problem Queries · SSA Data Assistant</title>
      <style>
        :root {{
          font-family: Arial, sans-serif;
          background: #f5f7fb;
          color: #1f2937;
        }}
        body {{
          margin: 0;
          padding: 2rem;
        }}
        h1 {{
          margin-bottom: 1rem;
        }}
        table {{
          width: 100%;
          border-collapse: collapse;
          box-shadow: 0 8px 16px rgba(15, 23, 42, 0.08);
        }}
        th, td {{
          padding: 0.75rem 1rem;
          border-bottom: 1px solid #d1d5db;
          vertical-align: top;
        }}
        th {{
          text-align: left;
          background: #111827;
          color: #f9fafb;
        }}
        tr:nth-child(even) td {{
          background: #f9fafb;
        }}
        td.numeric {{
          text-align: right;
          font-variant-numeric: tabular-nums;
        }}
        .meta {{
          margin-bottom: 1rem;
          color: #4b5563;
        }}
        code {{
          background: rgba(55, 65, 81, 0.12);
          padding: 0.1rem 0.35rem;
          border-radius: 0.35rem;
          font-size: 0.9rem;
        }}
      </style>
    </head>
    <body>
      <h1>Problem Queries</h1>
      <p class="meta">Showing up to <code>{limit}</code> queries with status <code>empty</code> or <code>error</code>.</p>
      <table>
        <thead>
          <tr>
            <th>Question</th>
            <th>Status</th>
            <th>Count</th>
            <th>Last Asked</th>
            <th>Last Error</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>
    </body>
    </html>
    """
    return HTMLResponse(content=html_doc)


# --- Golden query admin endpoints ---

class VerifyRequest(BaseModel):
    query_id: int
    verified: bool = True


@app.get("/admin/golden-queries", include_in_schema=False)
def admin_golden_queries():
    """List all verified golden queries."""
    return fetch_verified_queries()


@app.get("/admin/verifiable-queries", include_in_schema=False)
def admin_verifiable_queries(limit: int = 50):
    """List recent successful queries available for verification."""
    return fetch_verifiable_queries(limit=max(1, min(limit, 200)))


@app.post("/admin/verify-query", include_in_schema=False)
def admin_verify_query(req: VerifyRequest):
    """Mark a query as verified (golden) or unverified."""
    found = verify_query(req.query_id, req.verified)
    if not found:
        raise HTTPException(status_code=404, detail=f"Query ID {req.query_id} not found")

    # Sync to golden query ChromaDB store
    if req.verified and GOLDEN_STORE:
        verified_queries = fetch_verified_queries()
        for vq in verified_queries:
            if vq["id"] == req.query_id and vq["generated_sql"]:
                GOLDEN_STORE.add(vq["question"], vq["generated_sql"])
                break

    return {"ok": True, "query_id": req.query_id, "verified": req.verified}
