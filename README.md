# SCADA — Django + FastAPI + C3 + Logic Engine + Emulator

Configurable SCADA constructor: devices, tags, rules, and dashboards are defined
through the Django admin **without editing service code**. Python 3.14.

```
                    ┌──────────────┐
                    │     PLC      │  Modbus TCP
                    │ (sensors,   │
                    │  pump)       │
                    └──────┬───────┘
                           │ register read
                    ┌──────▼───────┐  HSET latest_tags     ┌──────────────┐
                    │  C3 driver   │ ────────────────────► │    Redis     │
                    │ modbus_1.c3  │                       │ latest_tags, │
                    └──────────────┘                       │ commands,    │
                              ▲                            │ alarms,      │
                              │ register map               │ cmd/*        │
                              │ device_<id>.txt            └──┬───┬───┬──┘
                    ┌─────────┴────┐                        │   │   │  │
                    │    Django    │  GET /api/rules/       │   │   │  │
                    │  admin,      │ ◄──────────────────────┘   │   │  │
                    │  API,        │  GET /api/devices/<id>/    │   │  │
                    │  dashboard,  │  tags, /api/screens/...    │   │  │
                    │  emulator    │  POST /ingest (FastAPI) ───┘   │  │
                    └──────────────┘  ▲                            │  │
                              ▲       │ publish via sender         │  │
                              │ login + Bearer tokens              │  │
                    ┌─────────┴────┐  ┌──────────────┐             │  │
                    │   Browser    │  │ Logic Engine │ ◄───────────┘  │
                    │  dashboard   │  │ eval rules,  │  HGET           │
                    │  (grid+WS)   │  │ cmd/alarm    │  latest_tags    │
                    └──────────────┘  └──────────────┘                │
                              ▲                                       │
                              │ ws://.../ws/live                      │
                    ┌─────────┴────┐                                  │
                    │   FastAPI    │ ◄────────────────────────────────┘
                    │  realtime    │  HGET latest_tags
                    └──────────────┘
                                           publish cmd/*, HSET commands, LPUSH alarms
```

Data flow: **C3 driver / emulator → Redis (`latest_tags`) → Logic Engine + FastAPI → commands/alerts**.
The configuration source for all services is **Django + DB**. The emulator follows the same path
as real drivers (shared `POST /ingest` → `latest_tags`); there is no separate
"simulation-only" channel.

## Repository Structure

```
composer.yml                 # compose: infrastructure (redis, postgres) + services
emulator_task.md             # emulator spec for virtual devices
README_old.md                # old short README (history)
django_scada/                # config, admin, REST API, dashboard, emulator, management commands
  scada/
    models.py                # Device, Tag, Rule, Screen, Widget, ServiceToken
    views.py                 # /api/* + dashboard page
    urls.py                  # app routes
    auth.py                  # Bearer tokens + api_auth_required decorator
    admin.py                 # admin (+ widget/tag inlines, token revoke)
    templates/scada/dashboard.html  # dashboard: CSS-grid + WebSocket
    management/commands/
      export_device_config.py   # register map for C3 driver
      create_service_token.py   # issue service tokens
    migrations/              # 0001_initial, 0002_seed (demo data), 0003_servicetoken
  emulator/
    models.py                # SimulatorDevice (FK Device + FK Tag, modes, intervals)
    generators.py            # stateless generators constant/random/sine/ramp/cycle
    sender.py                # publish(): POST /ingest with fallback to HSET latest_tags
    admin.py                 # simulator admin
    tests.py                 # generator unit tests (6)
    management/commands/
      seed_simulators.py     # starter set: 10 simulators (idempotent)
      run_simulators.py      # scheduler: one thread per simulator
    migrations/              # 0001_initial
  config/                    # settings.py, urls.py
fastapi_realtime/main.py     # POST /ingest, WS /ws/live, GET /, GET /history/{tag}
logic_engine/engine.py       # Redis polling loop + rule eval from Django API
c3_driver/
  modbus_1.c3                # config-driven Modbus → Redis driver (main)
  modbus.c3 / modbus_http.c3 # stubs / examples
  device_1.txt.example       # example register map config
modbus.c3                    # example/draft in C3 (root, history)
```

