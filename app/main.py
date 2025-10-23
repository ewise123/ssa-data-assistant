# app/main.py
import os
from pathlib import Path

from dotenv import load_dotenv

# --- Load .env from the project root (folder that contains .env) ---
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# (optional) quick sanity log
if not os.getenv("PG_DSN_READONLY"):
    print("[WARN] PG_DSN_READONLY not found after load_dotenv")

# --- Now import everything else ---
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from .ai_sql import propose_sql
from .sql_validator import validate_sql
from .db import run_select

app = FastAPI(title="SSA Data Assistant")

# Serve the single-page app from the static directory
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")

# --- optional debug endpoint to confirm env is loaded ---
@app.get("/debug/env", include_in_schema=False)
def debug_env():
    return {
        "has_PG_DSN_READONLY": bool(os.getenv("PG_DSN_READONLY")),
        "has_OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
    }

class AskRequest(BaseModel):
    question: str
    dataset: Optional[str] = None

class AskResponse(BaseModel):
    sql: str
    columns: List[str]
    rows: List[Dict[str, Any]]

@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    try:
        raw_sql = propose_sql(req.question, req.dataset)
        safe_sql = validate_sql(raw_sql)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not generate safe SQL: {e}")

    try:
        columns, rows = run_select(safe_sql)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e}")

    return AskResponse(sql=safe_sql, columns=columns, rows=rows)
