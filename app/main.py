# app/main.py
import os
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# --- Load .env from the project root (folder that contains .env) ---
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# --- Local imports AFTER env vars are loaded ---
from .ai_sql import propose_sql
from .catalog import Catalog, CatalogLoadError, load_catalog, suggest_schema_snippet
from .db import describe_dsn, run_select
from .sql_validator import validate_sql

# --- App setup ---
app = FastAPI(title="SSA Data Assistant")

# Schema to introspect (default to your schema)
SCHEMA = os.getenv("PG_SEARCH_PATH", "Project_Master_Database")

# Global in-memory catalog
CATALOG: Optional[Catalog] = None
CATALOG_ERROR: Optional[str] = None

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


# --- Load catalog on startup ---
@app.on_event("startup")
def _load_catalog_on_start() -> None:
    global CATALOG, CATALOG_ERROR
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
    snippet = suggest_schema_snippet(q, CATALOG)
    return {"snippet": snippet}


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

    # 1) Generate SQL with catalog-aware hinting (or fallback hints if catalog missing)
    try:
        raw_sql = propose_sql(req.question, req.dataset, active_catalog)
        safe_sql = validate_sql(raw_sql)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not generate safe SQL: {exc}")

    # 2) Execute against Postgres (read-only)
    try:
        columns, rows = run_select(safe_sql)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Database error: {exc}")

    return AskResponse(sql=safe_sql, columns=columns, rows=rows)


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
