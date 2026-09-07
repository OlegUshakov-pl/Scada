# My SCADA — Django + FastAPI + C3 + Logic Engine

Конфигурируемый SCADA-конструктор: устройства, тэги, правила и дашборды задаются
через Django-админку **без правки кода сервисов**. Python 3.14.

```
                    ┌──────────────┐
                    │     ПЛК      │  Modbus TCP
                    │ (датчики,    │
                    │  насос)      │
                    └──────┬───────┘
                           │ чтение регистров
                    ┌──────▼───────┐  HSET latest_tags     ┌──────────────┐
                    │  C3-драйвер  │ ────────────────────► │    Redis     │
                    │ modbus_1.c3  │                       │ latest_tags, │
                    └──────────────┘                       │ commands,    │
                              ▲                            │ alarms,      │
                              │ карта регистров            │ cmd/*        │
                              │ device_<id>.txt            └──┬───┬───┬──┘
                    ┌─────────┴────┐                        │   │   │  │
                    │    Django    │  GET /api/rules/       │   │   │  │
                    │  админка,    │ ◄──────────────────────┘   │   │  │
                    │  API,        │  GET /api/devices/<id>/    │   │  │
                    │  дашборд     │  tags, /api/screens/...    │   │  │
                    └──────────────┘                           │   │  │
                              ▲                                │   │  │
                              │ login + Bearer-токены          │   │  │
                    ┌─────────┴────┐  ┌──────────────┐          │   │  │
                    │   Браузер    │  │ Logic Engine │ ◄────────┘   │  │
                    │  дашборд     │  │ eval правил, │  HGET        │  │
                    │  (grid+WS)   │  │ cmd/alarm    │  latest_tags │  │
                    └──────────────┘  └──────────────┘              │  │
                              ▲                                    │  │
                              │ ws://.../ws/live                   │  │
                    ┌─────────┴────┐                               │  │
                    │   FastAPI    │ ◄─────────────────────────────┘  │
                    │  realtime    │  HGET latest_tags                 │
                    └──────────────┘                                  │
                                           publish cmd/*, HSET commands, LPUSH alarms
```

Поток данных: **C3-драйвер → Redis (`latest_tags`) → Logic Engine + FastAPI → команды/алерты**.
Источник конфигурации для всех — **Django + БД**.

## Структура репозитория

```
composer.yml                 # compose: инфраструктура (redis, postgres) + сервисы
task-scada-config-driven.md  # исходное ТЗ (конфигурируемость вместо хардкода)
README_old.md                # старый краткий README (история)
django_scada/                # конфиг, админка, REST API, дашборд, management-команды
  scada/
    models.py                # Device, Tag, Rule, Screen, Widget, ServiceToken
    views.py                 # /api/* + страница дашборда
    urls.py                  # маршруты приложения
    auth.py                  # Bearer-токены + декоратор api_auth_required
    admin.py                 # админка (+inline виджетов/тэгов, revoke токенов)
    templates/scada/dashboard.html  # дашборд: CSS-grid + WebSocket
    management/commands/
      export_device_config.py   # карта регистров для C3-драйвера
      create_service_token.py   # выпуск сервисных токенов
    migrations/              # 0001_initial, 0002_seed (демо-данные), 0003_servicetoken
  config/                    # settings.py, urls.py
fastapi_realtime/main.py     # POST /ingest, WS /ws/live, GET /, GET /history/{tag}
logic_engine/engine.py       # цикл опроса Redis + eval правил из Django API
c3_driver/
  modbus_1.c3                # config-driven драйвер Modbus → Redis (основной)
  modbus.c3 / modbus_http.c3 # заглушки/примеры
  device_1.txt.example       # пример конфига карты регистров
modbus.c3                    # пример/набросок на C3 (корень, история)
```

## Стек и версии