## Stack and Versions

- Python 3.14 (`python:3.14-slim` in Dockerfiles)
- Django 6.1.1 (Python 3.12–3.14, `python:3.14-slim` in Dockerfile), default DB — SQLite (`db.sqlite3`), TimescaleDB/PostgreSQL 17 — in compose for future use
- FastAPI + uvicorn, `redis-py`, `requests` (logic_engine, emulator.sender)
- C3 (`c3c`), libmodbus, hiredis — for the driver
- No extra auth dependencies — only built-in `django.contrib.auth`

## Quick Start

### 1. Infrastructure (Redis, PostgreSQL)

```bash
podman compose -f composer.yml up -d redis postgres
# or: docker compose -f composer.yml up -d redis postgres
```

Exposed ports: Redis `6379`, PostgreSQL `5432`. Inside the compose network services
are reachable via `redis` / `postgres` hostnames.

### 2. Python Services — Regular Processes in venv (Without Docker)

```bash
# Django
cd django_scada
python -m venv .venv && .venv/Scripts/activate  # Windows; on Linux: source .venv/bin/activate
python -m pip install -r requirements.txt       # django, redis, requests
python manage.py migrate                        # applies seed migration 0002_seed + emulator.0001
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000

# FastAPI (second terminal)
cd fastapi_realtime
python -m pip install -r requirements.txt       # fastapi, uvicorn, redis, pydantic
uvicorn main:app --host 0.0.0.0 --port 9000 --reload

# Logic Engine (third terminal)
cd logic_engine
python -m pip install -r requirements.txt       # redis, requests
SCADA_API_TOKEN=<token> DJANGO_URL=http://localhost:8000 REDIS_HOST=localhost python engine.py
```

> `docker-compose` is not used for Python services — only for infrastructure.
> Service sections in `composer.yml` are kept for compatibility, `logic_engine`
> is already parameterized via `DJANGO_URL` / `SCADA_API_TOKEN`.

### 3. Emulator Instead of PLC (Fourth Terminal)

```bash
cd django_scada
python manage.py seed_simulators   # once: device "Simulator" + 10 sim_* tags + 10 simulators
FASTAPI_URL=http://localhost:9000 REDIS_HOST=localhost python manage.py run_simulators [--reload 10]
```

Each simulator ticks at its own `update_interval` in a separate thread and publishes
via the shared `POST /ingest`. The `enabled` flag in admin is picked up without restart
(re-read every `--reload` seconds). See "Emulator" section below for details.

### 4. Verification

- Django admin: http://localhost:8000/admin/
- "Main" dashboard (seed): http://localhost:8000/screens/1/ (login required)
- FastAPI: http://localhost:9000/ , WS: ws://localhost:9000/ws/live
- Without emulator, manually publish a sensor reading without a PLC:

```bash
redis-cli HSET latest_tags pressure 1.5 temp_01 95 pump_fb 1
```

After ~5 seconds the `logic_engine` logs will trigger "Pump protection", and Redis
will contain `commands`/`alarms`.
- With emulator: `redis-cli HGETALL latest_tags` will show `sim_*` keys alongside
real tags.

## Django: Models and Admin

| Model | Purpose | Key Fields |
|---|---|---|
| `Device` | device (PLC) | `name`, `ip`, `protocol` (modbus/opcua/s7) |
| `Tag` | device tag | `device`, `name`, `address` (register), `unit` |
| `Rule` | Logic Engine rule | `name`, `condition` (Python), `action` (Python), `is_active` |
| `Screen` | screen: dashboard + constructor | `name`, `width`, `height`, `widgets` (JSON), `created_at`, `updated_at`; `layout` — legacy, kept as is |
| `Widget` | legacy widget table (dashboard row/col) | `screen` (related `legacy_widgets`), `tag`, `widget_type`, `row`, `col`, `label` |
| `ServiceToken` | service token for `/api/*` | `user` (owner), `name`, `key_hash` (sha256), `is_active` |
| `SimulatorDevice` | virtual generator (app `emulator`) | `device` (FK), `tag` (FK), `signal_type`, `mode`, `min/max_value`, `period`, `update_interval`, `enabled` |

