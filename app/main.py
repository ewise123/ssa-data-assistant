# app/main.py
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from .ai_sql import propose_sql
from .sql_validator import validate_sql

load_dotenv()  # load OPENAI_API_KEY, OPENAI_MODEL

app = FastAPI(title="SSA Data Assistant")

# Serve static
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def root_page():
    return FileResponse(static_dir / "index.html")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

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
        # 1) Ask the model for a SELECT query
        raw_sql = propose_sql(req.question, req.dataset)
        # 2) Validate & enforce safety
        safe_sql = validate_sql(raw_sql)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not generate safe SQL: {e}")

    # For now we do NOT execute SQL; we’ll hook Postgres in Step 7.
    # Return empty rows with the proposed SQL so you can see it in the UI.
    return AskResponse(sql=safe_sql, columns=[], rows=[])