- Python 3.14 (`python:3.14-slim` в Dockerfile)
- Django ≥ 5.2 (первая с официальной поддержкой Python 3.14), БД по умолчанию — SQLite (`db.sqlite3`), TimescaleDB/PostgreSQL 17 — в compose для будущего
- FastAPI + uvicorn, `redis-py`, `requests` (logic_engine)
- C3 (`c3c`), libmodbus, hiredis — для драйвера
- Зависимостей для авторизации не добавлялось — только встроенный `django.contrib.auth`

## Быстрый старт

### 1. Инфраструктура (Redis, PostgreSQL)

```bash
podman compose -f composer.yml up -d redis postgres
# или: docker compose -f composer.yml up -d redis postgres
```

Порты наружу: Redis `6379`, PostgreSQL `5432`. Внутри сети compose сервисы доступны
по именам `redis` / `postgres`.

### 2. Python-сервисы — обычные процессы в venv (без Docker)

```bash
# Django
cd django_scada
python -m venv .venv && .venv/Scripts/activate  # Windows; на Linux: source .venv/bin/activate
python -m pip install -r requirements.txt       # django, redis
python manage.py migrate                        # применит и seed-миграцию 0002_seed
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000

# FastAPI (второй терминал)
cd fastapi_realtime
python -m pip install -r requirements.txt       # fastapi, uvicorn, redis, pydantic
uvicorn main:app --host 0.0.0.0 --port 9000 --reload

# Logic Engine (третий терминал)
cd logic_engine
python -m pip install -r requirements.txt       # redis, requests
SCADA_API_TOKEN=<токен> DJANGO_URL=http://localhost:8000 REDIS_HOST=localhost python engine.py
```

> `docker-compose` для Python-сервисов не используется — только для инфраструктуры
> (см. `task-scada-config-driven.md`). В `composer.yml` секции сервисов оставлены
> для совместимости, `logic_engine` там уже параметризован через
> `DJANGO_URL` / `SCADA_API_TOKEN`.

### 3. Проверка

- Django-админка: http://localhost:8000/admin/
- Дашборд «Главный» (seed): http://localhost:8000/screens/1/ (потребует логин)
- FastAPI: http://localhost:9000/ , WS: ws://localhost:9000/ws/live
- Симуляция датчика без ПЛК:

```bash
redis-cli HSET latest_tags pressure 1.5 temp_01 95 pump_fb 1
```

Через ~5 сек в логах `logic_engine` сработает «Защита насоса», в Redis появятся
`commands`/`alarms`.

## Django: модели и админка

| Модель | Назначение | Ключевые поля |
|---|---|---|
| `Device` | устройство (ПЛК) | `name`, `ip`, `protocol` (modbus/opcua/s7) |
| `Tag` | тэг устройства | `device`, `name`, `address` (регистр), `unit` |
| `Rule` | правило Logic Engine | `name`, `condition` (Python), `action` (Python), `is_active` |
| `Screen` | экран дашборда | `name`, `layout` (legacy JSON, не используется, оставлен как есть) |
| `Widget` | виджет на экране | `screen`, `tag`, `widget_type` (number/chart/indicator), `row`, `col`, `label` |
| `ServiceToken` | сервисный токен для `/api/*` | `user` (владелец), `name`, `key_hash` (sha256), `is_active` |

Админка: `Tag` — inline на странице `Device`, `Widget` — inline (`TabularInline`)
на странице `Screen`. Раскладка виджетов задаётся числами `row`/`col` — drag-n-drop
сознательно не делался (достаточно для MVP).

Seed-демо (`migrations/0002_seed.py`, идемпотентно через `get_or_create`): устройство
«Насосная 1» (192.168.1.10, modbus), тэги `pressure/0/bar`, `temp_01/1/C`, `pump_fb/2`,
2 активных правила, экран «Главный» с 3 виджетами. Откат — `migrate scada 0001`.

Management-команды:

```bash
# карта регистров устройства для C3-драйвера (формат: name,address построчно)
python manage.py export_device_config <device_id> [--out /config/device_<id>.txt]

# выпуск сервисного токена (сырой токен печатается ОДИН раз!)
python manage.py create_service_token --user <username> --name logic_engine
```