Admin: `Tag` is inline on the `Device` page, legacy `Widget` is inline
(`TabularInline`) on the `Screen` page. `SimulatorDevice` has a dedicated page under
"Emulator" (filters by `signal_type`/`mode`/`enabled`, quick enable/disable via `list_editable`).
Legacy dashboard layout is set via `row`/`col` numbers. The new constructor
(`Screen.widgets` JSON) is drag-and-drop — see "Screen Constructor" section.

Seed demo (`scada/migrations/0002_seed.py`, idempotent via `get_or_create`):
device "Pump Station 1" (192.168.1.10, modbus), tags `pressure/0/bar`,
`temp_01/1/C`, `pump_fb/2`, 2 active rules, screen "Main" with 3 widgets.
Rollback — `migrate scada 0001`.

Management commands:

```bash
# register map for C3 driver (format: name,address per line)
python manage.py export_device_config <device_id> [--out /config/device_<id>.txt]

# issue a service token (raw token is printed ONCE!)
python manage.py create_service_token --user <username> --name logic_engine

# emulator starter pack (idempotent, no duplicates)
python manage.py seed_simulators

# run emulator: one thread per active SimulatorDevice
FASTAPI_URL=http://localhost:9000 REDIS_HOST=localhost python manage.py run_simulators [--reload 10]
```

## REST API (Django, Without DRF — Plain `JsonResponse`)

All `/api/*` endpoints require auth: a logged-in user session **or**
`Authorization: Bearer <token>` header. Without auth — `401 {"detail": ...}`.

| Method | URL | Response |
|---|---|---|
| `GET` | `/api/rules/` | active rules: `[{"name","condition","action"}, ...]` |
| `GET` | `/api/alarms/` (`?limit=`) | proxy to FastAPI — latest alarms (same origin, no CORS); if FastAPI is down — `{"alarms": []}` |
| `GET` | `/api/devices/` | devices for the constructor properties panel |
| `GET` | `/api/tags/` (`?device_id=`) | tags for properties panel: `[{"id","device_id","device","name","address","unit"}]` |
| `GET` | `/api/devices/<id>/tags/` | register map: `[{"name","address","unit"}, ...]` sorted by address |
| `GET` | `/api/screens/` | list of screens (constructor) |
| `POST` | `/api/screens/` | create screen — **staff only**, otherwise `403` |
| `GET` | `/api/screens/<id>/` | full screen with `widgets` |
| `PATCH` | `/api/screens/<id>/` | save — **staff only**; on edit conflict — `409` (see below) |
| `GET` | `/api/screens/<id>/widgets/` | legacy row/col widgets for the old dashboard |
| `GET` | `/screens/<id>/` | HTML dashboard (login required, redirect to `/admin/login/`) |
| `GET` | `/screens/<id>/edit/` | mimic editor (**staff only**, otherwise `403`) |

Permissions: viewing — any authenticated user (or Bearer token of an active
user); screen writes — only `is_staff` (service tokens inherit owner permissions).
Concurrent editing conflict: Save sends `updated_at` from the last load; if someone
else has already saved the screen — `409 {"detail": "Conflict...", "current": {...}}`,
the editor offers to overwrite or load the other version. No locking.

Examples:

```bash
T=<token>
curl -H "Authorization: Bearer $T" http://localhost:8000/api/rules/
curl -H "Authorization: Bearer $T" http://localhost:8000/api/devices/1/tags/
curl -H "Authorization: Bearer $T" http://localhost:8000/api/screens/
curl -H "Authorization: Bearer $T" http://localhost:8000/api/screens/1/
curl -X PATCH -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d '{"name":"Boiler Room #1","widgets":[...]}' http://localhost:8000/api/screens/1/
```

## Authentication

Minimal dependencies with room for future user permissions:

- Token is **bound to a `User`** (`ServiceToken.user`). When permissions arrive,
  checks come down to `request.api_user.has_perm("scada.view_rule")` → 403, and
  permissions are assigned via standard `Group`/`Permission` in admin. Services
  automatically inherit token owner permissions — no refactoring needed.
