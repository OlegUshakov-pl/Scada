# Задание: сделать SCADA-конструктор конфигурируемым (устройства + дашборд)

## Контекст

Есть рабочий скелет из 4 сервисов: `django_scada`, `fastapi_realtime`, `logic_engine`, `c3_driver`, связанных через Redis. Модели `Device`, `Tag`, `Rule`, `Screen` в Django уже есть, но два места пока захардкожены в коде вместо конфигурации через БД:

1. `logic_engine/engine.py` — список `RULES` зашит прямо в Python-файле
2. `c3_driver/modbus_1.c3` — карта регистров (`reg0=pressure`, `reg1=temp_01`, `reg2=pump_fb`) зашита в код под конкретное устройство

Из-за этого добавление нового устройства или правила требует правки и передеплоя кода. Цель — убрать этот затык, чтобы добавление устройства/правила/виджета делалось через Django admin, без правки кода сервисов.

## Часть 1. Logic Engine: правила из БД вместо хардкода

**Было:** `RULES = [...]` — список словарей прямо в `engine.py`.

**Нужно:**
- Добавить в `django_scada` простой REST-эндпоинт (Django ninja/DRF или голый `JsonResponse`, без лишней инфраструктуры) `GET /api/rules/`, отдающий активные `Rule` в виде `[{"name": ..., "condition": ..., "action": ...}, ...]`
- В `logic_engine/engine.py` заменить константу `RULES` на функцию `load_rules()`, которая раз в 5–10 секунд опрашивает `GET /api/rules/` (через `requests`, с обработкой ошибки соединения — если Django недоступен, работать на последнем закэшированном списке правил, не падать)
- Основной цикл `while True` использует текущий закэшированный список правил вместо статической константы
- Логику `eval`/`exec` над `condition`/`action` не менять — она остаётся, меняется только источник правил

## Часть 2. C3-драйвер: конфигурируемая карта регистров вместо хардкода на устройство

**Было:** `modbus_1.c3` жёстко знает про 3 регистра (`pressure`, `temp_01`, `pump_fb`) для одного устройства.

**Нужно:**
- В Django добавить эндпоинт `GET /api/devices/<id>/tags/`, отдающий список тэгов устройства: `[{"name": "pressure", "address": 0, "unit": "bar"}, ...]`
- Модифицировать `modbus_1.c3` так, чтобы он при старте (или через простой JSON-файл конфигурации, экспортированный отдельным Django management-command'ом в `/config/device_<id>.json`) получал список `{name, address}` и в цикле читал регистры по этому списку, а не по хардкоду `regs[0]/regs[1]/regs[2]`
- Формирование строки `redisCommand(... "HSET latest_tags %s %f ...")` собирать динамически по списку тэгов, а не как строку с 3 фиксированными полями
- Не переусложнять: если полноценный JSON-парсер в C3 добавлять дорого, ок сделать простой формат конфига (например, `name,address` построчно в текстовом файле) — простота важнее гибкости

## Часть 3. Дашборд: модель Widget вместо ручного JSON

**Было:** `Screen.layout` — `JSONField`, который нужно было бы писать руками, конструктора нет.

**Нужно:**
- Добавить модель в `scada/models.py`:
```python
class Widget(models.Model):
    WIDGET_TYPES = [('number', 'Число'), ('chart', 'График'), ('indicator', 'Индикатор')]
    screen = models.ForeignKey(Screen, on_delete=models.CASCADE, related_name='widgets')
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    widget_type = models.CharField(max_length=20, choices=WIDGET_TYPES, default='number')
    row = models.IntegerField(default=0)
    col = models.IntegerField(default=0)
    label = models.CharField(max_length=100, blank=True)
```
- Зарегистрировать `Widget` как `TabularInline` в `ScreenAdmin`, чтобы виджеты добавлялись прямо на странице экрана в админке
- Убрать использование `Screen.layout` как основного способа задать раскладку — оставить поле как есть (не трогать/не удалять), но дашборд собирается из `Widget`, а не из ручного JSON
- Добавить эндпоинт `GET /api/screens/<id>/widgets/`, отдающий список виджетов экрана с их `row/col/widget_type/tag.name`
- На фронте (простой HTML+JS, без React) — страница дашборда рисует CSS-grid по `row/col`, подключается к существующему `ws://.../ws/live` в FastAPI и обновляет значения виджетов по имени тэга из приходящего JSON

## Ограничения

- Не строить drag-n-drop редактор дашбордов — расположение виджетов (row/col) задаётся числами в админке, этого достаточно для MVP
- Не менять стек и Redis-схему (`latest_tags`, `cmd/*`, `alarms`) — расширяем существующее, не переписываем с нуля
- Минимум новых зависимостей: для REST можно обойтись `JsonResponse`/`django.views`, DRF не обязателен

## Про запуск (важно)

`django_scada`, `fastapi_realtime` и `logic_engine` разрабатываются и запускаются как обычные Python-процессы в venv (без Docker) — не оборачивать их обратно в контейнеры и не добавлять для них Dockerfile-шаги в это задание. `docker-compose.yml` остаётся только для инфраструктуры — Redis и (при подключении) TimescaleDB.
