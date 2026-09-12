"""SCADA Realtime: ingest + WebSocket live deltas.

Протокол WS /ws/live:
- После connect клиент может прислать {"subscribe": ["tag1", "tag2", ...]}
  (имена тэгов; фронт резолвит tag_id -> name через GET /api/tags/).
  Без subscribe — шлются дельты по всем тэгам (как раньше, но только изменения).
- Сервер шлёт только дельты: {"tag": value, ...} — тэги, чьё значение
  изменилось с прошлой отправки этому клиенту. Пустые диффы не шлются.
- ingest публикует изменение в Redis pub/sub канал tag_updates и пишет HSET
  latest_tags (как раньше) — downstream для Logic Engine не меняется.
"""
import asyncio
import json
import os
from collections import defaultdict
from contextlib import suppress

import redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
POLL_INTERVAL = float(os.getenv("WS_POLL_SEC", "0.5"))
# Телеметрия открыта (как и WS без авторизации), поэтому разрешаем
# кросс-доменные запросы с любого origin — в т.ч. со страницы Django на :8000.
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

r = redis.Redis(host=REDIS_HOST, decode_responses=True)

app = FastAPI(title="SCADA Realtime")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

latest = defaultdict(float)


class TagValue(BaseModel):
    tag: str
    value: float


def _hgetall_safe():
    try:
        return r.hgetall("latest_tags") or {}
    except redis.RedisError:
        return {}


def _publish_safe(tag: str, value: float):
    with suppress(redis.RedisError):
        r.publish("tag_updates", json.dumps({"tag": tag, "value": value}))


@app.post("/ingest")
async def ingest(data: TagValue):
    latest[data.tag] = data.value
    with suppress(redis.RedisError):
        r.hset("latest_tags", data.tag, data.value)
    _publish_safe(data.tag, data.value)
    return {"ok": True}


@app.websocket("/ws/live")
async def live(ws: WebSocket):
    await ws.accept()
    subscribed = None  # None = все тэги
    last_sent: dict = {}
    # Первичная загрузка: полный снапшот один раз, дальше только дельты.
    try:
        data = _hgetall_safe() or dict(latest)
        init = {k: float(v) for k, v in data.items()}
    except (ValueError, TypeError):
        init = dict(data)
    if subscribed is not None:
        init = {k: v for k, v in init.items() if k in subscribed}
    if init:
        await ws.send_json(init)
        last_sent.update(init)
    try:
        while True:
            # Неблокирующее чтение subscribe-сообщений
            try:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=POLL_INTERVAL)
                if isinstance(msg, dict) and "subscribe" in msg:
                    sub = msg["subscribe"]
                    subscribed = set(map(str, sub)) if isinstance(sub, list) else None
                    # При смене подписки — сразу отдать текущие значения запрошенных тэгов
                    data = _hgetall_safe() or dict(latest)
                    cur = {}
                    for k, v in data.items():
                        if subscribed is not None and k not in subscribed:
                            continue
                        try:
                            cur[k] = float(v)
                        except (ValueError, TypeError):
                            cur[k] = v
                    fresh = {k: v for k, v in cur.items() if last_sent.get(k) != v}
                    if fresh:
                        await ws.send_json(fresh)
                        last_sent.update(fresh)
                    continue
            except asyncio.TimeoutError:
                pass
            data = _hgetall_safe() or dict(latest)
            cur = {}
            for k, v in data.items():
                if subscribed is not None and k not in subscribed:
                    continue
                try:
                    cur[k] = float(v)
                except (ValueError, TypeError):
                    cur[k] = v
            delta = {k: v for k, v in cur.items() if last_sent.get(k) != v}
            if delta:
                await ws.send_json(delta)
                last_sent.update(delta)
    except WebSocketDisconnect:
        pass


@app.get("/")
async def root():
    return {"status": "FastAPI Realtime OK", "tags": _hgetall_safe()}


@app.get("/alarms")
async def alarms(limit: int = 20):
    """Последние аварии Logic Engine (Redis LIST alarms, LPUSH)."""
    try:
        items = r.lrange("alarms", 0, max(0, limit - 1))
    except redis.RedisError:
        items = []
    return {"alarms": list(items)}


@app.get("/history/{tag}")
async def history(tag: str):
    return {"tag": tag, "hint": "Тут подключи TimescaleDB"}
