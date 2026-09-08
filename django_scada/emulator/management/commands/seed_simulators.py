"""Стартовый набор из 10 SimulatorDevice (идемпотентно).

Создаёт отдельное устройство «Симуляторная» с 10 тэгами (реальные Device
не трогаем) и привязывает к ним 10 симуляторов строго по таблице из ТЗ.
Повторный запуск дубликатов не создаёт (update_or_create по tag).
"""

from django.core.management.base import BaseCommand

from emulator.models import SimulatorDevice
from scada.models import Device, Tag

# (tag_name, address, unit, signal_type, mode, min, max, period, update_interval)
SPECS = [
    ("sim_temp_1", 0, "C", "temperature", "sine", 18, 26, 300, 2),
    ("sim_temp_2", 1, "C", "temperature", "random", 15, 30, 60, 5),
    ("sim_press_1", 2, "bar", "pressure", "ramp", 0, 10, 60, 1),
    ("sim_press_2", 3, "bar", "pressure", "sine", 2, 8, 120, 2),
    ("sim_di_1", 4, "", "digital_input", "cycle", 0, 1, 4, 2),
    ("sim_di_2", 5, "", "digital_input", "constant", 1, 1, 60, 10),
    ("sim_motor_1", 6, "rpm", "motor", "ramp", 0, 1500, 30, 1),
    ("sim_motor_2", 7, "rpm", "motor", "random", 0, 1500, 60, 3),
    ("sim_temp_3", 8, "C", "temperature", "constant", 22, 22, 60, 10),
    ("sim_press_3", 9, "bar", "pressure", "random", 0, 12, 60, 5),
]


class Command(BaseCommand):
    help = "Seed 10 SimulatorDevice на отдельном устройстве «Симуляторная»."

    def handle(self, *args, **options):
        device, _ = Device.objects.get_or_create(
            name="Симуляторная",
            defaults={"ip": "127.0.0.1", "protocol": "modbus"},
        )
        created = 0
        for name, address, unit, signal, mode, lo, hi, period, interval in SPECS:
            tag, _ = Tag.objects.get_or_create(
                device=device,
                name=name,
                defaults={"address": address, "unit": unit},
            )
            _, was_created = SimulatorDevice.objects.update_or_create(
                tag=tag,
                defaults={
                    "device": device,
                    "signal_type": signal,
                    "mode": mode,
                    "min_value": lo,
                    "max_value": hi,
                    "period": period,
                    "update_interval": interval,
                    "enabled": True,
                },
            )
            created += int(was_created)
        self.stdout.write(
            self.style.SUCCESS(f"Simulator device seeded: 10 tags, created now: {created}")
        )
