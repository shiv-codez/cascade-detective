from fastapi import FastAPI

app = FastAPI()

@app.post("/notify")
async def notify(payload: dict):
    return {"status": "notified", "received": payload}

@app.get("/health")
async def health():
    return {"status": "ok"}