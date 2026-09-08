"""Планировщик эмулятора: у каждого SimulatorDevice свой независимый тик.

Механизм — отдельный daemon-поток на симулятор: 10 устройств с разными
update_interval не блокируют друг друга (каждый спит свой интервал).
Список активных перечитывается из БД каждые --reload сек, поэтому флаг
enabled в админке подхватывается без рестарта процесса.

Публикация — только через emulator.sender.publish (общий путь драйверов:
POST /ingest -> Redis latest_tags). Прямой записи в Device/Tag в БД нет.

Запуск:
    python manage.py run_simulators [--reload 10]
    FASTAPI_URL=http://localhost:9000 REDIS_HOST=localhost python manage.py run_simulators
"""

import logging
import threading
import time

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


def _worker(stop_event, sim_id):
    """Цикл одного симулятора: snapshot конфига свой, БД каждый тик не дёргаем."""
    from emulator.generators import compute_for_simulator
    from emulator.models import SimulatorDevice
    from emulator.sender import publish

    try:
        sim = SimulatorDevice.objects.select_related("tag").get(pk=sim_id)
    except SimulatorDevice.DoesNotExist:
        return
    tag_name = sim.tag.name
    interval = sim.update_interval
    logging.getLogger(__name__).warning(
        "simulator started: %s mode=%s every=%ss", tag_name, sim.mode, interval
    )
    while not stop_event.is_set():
        try:
            # enabled проверяем живым запросом, чтобы выключение в админке
            # останавливало поток до ближайшего reload в главном цикле
            if not SimulatorDevice.objects.filter(pk=sim_id, enabled=True).exists():
                break
            value = compute_for_simulator(sim)
            via = publish(tag_name, value)
            logger.debug("sim %s -> %s via %s", tag_name, value, via)
        except Exception as exc:  # noqa: BLE001 — воркер не должен падать
            logger.warning("simulator %s error: %s", tag_name, exc)
        stop_event.wait(interval)


class Command(BaseCommand):
    help = "Запустить эмуляторы (по потоку на каждый активный SimulatorDevice)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reload", type=float, default=10,
            help="Как часто перечитывать список активных симуляторов, сек.",
        )

    def handle(self, *args, **options):
        import django

        django.setup = getattr(django, "setup", None)
        from django.db import connections

        from emulator.models import SimulatorDevice

        reload_sec = options["reload"]
        running = {}  # sim_id -> (Thread, Event)

        self.stdout.write(f"Emulator running, reload every {reload_sec}s. Ctrl+C to stop.")
        try:
            while True:
                wanted = set(
                    SimulatorDevice.objects.filter(enabled=True).values_list("id", flat=True)
                )
                # Остановить выключенные/удалённые
                for sim_id in list(running):
                    if sim_id not in wanted:
                        thread, stop = running.pop(sim_id)
                        stop.set()
                        self.stdout.write(f"stopped simulator {sim_id}")
                # Запустить новые
                for sim_id in wanted - set(running):
                    stop = threading.Event()
                    thread = threading.Thread(
                        target=_worker, args=(stop, sim_id), daemon=True,
                        name=f"sim-{sim_id}",
                    )
                    thread.start()
                    running[sim_id] = (thread, stop)
                # Закрыть коннекты главного потока, чтобы не держать idle-соединения
                for conn in connections.all():
                    conn.close_if_unusable_or_obsolete()
                time.sleep(reload_sec)
        except KeyboardInterrupt:
            self.stdout.write("Stopping...")
            for _, stop in running.values():
                stop.set()