## REST API (Django, без DRF — голый `JsonResponse`)

Все `/api/*` требуют авторизацию: сессия залогиненного пользователя **или**
заголовок `Authorization: Bearer <токен>`. Без авторизации — `401 {"detail": ...}`.

| Метод | URL | Ответ |
|---|---|---|
| `GET` | `/api/rules/` | активные правила: `[{"name","condition","action"}, ...]` |
| `GET` | `/api/devices/<id>/tags/` | карта регистров: `[{"name","address","unit"}, ...]` по возрастанию адреса |
| `GET` | `/api/screens/<id>/widgets/` | виджеты: `[{"id","tag","unit","widget_type","row","col","label"}, ...]` |
| `GET` | `/screens/<id>/` | HTML-дашборд (требует логин, редирект на `/admin/login/`) |

Примеры:

```bash
T=<токен>
curl -H "Authorization: Bearer $T" http://localhost:8000/api/rules/
curl -H "Authorization: Bearer $T" http://localhost:8000/api/devices/1/tags/
curl -H "Authorization: Bearer $T" http://localhost:8000/api/screens/1/widgets/
```

## Авторизация

Схема — минимум зависимостей, но с заделом на будущие права пользователей:

- Токен **привязан к `User`** (`ServiceToken.user`). Когда появятся права, проверки
  сведутся к `request.api_user.has_perm("scada.view_rule")` → 403, а права раздаются
  штатными `Group`/`Permission` в админке. Сервисы автоматически наследуют права
  владельца токена — рефакторинг не понадобится.
- В БД хранится только **sha256-хэш** токена; сырое значение показывается один раз
  при создании. Утечка БД ≠ утечка доступа.
- Отзыв: флаг `is_active` (админка → `ServiceToken` → action «Revoke») или удаление записи.
  Токены неактивных пользователей не работают.
- Дашборд под `login_required`, его JS ходит к widgets-API по сессионной куке —
  токен в браузерный код не попадает.

```bash
python manage.py createsuperuser
python manage.py create_service_token --user <username> --name logic_engine
# -> SCADA_API_TOKEN=<сохранить в секретное хранилище, повтороно не показать>
```

## Logic Engine

`logic_engine/engine.py`: цикл 10 Гц читает `latest_tags` из Redis, выполняет
`eval(condition)` / `exec(action)` над текущим набором правил, пишет команды и алерты
обратно в Redis. Доступны хелперы: `cmd/tag/value`, `start/stop`, `alarm`, `duration`.

Правила **не зашиты в коде**: `load_rules()` опрашивает `GET /api/rules/` каждые
`RULES_POLL_SEC` (по умолчанию 10 с) и кэширует результат. Поведение при проблемах:

- Django недоступен → предупреждение в лог, работа на последнем кэше, не падает;
- `401` (нет/неверный `SCADA_API_TOKEN`) → предупреждение в лог, работа на кэше.

Переменные окружения:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `REDIS_HOST` | `localhost` | хост Redis |
| `DJANGO_URL` | `http://localhost:8000` | базовый URL Django API |
| `SCADA_API_TOKEN` | `""` (без токена) | Bearer-токен сервиса |
| `RULES_POLL_SEC` | `10` | период опроса `/api/rules/` |

Пример правила из seed:

```python
# condition:
tags.get('pressure', 99) < 2.0 and duration('pressure', '< 2.0') > 5
# action:
stop('pump_01'); alarm('Насос СТОП - давление <2 бар уже 5 сек')
```

## C3-драйвер (Modbus → Redis)

`c3_driver/modbus_1.c3` — config-driven: карта регистров **не зашита**, при старте
читается файл `CONFIG_PATH` (по умолчанию `/config/device_1.txt`):

```
# формат: name,address построчно (комментарии с #)
pressure,0
temp_01,1
pump_fb,2
```

Файл генерируется из Django (админка — источник правды):

