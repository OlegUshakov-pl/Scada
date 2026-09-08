"""Единая точка входа данных — та же, что у реальных драйверов.

Реальный путь сегодня: C3-драйвер делает HSET latest_tags <tag> <value>,
HTTP-фасад того же хэша — POST /ingest FastAPI (fastapi_realtime/main.py),
а читают его Logic Engine (HGETALL latest_tags) и WS /ws/live.

Эмулятор идёт первично через POST {FASTAPI_URL}/ingest. Если FastAPI
недоступен — fallback на прямой HSET latest_tags (тот же хэш, тот же
downstream для Logic Engine/WS). Отдельного канала «только для симуляции» нет.
"""

import logging
import os

logger = logging.getLogger(__name__)

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:9000")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        import redis

        _redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    return _redis_client


def publish(tag_name, value):
    """Опубликовать значение тэга общим путём драйверов. Возвращает путь: 'ingest'|'redis'."""
    value = float(value)
    try:
        import requests

        resp = requests.post(
            f"{FASTAPI_URL.rstrip('/')}/ingest",
            json={"tag": tag_name, "value": value},
            timeout=3,
        )
        resp.raise_for_status()
        return "ingest"
    except Exception as exc:
        logger.warning("POST /ingest недоступен (%s), fallback в Redis HSET", exc)
        _get_redis().hset("latest_tags", tag_name, value)
        return "redis"
