import os
import httpx
from fastapi import FastAPI

app = FastAPI()
PAYMENT_URL = os.environ.get("PAYMENT_URL", "http://localhost:8001/charge")

@app.post("/order")
async def place_order(payload: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(PAYMENT_URL, json=payload)
    return {"status": "order placed", "payment": resp.json()}

@app.get("/health")
async def health():
    return {"status": "ok"}