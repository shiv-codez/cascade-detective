import os
import httpx
from fastapi import FastAPI

app = FastAPI()
NOTIFICATION_URL = os.environ.get("NOTIFICATION_URL", "http://localhost:8003/notify")

@app.post("/reserve")
async def reserve(payload: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(NOTIFICATION_URL, json=payload)
    return {"status": "reserved", "notification": resp.json()}

@app.get("/health")
async def health():
    return {"status": "ok"}