- Only the **sha256 hash** is stored in the DB; the raw value is shown once
  at creation. A DB leak ≠ access leak.
- Revocation: `is_active` flag (admin → `ServiceToken` → "Revoke" action) or deleting the record.
  Tokens of inactive users do not work.
- Dashboard is behind `login_required`; its JS calls the widgets API via session cookie —
  no token is exposed to browser code.

```bash
python manage.py createsuperuser
python manage.py create_service_token --user <username> --name logic_engine
# -> SCADA_API_TOKEN=<store in secrets manager, will not be shown again>
```

## Emulator (Django App `emulator`)

Generates test readings for multiple devices simultaneously without mixing
with real `Device` records: `SimulatorDevice` is a separate table with `FK(Device)`,
no simulation fields on `Device`, no value written to DB. Publishing is only via
`emulator/sender.py::publish()`: primary `POST {FASTAPI_URL}/ingest`
(`fastapi_realtime/main.py:18-22`), on FastAPI failure — fallback to direct
`HSET latest_tags` (same hash, same downstream for Logic Engine and WS `/ws/live`).

Clarification to the spec: `FK(Device)` alone is not enough for routing because the key
in `latest_tags` is the **tag** name, and one `Device` has multiple tags. Therefore
the model has an additional `tag = FK(Tag)` field, and `clean()` verifies
that the tag belongs to the selected device.

### Generators (`emulator/generators.py`)

All formulas are stateless — only `time.time() % period`, restart-safe:

- `constant` — always `min_value`;
- `random` — `random.uniform(min_value, max_value)` on each tick;
- `sine` — sine wave between `min`/`max` with period `period`;
- `ramp` — linear growth `min → max` over `period`, then reset (`(now % period)/period`);
- `cycle` — alternating `[min, max]` (for `digital_input` typically `0/1`),
  switching every `period/2` (with `period=4` and a 2 s tick — `0/1/0/1...`).

### Scheduler (`run_simulators`)

One daemon thread per active `SimulatorDevice` — 10 devices with different
`update_interval` values do not block each other (no celery/beat, stdlib only).
The main loop every `--reload` seconds (default 10) reconciles the `enabled=True`
list with running threads: starts new ones, stops disabled/removed ones.
Worker logs publishing/generation errors and continues; the process does not crash.

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `FASTAPI_URL` | `http://localhost:9000` | where to `POST /ingest` |
| `REDIS_HOST` / `REDIS_PORT` | `localhost` / `6379` | fallback `HSET latest_tags` + local debugging |

### Starter Pack (`seed_simulators`)

Idempotent (`update_or_create` by `tag`): device "Simulator" (127.0.0.1, modbus) + 10 `sim_*` tags (addresses 0–9) + 10 simulators as per spec:

| # | tag | signal_type | mode | min | max | period | interval |
|---|---|---|---|---|---|---|---|
| 1 | `sim_temp_1` | temperature | sine | 18 | 26 | 300 | 2 |
| 2 | `sim_temp_2` | temperature | random | 15 | 30 | — | 5 |
| 3 | `sim_press_1` | pressure | ramp | 0 | 10 | 60 | 1 |
| 4 | `sim_press_2` | pressure | sine | 2 | 8 | 120 | 2 |
| 5 | `sim_di_1` | digital_input | cycle | 0 | 1 | 4 | 2 |
| 6 | `sim_di_2` | digital_input | constant | 1 | 1 | — | 10 |
| 7 | `sim_motor_1` | motor | ramp | 0 | 1500 | 30 | 1 |
| 8 | `sim_motor_2` | motor | random | 0 | 1500 | — | 3 |
| 9 | `sim_temp_3` | temperature | constant | 22 | 22 | — | 10 |
| 10 | `sim_press_3` | pressure | random | 0 | 12 | — | 5 |

Custom simulators — via admin ("Emulator" section): pick `device` + `tag`,
type, mode, range, intervals. Tests: `python manage.py test emulator` (6 generator
tests, no DB/Redis required).

## Logic Engine