```bash
python manage.py export_device_config 1 --out /config/device_1.txt
```

Как это работает: драйвер bulk-читает `max(address)+1` регистров с адреса 0 и публикует
**по одному `HSET latest_tags <name> <value>` на тэг** — эквивалентно одному большому
`HSET`, но работает с любым числом тэгов из конфига. Если конфиг отсутствует —
fallback на встроенную карту (`pressure/0`, `temp_01/1`, `pump_fb/2`) с предупреждением
в лог. Команды обратно (`HGET commands pump_01` → `modbus_write_register`) —
заготовка в коде, закомментирована.

Важно:

- Публикуется **сырое значение регистра** как float. Старого деления `/10.0` нет
  осознанно (generic-драйвер). Если датчикам нужен масштаб — следующий шаг: колонка
  `scale` в `Tag` + третья колонка в конфиге.
- Сборка: `c3c compile modbus_1.c3 -lmodbus -lhiredis -o driver` (нужны `c3c`,
  `libmodbus-dev`, `hiredis`). `modbus.c3` / `modbus_http.c3` — заглушки и примеры.

## Дашборд

`GET /screens/<id>/` — чистый HTML+JS без фреймворков (`scada/templates/scada/dashboard.html`):

- раскладка — CSS-grid по `row`/`col` виджетов (обновляется каждые 30 с из API);
- live-данные — WebSocket `ws://<host>:9000/ws/live` (тот же, что отдаёт FastAPI);
- типы: `number`/`chart` — текущее значение + единица; `indicator` — ● ВКЛ/ВЫКЛ.

Требует логина. Для доступа FastAPI WS из браузера ничего дополнительно настраивать
не нужно (WS без авторизации — данные телеметрии).

## Redis-схема (не менять — все сервисы на неё опираются)

| Ключ | Тип | Кто пишет | Кто читает | Пример |
|---|---|---|---|---|
| `latest_tags` | HASH field→value | C3-драйвер, `POST /ingest` | Logic Engine, FastAPI | `HSET latest_tags pressure 1.5` |
| `commands` | HASH tag→value | Logic Engine | C3-драйвер (заготовка) | `HGET commands pump_01` |
| `cmd/<tag>` | PUB/SUB | Logic Engine | подписчики команд | `cmd/pump_01 = 0` |
| `alarms` | LIST (LPUSH) | Logic Engine | операторы/мониторинг | `LRANGE alarms 0 10` |

FastAPI: `POST /ingest {"tag": ..., "value": ...}` пишет в `latest_tags`;
`GET /history/{tag}` — заглушка под TimescaleDB.

## Типичные проблемы

- **401 от `/api/*`** — нет заголовка `Authorization: Bearer` или токен отозван /
  пользователь неактивен. Выпусти новый через `create_service_token`.
- **Logic Engine пишет «Django недоступен»** — проверь `DJANGO_URL` и что
  `runserver` поднят; движок при этом продолжает работать на кэше правил.
- **Кракозябры/`UnicodeEncodeError` в Windows-консоли** — движок уже делает
  `sys.stdout.reconfigure(encoding="utf-8")`; выводы management-команд deliberately
  на английском. При желании: `$env:PYTHONUTF8="1"`.
- **Дашборд редиректит на `/admin/login/`** — так и должно: сначала залогинься.
- **C3-драйвер не видит конфиг** — проверь `CONFIG_PATH` и что файл экспортирован;
  без него работает fallback-карта из 3 тэгов.

## Что дальше

- Права пользователей: `has_perm`-проверки в `api_auth_required` + группы в админке
  (токены уже привязаны к `User` — см. «Авторизация»)
- TimescaleDB: история тэгов (`GET /history/{tag}`) и доделать `chart`-виджеты
- `scale` в `Tag` + третья колонка конфига C3-драйвера
- Запись команд C3-драйвером обратно в ПЛК (`HGET commands` → `modbus_write_register`)
- Тесты Django (`TestCase` на API/авторизацию) и CI
