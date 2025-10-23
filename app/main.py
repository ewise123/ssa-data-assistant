from fastapi import FastAPI

app = FastAPI(title="SSA Data Assistant")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

# We'll implement /ask later
@app.get("/")
def root():
    return {"message": "Backend is running. Go to /docs for the API UI."}