`logic_engine/engine.py`: 10 Hz loop reads `latest_tags` from Redis, executes
`eval(condition)` / `exec(action)` over the current rule set, writes commands and alerts
back to Redis. Available helpers: `cmd/tag/value`, `start/stop`, `alarm`, `duration`.

Rules are **not hard-coded**: `load_rules()` polls `GET /api/rules/` every
`RULES_POLL_SEC` (default 10 s) and caches the result. Behavior on failure:

- Django unavailable → warning in log, run on last cache, do not crash;
- `401` (missing/invalid `SCADA_API_TOKEN`) → warning in log, run on cache.

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `REDIS_HOST` | `localhost` | Redis host |
| `DJANGO_URL` | `http://localhost:8000` | Django API base URL |
| `SCADA_API_TOKEN` | `""` (no token) | service Bearer token |
| `RULES_POLL_SEC` | `10` | `/api/rules/` poll interval |

Seed rule example:

```python
# condition:
tags.get('pressure', 99) < 2.0 and duration('pressure', '< 2.0') > 5
# action:
stop('pump_01'); alarm('Pump STOP - pressure <2 bar for 5 sec')
```

Rules see `sim_*` emulator tags the same way — to test, write a condition like
`tags.get('sim_press_1', 99) > 9`.

## C3 Driver (Modbus → Redis)

`c3_driver/modbus_1.c3` — config-driven: the register map is **not hard-coded**, at startup
it reads `CONFIG_PATH` (default `/config/device_1.txt`):

```
# format: name,address per line (comments with #)
pressure,0
temp_01,1
pump_fb,2
```

File is generated from Django (admin is the single source of truth):

```bash
python manage.py export_device_config 1 --out /config/device_1.txt
```

How it works: the driver bulk-reads `max(address)+1` registers starting at address 0 and publishes
**one `HSET latest_tags <name> <value>` per tag** — equivalent to one large `HSET` but works
with any number of tags from the config. If the config is missing — fallback to the built-in
map (`pressure/0`, `temp_01/1`, `pump_fb/2`) with a warning in the log. Reverse commands
(`HGET commands pump_01` → `modbus_write_register`) — stub in code, commented out.

Notes:

- Publishes the **raw register value** as float. The old `/10.0` division is intentionally
  gone (generic driver). If sensors need scaling — next step: `scale` column on `Tag` + third
  column in the config.
- Build: `c3c compile modbus_1.c3 -lmodbus -lhiredis -o driver` (requires `c3c`,
  `libmodbus-dev`, `hiredis`). `modbus.c3` / `modbus_http.c3` are stubs/examples.

## Screen Constructor (`/screens/<id>/edit/`, staff only)

Option A from the spec (Django template `scada/templates/scada/constructor.html`,
no Vite/CORS — page and API on the same domain via session). There are no React
sources (prototype `Scada-Constructor-Prototype.html` is a bundled build), so the
editor is written in vanilla JS with the same functionality.

Widget format in `Screen.widgets` (JSON):
`{id, type, x, y, w, h, color, label, rotation, tag_id, device_id,
warn_above, alarm_above}`. Binding is `{tag_id, device_id}` to real
`Tag`/`Device` (may be `null` — pipe/label without a tag), picked in the
properties panel from `GET /api/tags/`.

Features: palette → drag-and-drop onto canvas (types `pump, valve, tank,
motor, pipe-h/v, label, indicator, number, lamp, fan`; new type = one entry
in the `TYPES` dictionary), mouse drag, Shift+click — multi-select with group
drag/delete, undo/redo (up to 50 steps, Ctrl+Z/Ctrl+Y),
conditional formatting (`warn_above`/`alarm_above` — amber/red border;
pumps/motors — green/red for on/off), dropdown navigation between screens,
alarm banner in Preview (`GET /api/alarms` — Django proxy to FastAPI so the
browser does not hit CORS; FastAPI also has CORS open directly:
`ALLOWED_ORIGINS`, default `*`), Save — `PATCH /api/screens/<id>/`
with conflict protection (409), live JSON model at the bottom.

## Dashboard

