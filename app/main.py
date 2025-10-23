from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

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
