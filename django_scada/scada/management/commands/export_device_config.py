import os

from django.core.management.base import BaseCommand, CommandError

from scada.models import Device


class Command(BaseCommand):
    help = "Экспорт карты регистров устройства в простой текстовый конфиг для C3-драйвера (строки 'name,address')."

    def add_arguments(self, parser):
        parser.add_argument("device_id", type=int, help="ID устройства")
        parser.add_argument(
            "--out",
            default=None,
            help="Путь к файлу. По умолчанию /config/device_<id>.txt (или ./device_<id>.txt если /config нет)",
        )

    def handle(self, *args, **options):
        try:
            device = Device.objects.get(pk=options["device_id"])
        except Device.DoesNotExist:
            raise CommandError(f"Device {options['device_id']} не найден")

        tags = device.tag_set.all().order_by("address")
        out = options["out"]
        if out is None:
            out = f"/config/device_{device.id}.txt" if os.path.isdir("/config") else f"device_{device.id}.txt"

        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            for t in tags:
                f.write(f"{t.name},{t.address}\n")

        self.stdout.write(self.style.SUCCESS(f"Exported {tags.count()} tags of device {device.id} -> {out}"))
