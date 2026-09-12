# My SCADA — Django + FastAPI + C3 + Logic Engine + Emulator

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
                    │  дашборд,    │  tags, /api/screens/...    │   │  │
                    │  эмулятор    │  POST /ingest (FastAPI) ───┘   │  │
                    └──────────────┘  ▲                            │  │
                              ▲       │ publish via sender         │  │
                              │ login + Bearer-токены              │  │
                    ┌─────────┴────┐  ┌──────────────┐             │  │
                    │   Браузер    │  │ Logic Engine │ ◄───────────┘  │
                    │  дашборд     │  │ eval правил, │  HGET           │
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

Поток данных: **C3-драйвер / эмулятор → Redis (`latest_tags`) → Logic Engine + FastAPI → команды/алерты**.
Источник конфигурации для всех — **Django + БД**. Эмулятор идёт тем же путём,
что и реальные драйверы (общий `POST /ingest` → `latest_tags`), отдельного канала
«только для симуляции» нет.

## Структура репозитория

```
composer.yml                 # compose: инфраструктура (redis, postgres) + сервисы
emulator_task.md             # ТЗ на эмулятор виртуальных устройств
README_old.md                # старый краткий README (история)
django_scada/                # конфиг, админка, REST API, дашборд, эмулятор, management-команды
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
  emulator/
    models.py                # SimulatorDevice (FK Device + FK Tag, режимы, интервалы)
    generators.py            # stateless-генераторы constant/random/sine/ramp/cycle
    sender.py                # publish(): POST /ingest с fallback на HSET latest_tags
    admin.py                 # админка симуляторов
    tests.py                 # юнит-тесты генераторов (6 шт.)
    management/commands/
      seed_simulators.py     # стартовый набор: 10 симуляторов (идемпотентно)
      run_simulators.py      # планировщик: по потоку на симулятор
    migrations/              # 0001_initial
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
- Django 6.1.1 (Python 3.12–3.14, `python:3.14-slim` в Dockerfile), БД по умолчанию — SQLite (`db.sqlite3`), TimescaleDB/PostgreSQL 17 — в compose для будущего
- FastAPI + uvicorn, `redis-py`, `requests` (logic_engine, emulator.sender)
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
python -m pip install -r requirements.txt       # django, redis, requests
python manage.py migrate                        # применит seed-миграцию 0002_seed + emulator.0001
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

> `docker-compose` для Python-сервисов не используется — только для инфраструктуры.
> В `composer.yml` секции сервисов оставлены для совместимости, `logic_engine`
> там уже параметризован через `DJANGO_URL` / `SCADA_API_TOKEN`.

### 3. Эмулятор вместо ПЛК (четвёртый терминал)

```bash
cd django_scada
python manage.py seed_simulators   # 1 раз: устройство «Симуляторная» + 10 тэгов sim_* + 10 симуляторов
FASTAPI_URL=http://localhost:9000 REDIS_HOST=localhost python manage.py run_simulators [--reload 10]
```

Каждый симулятор тикает по своему `update_interval` в отдельном потоке и публикует
через общий `POST /ingest`. Флаг `enabled` в админке подхватывается без рестарта
(перечитывается каждые `--reload` сек). Подробнее — раздел «Эмулятор» ниже.

### 4. Проверка

- Django-админка: http://localhost:8000/admin/
- Дашборд «Главный» (seed): http://localhost:8000/screens/1/ (потребует логин)
- FastAPI: http://localhost:9000/ , WS: ws://localhost:9000/ws/live
- Без эмулятора, вручную один датчик без ПЛК:

```bash
redis-cli HSET latest_tags pressure 1.5 temp_01 95 pump_fb 1
```

Через ~5 сек в логах `logic_engine` сработает «Защита насоса», в Redis появятся
`commands`/`alarms`.
- С эмулятором: `redis-cli HGETALL latest_tags` покажет ключи `sim_*` рядом
с реальными тэгами.

## Django: модели и админка

| Модель | Назначение | Ключевые поля |
|---|---|---|
| `Device` | устройство (ПЛК) | `name`, `ip`, `protocol` (modbus/opcua/s7) |
| `Tag` | тэг устройства | `device`, `name`, `address` (регистр), `unit` |
| `Rule` | правило Logic Engine | `name`, `condition` (Python), `action` (Python), `is_active` |
| `Screen` | экран: дашборд + конструктор | `name`, `width`, `height`, `widgets` (JSON), `created_at`, `updated_at`; `layout` — legacy, оставлен как есть |
| `Widget` | legacy-таблица виджетов (дашборд row/col) | `screen` (related `legacy_widgets`), `tag`, `widget_type`, `row`, `col`, `label` |
| `ServiceToken` | сервисный токен для `/api/*` | `user` (владелец), `name`, `key_hash` (sha256), `is_active` |
| `SimulatorDevice` | виртуальный генератор (приложение `emulator`) | `device` (FK), `tag` (FK), `signal_type`, `mode`, `min/max_value`, `period`, `update_interval`, `enabled` |

Админка: `Tag` — inline на странице `Device`, legacy-`Widget` — inline
(`TabularInline`) на странице `Screen`. `SimulatorDevice` — отдельная страница в разделе «Эмулятор»
(фильтры по `signal_type`/`mode`/`enabled`, быстрое вкл/выкл через `list_editable`).
Раскладка legacy-дашборда задаётся числами `row`/`col`. Новый конструктор
(`Screen.widgets` JSON) перетаскивается мышью — см. раздел «Конструктор экранов».

Seed-демо (`scada/migrations/0002_seed.py`, идемпотентно через `get_or_create`):
устройство «Насосная 1» (192.168.1.10, modbus), тэги `pressure/0/bar`,
`temp_01/1/C`, `pump_fb/2`, 2 активных правила, экран «Главный» с 3 виджетами.
Откат — `migrate scada 0001`.

Management-команды:

```bash
# карта регистров устройства для C3-драйвера (формат: name,address построчно)
python manage.py export_device_config <device_id> [--out /config/device_<id>.txt]

# выпуск сервисного токена (сырой токен печатается ОДИН раз!)
python manage.py create_service_token --user <username> --name logic_engine

# стартовый набор эмулятора (идемпотентно, дубликатов не создаёт)
python manage.py seed_simulators

# запуск эмулятора: по потоку на каждый активный SimulatorDevice
FASTAPI_URL=http://localhost:9000 REDIS_HOST=localhost python manage.py run_simulators [--reload 10]
```

## REST API (Django, без DRF — голый `JsonResponse`)

Все `/api/*` требуют авторизацию: сессия залогиненного пользователя **или**
заголовок `Authorization: Bearer <токен>`. Без авторизации — `401 {"detail": ...}`.

| Метод | URL | Ответ |
|---|---|---|
| `GET` | `/api/rules/` | активные правила: `[{"name","condition","action"}, ...]` |
| `GET` | `/api/alarms/` (`?limit=`) | прокси к FastAPI — последние аварии (same origin, без CORS); FastAPI недоступен — `{"alarms": []}` |
| `GET` | `/api/devices/` | устройства для панели свойств конструктора |
| `GET` | `/api/tags/` (`?device_id=`) | тэги для панели свойств: `[{"id","device_id","device","name","address","unit"}]` |
| `GET` | `/api/devices/<id>/tags/` | карта регистров: `[{"name","address","unit"}, ...]` по возрастанию адреса |
| `GET` | `/api/screens/` | список экранов (конструктор) |
| `POST` | `/api/screens/` | создание экрана — **только staff**, иначе `403` |
| `GET` | `/api/screens/<id>/` | экран целиком с `widgets` |
| `PATCH` | `/api/screens/<id>/` | сохранение — **только staff**; при конфликте правок — `409` (см. ниже) |
| `GET` | `/api/screens/<id>/widgets/` | legacy-виджеты row/col для старого дашборда |
| `GET` | `/screens/<id>/` | HTML-дашборд (требует логин, редирект на `/admin/login/`) |
| `GET` | `/screens/<id>/edit/` | конструктор мнемосхем (**только staff**, иначе `403`) |

Права: просмотр — любой залогиненный (или Bearer-токен активного
пользователя); запись экранов — только `is_staff` (сервисные токены наследуют
права владельца). Конфликт одновременного редактирования: Save шлёт
`updated_at` с прошлой загрузки; если экран уже сохранил кто-то другой —
`409 {"detail": "Conflict...", "current": {...}}`, редактор предлагает
перезаписать или загрузить чужую версию. Блокировок нет.

Примеры:

```bash
T=<токен>
curl -H "Authorization: Bearer $T" http://localhost:8000/api/rules/
curl -H "Authorization: Bearer $T" http://localhost:8000/api/devices/1/tags/
curl -H "Authorization: Bearer $T" http://localhost:8000/api/screens/
curl -H "Authorization: Bearer $T" http://localhost:8000/api/screens/1/
curl -X PATCH -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d '{"name":"Котельная №1","widgets":[...]}' http://localhost:8000/api/screens/1/
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

## Эмулятор (Django-приложение `emulator`)

Генерирует тестовые показания для нескольких устройств одновременно, не смешиваясь
с реальными `Device`: `SimulatorDevice` — отдельная таблица со ссылкой `FK(Device)`,
в `Device` полей симуляции нет, в БД значение не пишется. Публикация — только через
`emulator/sender.py::publish()`: первично `POST {FASTAPI_URL}/ingest`
(`fastapi_realtime/main.py:18-22`), при недоступности FastAPI — fallback на прямой
`HSET latest_tags` (тот же хэш, тот же downstream для Logic Engine и WS `/ws/live`).

Уточнение к ТЗ: `FK(Device)` недостаточно для маршрутизации, т.к. ключ
в `latest_tags` — это имя **тэга**, а у одного `Device` их несколько. Поэтому
в модели есть дополнительное поле `tag = FK(Tag)`, а `clean()` проверяет,
что тэг принадлежит выбранному устройству.

### Генераторы (`emulator/generators.py`)

Все формулы stateless — только от `time.time() % period`, рестарт безопасен:

- `constant` — всегда `min_value`;
- `random` — `random.uniform(min_value, max_value)` на каждый тик;
- `sine` — синусоида между `min`/`max` с периодом `period`;
- `ramp` — линейный рост `min → max` за `period`, затем сброс (`(now % period)/period`);
- `cycle` — чередование `[min, max]` (для `digital_input` обычно `0/1`),
  переключение каждые `period/2` (при `period=4` и тике 2 сек — `0/1/0/1...`).

### Планировщик (`run_simulators`)

По daemon-потоку на каждый активный `SimulatorDevice` — 10 устройств с разными
`update_interval` не блокируют друг друга (без celery/beat, только stdlib).
Главный цикл каждые `--reload` сек (по умолчанию 10) сверяет список `enabled=True`
с запущенными потоками: новые стартует, выключенные/удалённые останавливает.
Воркер при ошибке публикации/генерации логирует и продолжает, процесс не падает.

Переменные окружения:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `FASTAPI_URL` | `http://localhost:9000` | куда `POST /ingest` |
| `REDIS_HOST` / `REDIS_PORT` | `localhost` / `6379` | fallback `HSET latest_tags` + локальная отладка |

### Стартовый набор (`seed_simulators`)

Идемпотентно (`update_or_create` по `tag`): устройство «Симуляторная»
(127.0.0.1, modbus) + 10 тэгов `sim_*` (адреса 0–9) + 10 симуляторов по ТЗ:

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

Свои симуляторы — через админку (раздел «Эмулятор»): выбрать `device` + `tag`,
тип, режим, диапазон, интервалы. Тесты: `python manage.py test emulator` (6 тестов
генераторов, без БД/Redis).

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

Правила точно так же видят тэги `sim_*` от эмулятора — для проверки достаточно
написать условие вида `tags.get('sim_press_1', 99) > 9`.

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

## Конструктор экранов (`/screens/<id>/edit/`, только staff)

Вариант А из ТЗ (Django-шаблон `scada/templates/scada/constructor.html`,
без Vite/CORS — страница и API на одном домене по сессии). Исходников React
нет (прототип `Scada-Constructor-Prototype.html` — собранный бандл), поэтому
редактор написан на ванильном JS с тем же функционалом.

Формат виджета в `Screen.widgets` (JSON):
`{id, type, x, y, w, h, color, label, rotation, tag_id, device_id,
warn_above, alarm_above}`. Привязка — `{tag_id, device_id}` на реальные
`Tag`/`Device` (могут быть `null` — труба/label без тэга), выбираются
в панели свойств из `GET /api/tags/`.

Возможности: палитра → drag-and-drop на канвас (типы `pump, valve, tank,
motor, pipe-h/v, label, indicator, number, lamp, fan`; новый тип — одна запись
в словаре `TYPES`), drag мышью, Shift+клик — мультивыбор с групповым
перетаскиванием/удалением, undo/redo (до 50 шагов, Ctrl+Z/Ctrl+Y),
условное форматирование (`warn_above`/`alarm_above` — рамка янтарь/красная;
насосы/моторы — зелёный/красный по вкл/выкл), dropdown-навигация между экранами,
alarm-баннер в Preview (`GET /api/alarms` — Django-прокси к FastAPI,
чтобы браузер не упирался в CORS; напрямую у FastAPI CORS тоже открыт:
`ALLOWED_ORIGINS`, по умолчанию `*`), Save — `PATCH /api/screens/<id>/`
с защитой от конфликта (409), живой JSON модели внизу.

## Дашборд

`GET /screens/<id>/` — чистый HTML+JS без фреймворков (`scada/templates/scada/dashboard.html`),
показывает оба формата: виджеты конструктора (`Screen.widgets`, абсолютные `x/y`
на канвасе `width×height`, live-значения и пороговые цвета по WS) и ниже —
legacy grid по `row`/`col` (обновляется каждые 30 с из API). Ссылка
«→ открыть в конструкторе» ведёт на `/screens/<id>/edit/`:

- раскладка — CSS-grid по `row`/`col` виджетов (обновляется каждые 30 с из API);
- live-данные — WebSocket `ws://<host>:9000/ws/live`: при коннекте один полный
  снапшот, дальше только дельты `{tag: value}` изменившихся значений;
  клиент может прислать `{"subscribe": ["tag1", ...]}` (имена тэгов) —
  тогда дельты только по ним. Опрос сервера — каждые `WS_POLL_SEC` (0.5 с).
  Конструктор резолвит `tag_id → name` через `GET /api/tags/`.
  Старый дашборд дельты понимает (игнорирует отсутствующие ключи);
- типы: `number`/`chart` — текущее значение + единица; `indicator` — ● ВКЛ/ВЫКЛ.

Требует логина. Для доступа FastAPI WS из браузера ничего дополнительно настраивать
не нужно (WS без авторизации — данные телеметрии). Тэги `sim_*` на дашборд выводятся
обычными виджетами (привязка виджета к `Tag`).

## Redis-схема (не менять — все сервисы на неё опираются)

| Ключ | Тип | Кто пишет | Кто читает | Пример |
|---|---|---|---|---|
| `latest_tags` | HASH field→value | C3-драйвер, `POST /ingest` (в т.ч. эмулятор) | Logic Engine, FastAPI | `HSET latest_tags pressure 1.5` |
| `commands` | HASH tag→value | Logic Engine | C3-драйвер (заготовка) | `HGET commands pump_01` |
| `cmd/<tag>` | PUB/SUB | Logic Engine | подписчики команд | `cmd/pump_01 = 0` |
| `alarms` | LIST (LPUSH) | Logic Engine | операторы/мониторинг | `LRANGE alarms 0 10` |

FastAPI: `POST /ingest {"tag": ..., "value": ...}` пишет в `latest_tags`
и публикует в pub/sub канал `tag_updates`;
`GET /alarms?limit=20` — последние аварии (Redis LIST `alarms`, пишет Logic Engine);
`GET /history/{tag}` — заглушка под TimescaleDB.

## Типичные проблемы

- **401 от `/api/*`** — нет заголовка `Authorization: Bearer` или токен отозван /
  пользователь неактивен. Выпусти новый через `create_service_token`.
- **403 от `/api/screens/` или `/screens/<id>/edit/`** — запись экранов только
  для `is_staff` (в админке поставь флаг «staff status»); просмотр доступен всем
  залогиненным. Сервисным токенам нужен staff-владелец.
- **409 при Save в конструкторе** — экран параллельно сохранил кто-то другой;
  редактор предложит перезаписать или загрузить чужую версию.
- **Logic Engine пишет «Django недоступен»** — проверь `DJANGO_URL` и что
  `runserver` поднят; движок при этом продолжает работать на кэше правил.
- **Эмулятор пишет «POST /ingest недоступен, fallback в Redis»** — FastAPI
  не поднят или неверный `FASTAPI_URL`; данные при этом всё равно идут в тот же
  `latest_tags` напрямую, Logic Engine их увидит. Если следом ошибки Redis —
  проверь что Redis поднят (`compose up -d redis`).
- **Кракозябры/`UnicodeEncodeError` в Windows-консоли** — движок уже делает
  `sys.stdout.reconfigure(encoding="utf-8")`; выводы management-команд deliberately
  на английском. При желании: `$env:PYTHONUTF8="1"`.
- **Дашборд редиректит на `/admin/login/`** — так и должно: сначала залогинься.
- **C3-драйвер не видит конфиг** — проверь `CONFIG_PATH` и что файл экспортирован;
  без него работает fallback-карта из 3 тэгов.

## Что дальше

- Права пользователей: гранулярные `has_perm`-проверки в `api_auth_required` +
  группы в админке (база есть: запись экранов уже только для `is_staff`,
  токены привязаны к `User` — см. «Авторизация»)
- Конструктор: drag resize за угловые хендлы и rotation-хендл на канвасе
  (пока — числами в панели свойств), перетаскивание палитры на тачскринах
- TimescaleDB: история тэгов (`GET /history/{tag}`) и доделать `chart`-виджеты
- `scale` в `Tag` + третья колонка конфига C3-драйвера
- Запись команд C3-драйвером обратно в ПЛК (`HGET commands` → `modbus_write_register`)
- Тесты Django на API/авторизацию (`TestCase`) и CI (тесты генераторов эмулятора уже есть: `test emulator`)
