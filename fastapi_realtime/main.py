
from fastapi import FastAPI, WebSocket
from pydantic import BaseModel
import redis, asyncio, os
from collections import defaultdict

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")  # localhost: redis крутится в Docker с проброшенным портом 6379
r = redis.Redis(host=REDIS_HOST, decode_responses=True)

app = FastAPI(title="SCADA Realtime")

latest = defaultdict(float)

class TagValue(BaseModel):
    tag: str
    value: float

@app.post("/ingest")
async def ingest(data: TagValue):
    latest[data.tag] = data.value
    r.hset("latest_tags", data.tag, data.value)
    return {"ok": True}

@app.websocket("/ws/live")
async def live(ws: WebSocket):
    await ws.accept()
    while True:
        data = r.hgetall("latest_tags") or dict(latest)
        # конвертим в float для фронта
        try:
            out = {k: float(v) for k,v in data.items()}
        except:
            out = data
        await ws.send_json(out)
        await asyncio.sleep(0.1)

@app.get("/")
async def root():
    return {"status": "FastAPI Realtime OK", "tags": r.hgetall("latest_tags")}

@app.get("/history/{tag}")
async def history(tag: str):
    return {"tag": tag, "hint": "Тут подключи TimescaleDB"}
