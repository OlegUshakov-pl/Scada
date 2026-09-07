
import time, redis, os
from collections import defaultdict, deque
from datetime import datetime

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")  # localhost: redis крутится в Docker с проброшенным портом 6379
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

RULES = [
    {
        "name": "Защита насоса по давлению",
        "condition": "tags.get('pressure', 99) < 2.0 and duration('pressure', '< 2.0') > 5",
        "action": "stop('pump_01'); alarm('Насос СТОП - давление <2 бар уже 5 сек')",
    },
    {
        "name": "Перегрев",
        "condition": "tags.get('temp_01', 0) > 90",
        "action": "alarm(f"Перегрев! temp_01={tags['temp_01']}")",
    },
]

print("Logic Engine запущен...", flush=True)

while True:
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

    for rule in RULES:
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
