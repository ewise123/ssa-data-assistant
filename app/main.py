from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel
from typing import List, Dict, Any

app = FastAPI(title="SSA Data Assistant")

# Serve /static/* and the root index.html
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def root_page():
    return FileResponse(static_dir / "index.html")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

# ===== NEW: models for /ask =====
class AskRequest(BaseModel):
    question: str
    dataset: str | None = None  # e.g., "clients", "consultants"

class AskResponse(BaseModel):
    sql: str
    columns: List[str]
    rows: List[Dict[str, Any]]

# ===== NEW: stub /ask endpoint =====
@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    # For now, return a tiny fake table and a pretend SQL query.
    # This proves frontend<->backend wiring before we add the model + DB.
    if (req.dataset or "").lower() == "clients":
        columns = ["client_id", "name", "industry"]
        rows = [
            {"client_id": "1111-aaaa", "name": "Acme Corp", "industry": "Insurance"},
            {"client_id": "2222-bbbb", "name": "Globex", "industry": "Finance"},
        ]
        sql = "SELECT client_id, name, industry FROM clients LIMIT 2;"
    else:
        columns = ["contact_id", "full_name", "email"]
        rows = [
            {"contact_id": "c-1001", "full_name": "Alex Rivera", "email": "alex@acme.com"},
            {"contact_id": "c-1002", "full_name": "Sam Park", "email": "sam@globex.com"},
        ]
        sql = "SELECT contact_id, full_name, email FROM client_contacts LIMIT 2;"

    return AskResponse(sql=sql, columns=columns, rows=rows)