import os
import random
import asyncio
import httpx
from fastapi import FastAPI

app = FastAPI()
INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://localhost:8002/reserve")

chaos_enabled = {"value": True}

@app.post("/charge")
async def charge(payload: dict):
    if chaos_enabled["value"] and random.random() < 0.3:
        await asyncio.sleep(random.uniform(2, 5))

    async with httpx.AsyncClient() as client:
        resp = await client.post(INVENTORY_URL, json=payload)
    return {"status": "charged", "inventory": resp.json()}

@app.post("/admin/disable-chaos")
async def disable_chaos():
    chaos_enabled["value"] = False
    return {"chaos_enabled": False}

@app.post("/admin/enable-chaos")
async def enable_chaos():
    chaos_enabled["value"] = True
    return {"chaos_enabled": True}

@app.get("/health")
async def health():
    return {"status": "ok"}