`GET /screens/<id>/` — plain HTML+JS with no frameworks (`scada/templates/scada/dashboard.html`),
renders both formats: constructor widgets (`Screen.widgets`, absolute `x/y`
on a `width×height` canvas, live values and threshold colors via WS) and below —
legacy grid by `row`/`col` (refreshed every 30 s from API). The
"→ open in constructor" link goes to `/screens/<id>/edit/`:

- layout — CSS-grid by `row`/`col` widgets (refreshed every 30 s from API);
- live data — WebSocket `ws://<host>:9000/ws/live`: one full snapshot on connect,
  then only deltas `{tag: value}` for changed values; client may send
  `{"subscribe": ["tag1", ...]}` (tag names) — then deltas only for those.
  Server polls every `WS_POLL_SEC` (0.5 s). Constructor resolves `tag_id → name`
  via `GET /api/tags/`. The old dashboard understands deltas (ignores missing keys);
- types: `number`/`chart` — current value + unit; `indicator` — ● ON/OFF.

Login required. No extra setup is needed for FastAPI WS access from the browser
(WS is unauthenticated — telemetry data). `sim_*` tags are shown on the dashboard
as regular widgets (widget bound to `Tag`).

## Redis Schema (Do Not Change — All Services Depend on It)

| Key | Type | Written By | Read By | Example |
|---|---|---|---|---|
| `latest_tags` | HASH field→value | C3 driver, `POST /ingest` (incl. emulator) | Logic Engine, FastAPI | `HSET latest_tags pressure 1.5` |
| `commands` | HASH tag→value | Logic Engine | C3 driver (stub) | `HGET commands pump_01` |
| `cmd/<tag>` | PUB/SUB | Logic Engine | command subscribers | `cmd/pump_01 = 0` |
| `alarms` | LIST (LPUSH) | Logic Engine | operators/monitoring | `LRANGE alarms 0 10` |

FastAPI: `POST /ingest {"tag": ..., "value": ...}` writes to `latest_tags`
and publishes to pub/sub channel `tag_updates`;
`GET /alarms?limit=20` — latest alarms (Redis LIST `alarms`, written by Logic Engine);
`GET /history/{tag}` — stub for TimescaleDB.

## Troubleshooting

- **401 from `/api/*`** — missing `Authorization: Bearer` header or token revoked /
  user inactive. Issue a new one via `create_service_token`.
- **403 from `/api/screens/` or `/screens/<id>/edit/`** — screen writes are
  `is_staff` only (set "staff status" in admin); viewing is available to all
  authenticated users. Service tokens need a staff owner.
- **409 on Save in constructor** — someone else saved the screen concurrently;
  the editor will offer to overwrite or load the other version.
- **Logic Engine logs "Django unavailable"** — check `DJANGO_URL` and that
  `runserver` is up; the engine keeps running on cached rules.
- **Emulator logs "POST /ingest unavailable, fallback to Redis"** — FastAPI
  is down or `FASTAPI_URL` is wrong; data still goes to the same `latest_tags`
  directly and Logic Engine will see it. If Redis errors follow — check that Redis
  is up (`compose up -d redis`).
- **Garbled output / `UnicodeEncodeError` in Windows console** — the engine already does
  `sys.stdout.reconfigure(encoding="utf-8")`; management command output is deliberately
  in English. Optionally: `$env:PYTHONUTF8="1"`.
- **Dashboard redirects to `/admin/login/`** — expected: log in first.
- **C3 driver does not see config** — check `CONFIG_PATH` and that the file was exported;
  without it the fallback map of 3 tags is used.

## Roadmap

- User permissions: granular `has_perm` checks in `api_auth_required` +
  groups in admin (foundation exists: screen writes already require `is_staff`,
  tokens are bound to `User` — see "Authentication")
- Constructor: drag-resize via corner handles and rotation handle on canvas
  (currently — numbers in properties panel), palette drag on touch screens
- TimescaleDB: tag history (`GET /history/{tag}`) and `chart` widgets
- `scale` on `Tag` + third config column for the C3 driver
- C3 driver writing commands back to PLC (`HGET commands` → `modbus_write_register`)
- Django API/auth tests (`TestCase`) and CI (emulator generator tests already exist: `test emulator`)
