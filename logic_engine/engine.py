
import time, redis, os
import requests
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import defaultdict, deque
from datetime import datetime

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")  # localhost: redis крутится в Docker с проброшенным портом 6379
DJANGO_URL = os.getenv("DJANGO_URL", "http://localhost:8000")
SCADA_API_TOKEN = os.getenv("SCADA_API_TOKEN", "")
RULES_POLL_SEC = float(os.getenv("RULES_POLL_SEC", "10"))
r = redis.Redis(host=REDIS_HOST, decode_responses=True)

tag_history = defaultdict(lambda: deque(maxlen=1000))

def duration(tag_name, condition_str, history_sec=60):
    now = time.time()
    q = tag_history[tag_name]
    while q and now - q[0][0] > history_sec:
        q.popleft()
    if not q:
        return 0
    elapsed = 0
    for t, val in reversed(q):
        try:
            if not eval(f"{val} {condition_str}", {}, {}):
                break
            elapsed = now - t
        except:
            break
    return elapsed

def cmd(tag, value):
    print(f"[CMD] {tag} -> {value}", flush=True)
    r.publish(f"cmd/{tag}", str(value))
    r.hset("commands", tag, value)

def alarm(text):
    print(f"[ALARM] {text}", flush=True)
    r.lpush("alarms", f"{datetime.now().isoformat()}: {text}")

def stop(tag): cmd(tag, 0)
def start(tag): cmd(tag, 1)

# Кэш последнего успешного списка правил — работаем на нём, если Django недоступен
CACHED_RULES = []

def load_rules():
    """Опрашивает GET /api/rules/. При ошибке возвращает последний кэш, не падает."""
    global CACHED_RULES
    headers = {}
    if SCADA_API_TOKEN:
        headers["Authorization"] = f"Bearer {SCADA_API_TOKEN}"
    try:
        resp = requests.get(f"{DJANGO_URL}/api/rules/", headers=headers, timeout=5)
        if resp.status_code == 401:
            print("[RULES] 401: нет/неверный SCADA_API_TOKEN, работаю на кэше "
                  f"({len(CACHED_RULES)} правил)", flush=True)
            return CACHED_RULES
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            CACHED_RULES = data
            print(f"[RULES] загружено {len(CACHED_RULES)} правил из Django", flush=True)
        else:
            print(f"[RULES] неожиданный формат ответа: {data!r}, использую кэш ({len(CACHED_RULES)})", flush=True)
    except Exception as e:
        print(f"[RULES] Django недоступен ({e}), работаю на кэше ({len(CACHED_RULES)} правил)", flush=True)
    return CACHED_RULES

print("Logic Engine запущен...", flush=True)
load_rules()
_last_rules_poll = time.time()

while True:
    # Периодически обновляем правила из Django (5-10 сек)
    if time.time() - _last_rules_poll >= RULES_POLL_SEC:
        load_rules()
        _last_rules_poll = time.time()

    tags_raw = r.hgetall("latest_tags")
    if not tags_raw:
        time.sleep(0.2)
        continue

    try:
        tags = {k: float(v) for k,v in tags_raw.items()}
    except:
        tags = tags_raw

    now = time.time()
    for k, v in tags.items():
        try:
            tag_history[k].append((now, float(v)))
        except:
            pass

    for rule in CACHED_RULES:
        try:
            if eval(rule["condition"], {}, {"tags": tags, "duration": duration}):
                print(f"--> Сработало: {rule['name']} | tags={tags}", flush=True)
                exec(rule["action"], {}, {
                    "tags": tags, "cmd": cmd, "alarm": alarm,
                    "stop": stop, "start": start, "duration": duration
                })
        except Exception as e:
            print(f"Ошибка в правиле {rule['name']}: {e}", flush=True)

    time.sleep(0.1)
