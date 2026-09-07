# My SCADA - Django + FastAPI + C3 + Logic Engine

4 слоя, всё в контейнерах (Podman/Docker compose), Python 3.14.

## Запуск

```
podman compose -f composer.yml up -d
```
(или `docker compose -f composer.yml up -d`, если решишь вернуться на Docker)

Сервисы:
- Django admin: http://localhost:8000/admin/  (admin/admin)
- FastAPI: http://localhost:9000/  и WS: ws://localhost:9000/ws/live
- Redis, TimescaleDB — внутренние, доступны по именам `redis`/`postgres` внутри сети compose (наружу тоже проброшены: 6379 и 5432)

Код каждого сервиса примонтирован как volume — правки в файлах подхватываются на лету (`--reload` у uvicorn, автоперезагрузка у `runserver`), пересобирать образ на каждое изменение не нужно.

## Симуляция датчика (пока нет живого C3-драйвера)

```
podman exec -it my_scada-redis-1 redis-cli HSET latest_tags pressure 1.5 temp_01 85
```

Через 5 сек в логах `logic_engine` должно сработать правило "Защита насоса".

## Авторизация

Зависимостей не добавлялось — только встроенный `django.contrib.auth`.

- `/api/*` требует либо сессию залогиненного пользователя, либо Bearer-токен сервиса:
  `Authorization: Bearer <токен>`
- Дашборд `screens/<id>/` требует логин (редирект на `/admin/login/`), JS ходит к API по куке сессии
- Токен привязан к `User` (`ServiceToken`), поэтому будущие права лягут на стандартные
  `has_perm`/`Group` без рефакторинга — сервисы наследуют права владельца токена

```
# создать пользователя и токен (сырой токен показывается один раз!)
python manage.py createsuperuser
python manage.py create_service_token --user <username> --name logic_engine

# logic_engine забирает правила с токеном (без токена — 401 и работа на кэше)
SCADA_API_TOKEN=<токен> DJANGO_URL=http://localhost:8000 python engine.py
```

Отзыв токена — флаг `is_active` в админке (`ServiceToken`) или удаление записи.

## Версии

- Python 3.14 (`python:3.14-slim` во всех трёх Dockerfile)
- Django >= 5.2 (первая версия с официальной поддержкой Python 3.14)
- TimescaleDB на базе PostgreSQL 17

## Что дальше

- Напиши реальный modbus.c3, который пишет в Redis
- В Django админке добавь свои Device/Tag/Rule
- Замени RULES в logic_engine/engine.py на загрузку из Django API (см. task-scada-config-driven.md)
- Подключи TimescaleDB в Django/FastAPI для хранения истории тегов
